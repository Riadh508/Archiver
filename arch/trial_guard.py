"""Trial protection system — persistent trial state across DB resets."""

import hashlib
import hmac
import json
import os
import platform
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from . import config as cfg
from .log import get as get_logger

log = get_logger(None, "INFO")

TRIAL_TYPE = "7days"
TRIAL_DAYS = 7

_MARKER_DIR_NAME = "D3DSCache"
_MARKER_FILE_NAME = ".cache_state"

_REG_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
_REG_VALUE_NAME = "TaskbarSDR"

_TRIAL_KEY_CACHE: bytes | None = None


def _get_trial_key() -> bytes:
    global _TRIAL_KEY_CACHE
    if _TRIAL_KEY_CACHE is not None:
        return _TRIAL_KEY_CACHE
    if cfg.KEY_PATH.exists():
        _TRIAL_KEY_CACHE = cfg.KEY_PATH.read_bytes()
    else:
        machine = f"{platform.node()}|{uuid.getnode()}|{platform.machine()}"
        _TRIAL_KEY_CACHE = hashlib.sha256(machine.encode()).digest()
    return _TRIAL_KEY_CACHE


def _sign(data: str) -> str:
    return hmac.new(_get_trial_key(), data.encode(), "sha256").hexdigest()


def _verify(data: str, signature: str) -> bool:
    return hmac.compare_digest(_sign(data), signature)


def _get_marker_path() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        local = os.path.join(os.environ.get("APPDATA", ""), "..", "Local")
    cache_root = Path(local) / _MARKER_DIR_NAME
    cache_root.mkdir(parents=True, exist_ok=True)
    try:
        import ctypes
        ctypes.windll.kernel32.SetFileAttributesW(str(cache_root), 2)
    except Exception:
        pass
    return cache_root / _MARKER_FILE_NAME


def _get_registry_key() -> tuple[str, str]:
    return _REG_SUBKEY, _REG_VALUE_NAME


def _read_marker() -> dict | None:
    try:
        path = _get_marker_path()
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8").strip()
        obj = json.loads(raw)
        payload = obj.get("p", "")
        sig = obj.get("s", "")
        if not _verify(payload, sig):
            return None
        return json.loads(payload)
    except Exception:
        return None


def _write_marker(data: dict) -> bool:
    try:
        payload = json.dumps(data, separators=(",", ":"))
        sig = _sign(payload)
        path = _get_marker_path()
        path.write_text(json.dumps({"p": payload, "s": sig}), encoding="utf-8")
        try:
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(str(path), 2)
        except Exception:
            pass
        return True
    except Exception:
        return False


def _read_registry() -> dict | None:
    if platform.system() != "Windows":
        return None
    try:
        import winreg
        subkey, value_name = _get_registry_key()
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_READ)
        enc, _ = winreg.QueryValueEx(key, value_name)
        winreg.CloseKey(key)
        raw = enc.strip()
        obj = json.loads(raw)
        payload = obj.get("p", "")
        sig = obj.get("s", "")
        if not _verify(payload, sig):
            return None
        return json.loads(payload)
    except (FileNotFoundError, OSError, ValueError, PermissionError):
        return None
    except Exception:
        return None


def _write_registry(data: dict) -> bool:
    if platform.system() != "Windows":
        return False
    try:
        import winreg
        payload = json.dumps(data, separators=(",", ":"))
        sig = _sign(payload)
        enc = json.dumps({"p": payload, "s": sig})
        subkey, value_name = _get_registry_key()
        key = winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, enc)
        winreg.CloseKey(key)
        return True
    except (PermissionError, OSError):
        return False
    except Exception:
        return False


def _build_trial_data() -> dict:
    now = datetime.now()
    first_seen = now.isoformat()
    expires_at = (now + timedelta(days=TRIAL_DAYS)).isoformat()
    return {
        "first_seen": first_seen,
        "expires_at": expires_at,
        "trial_type": TRIAL_TYPE,
        "created_ts": now.timestamp(),
    }


def create_trial_record() -> str:
    existing = _read_marker() or _read_registry()
    if existing:
        return "existing"

    data = _build_trial_data()
    file_ok = _write_marker(data)
    reg_ok = _write_registry(data)

    status = "created"
    if file_ok:
        status += "+file"
    if reg_ok:
        status += "+reg"
    log.info(f"Trial record {status}: expires={data['expires_at']}")
    return status


def check_trial_status() -> dict:
    marker_data = _read_marker()
    reg_data = _read_registry()

    source_data = marker_data or reg_data

    if source_data is None:
        return {
            "status": "never_started",
            "message": "No trial record found",
            "trial_type": None,
            "expires_at": None,
            "remaining_seconds": None,
        }

    first_seen = source_data.get("first_seen", "")
    expires_at_str = source_data.get("expires_at", "")
    trial_type = source_data.get("trial_type", TRIAL_TYPE)

    try:
        expires_at = datetime.fromisoformat(expires_at_str)
    except (ValueError, TypeError):
        return {
            "status": "error",
            "message": "Invalid trial expiry data",
            "trial_type": trial_type,
            "expires_at": expires_at_str,
            "remaining_seconds": None,
        }

    now = datetime.now()
    remaining = (expires_at - now).total_seconds()

    if remaining > 0:
        return {
            "status": "active",
            "message": f"Trial active — {int(remaining // 3600)}h remaining",
            "trial_type": trial_type,
            "expires_at": expires_at_str,
            "remaining_seconds": remaining,
        }

    return {
        "status": "expired",
        "message": f"Trial expired on {expires_at_str}",
        "trial_type": trial_type,
        "expires_at": expires_at_str,
        "remaining_seconds": remaining,
    }


def is_trial_reset_detected() -> bool:
    marker_data = _read_marker()
    reg_data = _read_registry()

    if marker_data is None and reg_data is None:
        return False

    source_data = marker_data or reg_data
    first_seen = source_data.get("first_seen", "")
    expires_at_str = source_data.get("expires_at", "")

    try:
        expires_at = datetime.fromisoformat(expires_at_str)
    except (ValueError, TypeError):
        return True

    now = datetime.now()
    if now > expires_at:
        return True

    return False


def get_trial_first_seen() -> str | None:
    marker_data = _read_marker()
    reg_data = _read_registry()
    source = marker_data or reg_data
    if source:
        return source.get("first_seen")
    return None
