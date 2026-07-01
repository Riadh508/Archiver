"""Archive operations: add, extract, list, search, remove, verify, sign, lock, unlock"""

import hashlib
import os
import secrets
import shutil
import sys
import tarfile
import zipfile
from pathlib import Path

from . import core
from .config import ARCHIVES_DIR, LOG_PATH
from .log import get as get_logger

log = get_logger(LOG_PATH, "INFO")


def _checksum(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _size_fmt(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def _find_files(src: Path, glob: str | None) -> list[tuple[str, str, int, str | None]]:
    files = []
    if src.is_file():
        files.append((src.name, src.name, src.stat().st_size, None))
        return files
    if glob:
        for fpath in sorted(src.glob("**/*")):
            if fpath.is_file():
                rel = str(fpath.relative_to(src))
                if fpath.match(glob) or Path(rel).match(glob):
                    files.append((fpath.name, rel, fpath.stat().st_size, None))
    else:
        for fpath in sorted(src.rglob("*")):
            if fpath.is_file():
                rel = str(fpath.relative_to(src))
                files.append((fpath.name, rel, fpath.stat().st_size, None))
    return files


def _safe_extract_zip(src: Path, dst: Path):
    dst_resolved = dst.resolve()
    with zipfile.ZipFile(str(src), "r") as z:
        for info in z.infolist():
            resolved = (dst / info.filename).resolve()
            prefix = str(dst_resolved) + os.sep
            if not str(resolved).startswith(prefix) and resolved != dst_resolved:
                raise ValueError(f"Zip slip blocked: {info.filename}")
            if info.filename.endswith("/"):
                resolved.mkdir(parents=True, exist_ok=True)
            else:
                resolved.parent.mkdir(parents=True, exist_ok=True)
                with open(resolved, "wb") as f:
                    f.write(z.read(info.filename))


def _safe_extract_tar(src: Path, dst: Path):
    dst_resolved = dst.resolve()
    prefix = str(dst_resolved) + os.sep
    with tarfile.open(str(src), "r") as t:
        for member in t.getmembers():
            resolved = (dst / member.name).resolve()
            if not str(resolved).startswith(prefix) and resolved != dst_resolved:
                raise ValueError(f"Tar slip blocked: {member.name}")
            if member.isdir():
                resolved.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                resolved.parent.mkdir(parents=True, exist_ok=True)
                with open(resolved, "wb") as f:
                    f.write(t.extractfile(member).read())


def _safe_extract(src: Path, dst: Path):
    ext = "".join(src.suffixes)
    if ext in (".zip",):
        _safe_extract_zip(src, dst)
    elif ext in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz"):
        _safe_extract_tar(src, dst)
    else:
        shutil.unpack_archive(str(src), str(dst))


def _maybe_crypto():
    try:
        from cryptography.fernet import Fernet
        return Fernet
    except ImportError:
        return None


def _get_fernet_key(password: str) -> bytes:
    key = hashlib.sha256(password.encode()).digest()
    from base64 import urlsafe_b64encode
    return urlsafe_b64encode(key)


def cmd_add(paths: list[str], fmt: str | None, name: str | None,
            notes: str, glob_pattern: str | None, level: int | None,
            category: str = "") -> list[int]:
    ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)
    core.init_db()
    created = []

    for i, src_path in enumerate(paths):
        src = Path(src_path).resolve()
        if not src.exists():
            log.error(f"Path not found: {src_path}")
            continue

        label = name or src.stem
        ext = fmt or "zip"
        ext_map = {"tar": "tar", "gztar": "tar.gz", "bztar": "tar.bz2", "xztar": "tar.xz"}
        display_ext = ext_map.get(ext, ext)

        dest = ARCHIVES_DIR / f"{label}.{display_ext}"
        archive_name = str(dest.parent / label)
        root_dir = str(src.parent) if src.is_dir() else None

        print(f"[{i+1}/{len(paths)}] Creating {display_ext} archive: {label}", file=sys.stderr)
        archive_path = shutil.make_archive(
            archive_name, fmt or "zip", root_dir=root_dir,
            base_dir=src.name if src.is_dir() else None,
        )
        archive_path = Path(archive_path)
        chk = _checksum(archive_path)
        files = _find_files(src, glob_pattern)
        total_size = sum(f[2] for f in files)

        aid = core.add_archive(
            name=label,
            path=str(archive_path),
            fmt=display_ext,
            size=archive_path.stat().st_size,
            file_count=len(files),
            checksum=chk,
            notes=notes,
            category=category,
        )
        if files:
            core.add_files(aid, files)

        log.info(f"Archive created: id={aid}")
        print(f"  -> id={aid} files={len(files)} size={_size_fmt(archive_path.stat().st_size)}", file=sys.stderr)
        created.append(aid)

    return created


def cmd_list(archive_id: int | None, json: bool = False):
    core.init_db()
    if json:
        import json as _json
        if archive_id is not None:
            arch = core.get_archive(archive_id)
            if not arch:
                print(_json.dumps({"error": "not found"}))
                return
            files = core.list_files(archive_id)
            print(_json.dumps({
                "archive": arch._asdict(),
                "files": [f._asdict() for f in files],
            }, default=str, indent=2))
        else:
            archives = core.list_archives()
            print(_json.dumps([a._asdict() for a in archives], default=str, indent=2))
        return

    if archive_id is not None:
        arch = core.get_archive(archive_id)
        if not arch:
            log.error(f"Archive id={archive_id} not found")
            return
        print(f"ID:       {arch.id}")
        print(f"Name:     {arch.name}")
        print(f"Path:     {arch.path}")
        print(f"Format:   {arch.format}")
        print(f"Size:     {_size_fmt(arch.size_bytes)}")
        print(f"Files:    {arch.file_count}")
        print(f"Checksum: {arch.checksum or '-'}")
        print(f"Signature:{' OK' if core.verify_signature(archive_id) else ' MISSING' if arch.signature else ' NONE'}")
        print(f"Notes:    {arch.notes or '-'}")
        print(f"Created:  {arch.created_at}")
        print(f"Updated:  {arch.updated_at}")
        print()
        files = core.list_files(archive_id)
        if files:
            print(f"{'File':<40} {'Size':<10}")
            print("-" * 50)
            for f in files:
                print(f"{f.path:<40} {_size_fmt(f.size_bytes):<10}")
    else:
        archives = core.list_archives()
        if not archives:
            print("No archives found.")
            return
        print(f"{'ID':<4} {'Name':<25} {'Format':<10} {'Size':<10} {'Files':<6} {'Sig':<5} {'Created':<20}")
        print("-" * 80)
        for a in archives:
            sig = "OK" if core.verify_signature(a.id) else "NO"
            print(f"{a.id:<4} {a.name:<25} {a.format:<10} {_size_fmt(a.size_bytes):<10} {a.file_count:<6} {sig:<5} {a.created_at:<20}")


def cmd_extract(archive_id: int, output_dir: str | None):
    core.init_db()
    arch = core.get_archive(archive_id)
    if not arch:
        log.error(f"Archive id={archive_id} not found")
        return

    src = Path(arch.path)
    if not src.exists():
        log.error(f"Archive file not found: {src}")
        return

    out = Path(output_dir) if output_dir else Path.cwd() / arch.name
    out.mkdir(parents=True, exist_ok=True)

    log.info("Extracting with zip-slip protection")
    try:
        _safe_extract(src, out)
    except (ValueError, Exception) as e:
        log.error(f"Extraction failed: {e}")
        return
    log.info(f"Extracted to {out}")


def cmd_search(query: str):
    core.init_db()
    results = core.search_files(query)
    if not results:
        print(f"No results for '{query}'")
        return
    for arch, file_rec in results:
        print(f"[{arch.id:>3}] {arch.name:<20}  {file_rec.path:<50}  {_size_fmt(file_rec.size_bytes):<10}")


def cmd_remove(archive_id: int):
    core.init_db()
    arch = core.get_archive(archive_id)
    if not arch:
        log.error(f"Archive id={archive_id} not found")
        return
    core.soft_delete_archive(archive_id)
    log.info(f"Archive id={archive_id} soft-deleted")


def cmd_verify(archive_id: int):
    core.init_db()
    arch = core.get_archive(archive_id)
    if not arch:
        log.error(f"Archive id={archive_id} not found")
        return

    sig_ok = core.verify_signature(archive_id)
    if not sig_ok and arch.signature:
        print("FAIL: HMAC signature mismatch — data may be tampered")
        log.error(f"HMAC mismatch for id={archive_id}")
        return

    src = Path(arch.path)
    if not src.exists():
        log.error(f"Archive file missing: {src}")
        return
    actual = _checksum(src)
    if arch.checksum and actual != arch.checksum:
        log.error(f"Checksum MISMATCH for id={archive_id}")
        print(f"FAIL: checksum mismatch (expected {arch.checksum}, got {actual})")
    else:
        status = "HMAC verified + " if sig_ok else ""
        print(f"PASS: {status}checksum matches")
        log.info(f"Archive id={archive_id} verified OK")


def cmd_restore(archive_id: int):
    core.init_db()
    ok = core.restore_archive(archive_id)
    if ok:
        log.info(f"Archive id={archive_id} restored")
    else:
        log.error(f"Archive id={archive_id} not found or not deleted")


def cmd_prune():
    core.init_db()
    count = core.prune_archives()
    print(f"Pruned {count} soft-deleted archive(s)")


def cmd_export(dest: str):
    core.init_db()
    core.export_db(dest)
    print(f"Exported to {dest}")


def cmd_import(src: str):
    core.import_db(src)
    core.init_db()
    print(f"Imported from {src}")


def cmd_scan(dir_path: str, fmt: str | None, glob_pattern: str | None, notes: str):
    root = Path(dir_path).resolve()
    if not root.is_dir():
        log.error(f"Not a directory: {dir_path}")
        return
    subdirs = sorted(d for d in root.iterdir() if d.is_dir())
    if not subdirs:
        print(f"No subdirectories found in {dir_path}")
        return
    print(f"Scanning {len(subdirs)} subdirectories...", file=sys.stderr)
    paths = [str(d) for d in subdirs]
    created = cmd_add(paths, fmt=fmt, name=None, notes=notes, glob_pattern=glob_pattern, level=None)
    print(f"Created {len(created)} archive(s)")


def cmd_lock(archive_id: int, password: str):
    Fernet = _maybe_crypto()
    if Fernet is None:
        print("Error: 'cryptography' package required for encryption. Install: pip install cryptography")
        return
    core.init_db()
    arch = core.get_archive(archive_id)
    if not arch:
        log.error(f"Archive id={archive_id} not found")
        return
    src = Path(arch.path)
    if not src.exists():
        log.error(f"Archive file not found: {src}")
        return
    key = _get_fernet_key(password)
    f = Fernet(key)
    data = src.read_bytes()
    encrypted = f.encrypt(data)
    encrypted_path = src.with_suffix(src.suffix + ".enc")
    encrypted_path.write_bytes(encrypted)
    src.unlink()
    core.update_archive_size(archive_id, len(encrypted))
    log.info(f"Archive id={archive_id} encrypted")
    print(f"Locked: {encrypted_path}")


def cmd_unlock(archive_id: int, password: str, output: str | None):
    Fernet = _maybe_crypto()
    if Fernet is None:
        print("Error: 'cryptography' package required for decryption. Install: pip install cryptography")
        return
    core.init_db()
    arch = core.get_archive(archive_id)
    if not arch:
        log.error(f"Archive id={archive_id} not found")
        return
    src = Path(arch.path)
    if not src.exists():
        log.error(f"Archive file not found: {src}")
        return
    key = _get_fernet_key(password)
    f = Fernet(key)
    try:
        decrypted = f.decrypt(src.read_bytes())
    except Exception:
        log.error("Decryption failed — wrong password or corrupted data")
        print("FAIL: decryption failed (wrong password?)")
        return
    dec_path = Path(output) if output else src.with_suffix("")
    dec_path.write_bytes(decrypted)
    log.info(f"Archive id={archive_id} decrypted to {dec_path}")
    print(f"Unlocked: {dec_path}")


# ─── License Commands ────────────────────────────────────────────────────────

def cmd_license_generate(license_type: str, hardware_id: str | None = None,
                         device_bound: bool = False, count: int = 1):
    if license_type not in core.LICENSE_TYPES:
        print(f"Error: invalid license type '{license_type}'")
        return
    secret = core._get_license_secret()
    for i in range(count):
        label = f"[{i+1}/{count}] " if count > 1 else ""
        raw = secrets.token_hex(8).upper()
        if (device_bound or hardware_id) and hardware_id:
            hw_part = hardware_id.replace("HW-", "").replace("-", "").upper()[:12]
            sig = hashlib.sha256((secret + hw_part + raw + license_type).encode()).hexdigest()[:6].upper()
            code = f"{hw_part}_{raw}_{license_type}_{sig}"
        else:
            sig = hashlib.sha256((secret + raw + license_type).encode()).hexdigest()[:4].upper()
            code = f"{raw}_{license_type}_{sig}"
        info = core.LICENSE_TYPES[license_type]
        from datetime import datetime, timedelta
        expiry = (datetime.now() + timedelta(days=info["days"], minutes=info["minutes"])).strftime("%Y-%m-%d")
        print(f"{label}{code}  (expires: {expiry})")


def cmd_license_activate(code: str):
    core.init_db()
    valid, msg = core.activate_license(code)
    print(f"{'OK' if valid else 'FAIL'}: {msg}")


def cmd_license_verify(code: str):
    core.init_db()
    valid, msg = core.verify_license_code(code)
    print(f"{'VALID' if valid else 'INVALID'}: {msg}")


def cmd_license_status():
    core.init_db()
    valid, msg, info = core.check_license_status()
    if not valid:
        print(f"No active license: {msg}")
        return
    print(f"Type:    {info['type']}")
    print(f"Expires: {info['expires_at']}")
    print(f"Days remaining: {info['remaining_days']}")


# ─── User Commands ───────────────────────────────────────────────────────────

def cmd_user_add(username: str, password: str, role: str = "user", full_name: str = ""):
    core.init_db()
    uid = core.add_user(username, password, role, full_name)
    if uid:
        print(f"User created: id={uid}")
    else:
        print(f"Error: username '{username}' already exists")


def cmd_user_list():
    core.init_db()
    users = core.list_users()
    if not users:
        print("No users found")
        return
    print(f"{'ID':<4} {'Username':<20} {'Role':<10} {'Name':<20} {'Created':<20}")
    print("-" * 74)
    for u in users:
        print(f"{u['id']:<4} {u['username']:<20} {u['role']:<10} {u.get('full_name',''):<20} {u['created_at']:<20}")


def cmd_user_delete(user_id: int):
    core.init_db()
    ok = core.delete_user(user_id)
    if ok:
        print(f"User id={user_id} deleted")
    else:
        print(f"Cannot delete id={user_id} (not found or is admin)")


# ─── Backup Commands ─────────────────────────────────────────────────────────

def cmd_backup():
    core.init_db()
    path = core.create_backup()
    if path:
        print(f"Backup created: {path}")
    else:
        print("Error: backup failed")


def cmd_backup_list():
    core.init_db()
    backups = core.list_backups()
    if not backups:
        print("No backups found")
        return
    print(f"{'ID':<4} {'Filename':<40} {'Size':<10} {'Created':<20}")
    print("-" * 74)
    for b in backups:
        print(f"{b['id']:<4} {b['filename']:<40} {_size_fmt(b['size_bytes']):<10} {b['created_at']:<20}")


def cmd_backup_restore(backup_id: int):
    core.init_db()
    path = core.restore_backup(backup_id)
    if path:
        print(f"Backup id={backup_id} restored from {path}")
    else:
        print(f"Error: backup id={backup_id} not found")
