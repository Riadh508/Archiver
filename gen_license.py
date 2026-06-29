#!/usr/bin/env python3
"""Standalone license generator and verifier for arch system.

Generates HMAC-signed license codes compatible with arch's verify_license_code().
Uses a shared secret (from .arch_key or --secret) to produce signed codes.

Usage:
  python gen_license.py generate <type> [--hw HWID] [--count N] [--secret KEY]
  python gen_license.py verify <code> [--secret KEY]
  python gen_license.py export <type> [--hw HWID] [--output FILE] [--secret KEY]

Types: 5min, 7days, monthly, yearly, lifetime
"""

import argparse
import hashlib
import json
import secrets
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

LICENSE_TYPES = {
    "5min":     {"name": "Trial 5 minutes",  "days": 0,     "minutes": 5},
    "7days":    {"name": "Trial 7 days",     "days": 7,     "minutes": 0},
    "monthly":  {"name": "Monthly",          "days": 30,    "minutes": 0},
    "yearly":   {"name": "Yearly",           "days": 365,   "minutes": 0},
    "lifetime": {"name": "Lifetime",         "days": 36500, "minutes": 0},
}


def _get_secret(secret_arg: str | None) -> str:
    if secret_arg:
        return hashlib.sha256(secret_arg.encode()).hexdigest()
    key_file = Path(__file__).parent / "data" / ".arch_key"
    if key_file.exists():
        key = key_file.read_bytes()
        return hashlib.sha256(key + b"arch-license-v1").hexdigest()
    print("Error: no --secret provided and data/.arch_key not found.", file=sys.stderr)
    print("Run the arch system first to generate a key, or use --secret KEY.", file=sys.stderr)
    sys.exit(1)


def _extract_hw_part(hardware_id: str) -> str:
    hw = hardware_id.replace("HW-", "").replace("-", "").upper()
    return hw[:12]


def generate(license_type: str, hardware_id: str | None = None,
             is_device_bound: bool | None = None, secret_str: str | None = None) -> str | None:
    if license_type not in LICENSE_TYPES:
        print(f"Error: invalid license type '{license_type}'", file=sys.stderr)
        return None
    if is_device_bound is None:
        is_device_bound = hardware_id is not None
    raw = secrets.token_hex(8).upper()
    secret = _get_secret(secret_str)
    if is_device_bound and hardware_id:
        hw_part = _extract_hw_part(hardware_id)
        sig = hashlib.sha256((secret + hw_part + raw + license_type).encode()).hexdigest()[:6].upper()
        code = f"{hw_part}_{raw}_{license_type}_{sig}"
    else:
        sig = hashlib.sha256((secret + raw + license_type).encode()).hexdigest()[:4].upper()
        code = f"{raw}_{license_type}_{sig}"
    return code


def verify(code: str, secret_str: str | None = None) -> tuple[bool, str]:
    try:
        parts = code.split("_")
        secret = _get_secret(secret_str)
        if len(parts) == 4:
            hw_part, raw_part, type_part, sig_part = parts
            if type_part.lower() not in LICENSE_TYPES:
                return False, f"Unknown license type: {type_part}"
            expected = hashlib.sha256((secret + hw_part + raw_part + type_part.lower()).encode()).hexdigest()[:6].upper()
            if sig_part != expected:
                return False, "Invalid signature"
            return True, "VALID — Device-Specific"
        elif len(parts) == 3:
            raw_part, type_part, sig_part = parts
            if type_part.lower() not in LICENSE_TYPES:
                return False, f"Unknown license type: {type_part}"
            expected = hashlib.sha256((secret + raw_part + type_part.lower()).encode()).hexdigest()[:4].upper()
            if sig_part != expected:
                return False, "Invalid signature"
            return True, "VALID — General"
        else:
            return False, "Invalid license format"
    except Exception as e:
        return False, f"Verification error: {e}"


def export_activation(code: str, license_type: str, output: str | None = None):
    info = LICENSE_TYPES.get(license_type, {})
    now = datetime.now()
    expires = now.isoformat() if license_type == "lifetime" else (
        now + timedelta(days=info.get("days", 0), minutes=info.get("minutes", 0))
    ).isoformat()
    payload = {
        "license_code": code,
        "license_type": license_type,
        "generated_at": now.isoformat(),
        "expires_at": expires,
        "days_valid": info.get("days", 0),
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if output:
        Path(output).write_text(text, encoding="utf-8")
        print(f"Exported to {output}")
    else:
        print(text)


def _clear():
    os.system("cls" if os.name == "nt" else "clear")

def _pause():
    input("\nاضغط Enter للعودة...")


def interactive():
    while True:
        _clear()
        print("=" * 50)
        print("  📦 Archiver - مولد الترخيص (الوضع التفاعلي)")
        print("=" * 50)
        types_list = list(LICENSE_TYPES.keys())
        print("\n🔹 اختر نوع الترخيص:")
        for i, (key, val) in enumerate(LICENSE_TYPES.items(), 1):
            print(f"   {i}. {val['name']} ({key})")
        print(f"   {len(types_list)+1}. 🔍 التحقق من كود ترخيص")
        print(f"   {len(types_list)+2}. 📤 تصدير ترخيص إلى ملف JSON")
        print(f"   {len(types_list)+3}. 🚪 خروج")
        try:
            choice = input("\nأدخل رقم الاختيار: ").strip()
            if not choice:
                continue
            choice = int(choice)
        except ValueError:
            _pause()
            continue

        if choice == len(types_list) + 3:
            print("وداعاً!")
            break

        elif choice == len(types_list) + 1:
            _clear()
            print("=" * 50)
            print("  🔍 التحقق من كود الترخيص")
            print("=" * 50)
            code = input("\nأدخل كود الترخيص: ").strip()
            if code:
                valid, msg = verify(code)
                print(f"\n{'✅ صالح' if valid else '❌ غير صالح'}: {msg}")
            _pause()
            continue

        elif choice == len(types_list) + 2:
            _clear()
            print("=" * 50)
            print("  📤 تصدير ترخيص إلى ملف JSON")
            print("=" * 50)
            print("\n🔹 اختر نوع الترخيص:")
            for i, (key, val) in enumerate(LICENSE_TYPES.items(), 1):
                print(f"   {i}. {val['name']} ({key})")
            try:
                t = int(input("\nأدخل رقم النوع: ").strip())
                if t < 1 or t > len(types_list):
                    _pause()
                    continue
                license_type = types_list[t - 1]
            except ValueError:
                _pause()
                continue
            hw = input("رقم الجهاز (HWID) أو اتركه فارغاً: ").strip() or None
            out = input("مسار ملف الإخراج (أو اتركه فارغاً للطباعة): ").strip() or None
            code = generate(license_type, hw, None)
            if code:
                export_activation(code, license_type, out)
            _pause()
            continue

        elif 1 <= choice <= len(types_list):
            license_type = types_list[choice - 1]
            _clear()
            info = LICENSE_TYPES[license_type]
            print("=" * 50)
            print(f"  توليد ترخيص: {info['name']}")
            print("=" * 50)
            try:
                count = int(input("\nعدد التراخيص (Enter = 1): ").strip() or "1")
            except ValueError:
                count = 1
            hw = input("رقم الجهاز (HWID) أو اتركه فارغاً: ").strip() or None
            out = input("مسار ملف JSON أو اتركه فارغاً: ").strip() or None
            print()
            for i in range(count):
                label = f"[{i+1}/{count}] " if count > 1 else ""
                code = generate(license_type, hw, None)
                if code is None:
                    continue
                expiry = (datetime.now() + timedelta(days=info["days"], minutes=info["minutes"])).strftime("%Y-%m-%d")
                print(f"{label}{code}  (ينتهي: {expiry})")
                if out and count == 1:
                    export_activation(code, license_type, out)
            _pause()
            continue
        else:
            _pause()
            continue


def main():
    if len(sys.argv) == 1:
        interactive()
        return

    parser = argparse.ArgumentParser(
        prog="gen_license",
        description="Standalone license generator for arch system",
    )
    parser.add_argument("--secret", help="Shared secret key (default: read from data/.arch_key)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_gen = sub.add_parser("generate", help="Generate license code(s)")
    p_gen.add_argument("type", choices=list(LICENSE_TYPES.keys()), help="License type")
    p_gen.add_argument("--hw", "--hardware", help="Hardware ID for device-bound license")
    p_gen.add_argument("--device-bound", action="store_true", default=None, help="Force device-bound (auto if --hw provided)")
    p_gen.add_argument("--count", "-c", type=int, default=1, help="Number of codes to generate (default: 1)")
    p_gen.add_argument("--output", "-o", help="Export to JSON file")

    p_vfy = sub.add_parser("verify", help="Verify a license code")
    p_vfy.add_argument("code", help="License code to verify")

    p_export = sub.add_parser("export", help="Generate and export activation JSON")
    p_export.add_argument("type", choices=list(LICENSE_TYPES.keys()), help="License type")
    p_export.add_argument("--hw", "--hardware", help="Hardware ID for device-bound")
    p_export.add_argument("--device-bound", action="store_true", default=None, help="Force device-bound (auto if --hw provided)")
    p_export.add_argument("--output", "-o", help="Output JSON file (default: stdout)")

    args = parser.parse_args()

    if args.command == "generate":
        for i in range(args.count):
            label = f"[{i+1}/{args.count}] " if args.count > 1 else ""
            code = generate(args.type, args.hw, args.device_bound, args.secret)
            if code is None:
                sys.exit(1)
            if args.output and args.count == 1:
                export_activation(code, args.type, args.output)
            else:
                info = LICENSE_TYPES[args.type]
                expiry = (datetime.now() + timedelta(days=info["days"], minutes=info["minutes"])).strftime("%Y-%m-%d")
                print(f"{label}{code}  (expires: {expiry})")

    elif args.command == "verify":
        valid, msg = verify(args.code, args.secret)
        print(f"{'VALID' if valid else 'INVALID'}: {msg}")
        sys.exit(0 if valid else 1)

    elif args.command == "export":
        code = generate(args.type, args.hw, args.device_bound, args.secret)
        if code is None:
            sys.exit(1)
        export_activation(code, args.type, args.output)


if __name__ == "__main__":
    main()
