"""SQLite database core — models and CRUD for archives & files"""

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import platform as _platform
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import NamedTuple

from . import config as cfg
from .log import get as get_logger
from . import trial_guard
from . import trial_guard

log = get_logger(cfg.LOG_PATH, "INFO")

_local = threading.local()
_KEY_CACHE: bytes | None = None
_KEY_LOCK = threading.Lock()


def _get_or_create_key() -> bytes:
    global _KEY_CACHE
    if _KEY_CACHE is not None:
        return _KEY_CACHE
    with _KEY_LOCK:
        if _KEY_CACHE is not None:
            return _KEY_CACHE
        if cfg.KEY_PATH.exists():
            _KEY_CACHE = cfg.KEY_PATH.read_bytes()
        else:
            cfg.KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
            _KEY_CACHE = secrets.token_bytes(32)
            cfg.KEY_PATH.write_bytes(_KEY_CACHE)
            os.chmod(str(cfg.KEY_PATH), 0o600)
        return _KEY_CACHE


def _sign(data: str) -> str:
    key = _get_or_create_key()
    return hmac.new(key, data.encode(), "sha256").hexdigest()


def _sanitize(val: str, maxlen: int = 512) -> str:
    return val.strip().replace("\0", "")[:maxlen]


def _sanitize_path(val: str) -> str:
    p = Path(val).as_posix()
    if ".." in p.split("/"):
        raise ValueError(f"Path contains parent traversal: {val}")
    return p


class ArchiveRecord(NamedTuple):
    id: int
    name: str
    path: str
    format: str
    size_bytes: int
    file_count: int
    checksum: str
    signature: str
    notes: str
    category: str
    created_at: str
    updated_at: str
    is_deleted: bool


class FileRecord(NamedTuple):
    id: int
    archive_id: int
    name: str
    path: str
    size_bytes: int
    checksum: str
    created_at: str


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None or _local.db_path != str(cfg.DB_PATH):
        if hasattr(_local, "conn") and _local.conn is not None:
            _local.conn.close()
        cfg.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _local.conn = sqlite3.connect(str(cfg.DB_PATH))
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
        _local.db_path = str(cfg.DB_PATH)
    return _local.conn


@contextmanager
def _tx():
    conn = _get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db():
    with _tx() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS archives (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                path        TEXT NOT NULL,
                format      TEXT NOT NULL DEFAULT 'zip',
                size_bytes  INTEGER NOT NULL DEFAULT 0,
                file_count  INTEGER NOT NULL DEFAULT 0,
                checksum    TEXT,
                signature   TEXT,
                notes       TEXT,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                is_deleted  INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS files (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                archive_id  INTEGER NOT NULL REFERENCES archives(id) ON DELETE CASCADE,
                name        TEXT NOT NULL,
                path        TEXT NOT NULL,
                size_bytes  INTEGER NOT NULL DEFAULT 0,
                checksum    TEXT,
                created_at  TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_files_archive ON files(archive_id);
            CREATE INDEX IF NOT EXISTS idx_files_name   ON files(name);
            CREATE INDEX IF NOT EXISTS idx_archives_name ON archives(name);
        """)
        # Migrate: add missing columns
        cols = [r[1] for r in conn.execute("PRAGMA table_info(archives)")]
        if "signature" not in cols:
            conn.execute("ALTER TABLE archives ADD COLUMN signature TEXT")
        if "category" not in cols:
            conn.execute("ALTER TABLE archives ADD COLUMN category TEXT DEFAULT ''")
        _add_license_tables(conn)
    try:
        trial_guard.create_trial_record()
    except Exception:
        pass
    log.info("Database initialised")


def add_archive(name: str, path: str, fmt: str, size: int,
                file_count: int, checksum: str | None = None,
                notes: str = "", category: str = "") -> int:
    name = _sanitize(name)
    notes = _sanitize(notes, 2000)
    category = _sanitize(category, 128)
    sig = _sign(checksum or "") if checksum else None
    now = datetime.now().isoformat()
    with _tx() as conn:
        cur = conn.execute(
            "INSERT INTO archives (name,path,format,size_bytes,file_count,checksum,signature,notes,category,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (name, path, fmt, size, file_count, checksum, sig, notes, category, now, now),
        )
        aid = cur.lastrowid
    log.info(f"Archive added: id={aid}")
    return aid


def add_files(archive_id: int, files: list[tuple[str, str, int, str | None]]):
    now = datetime.now().isoformat()
    sanitized = []
    for name, path, sz, chk in files:
        sanitized.append((_sanitize(name), _sanitize_path(path), sz, chk, now))
    rows = [(archive_id, *r) for r in sanitized]
    with _tx() as conn:
        conn.executemany(
            "INSERT INTO files (archive_id,name,path,size_bytes,checksum,created_at) VALUES (?,?,?,?,?,?)",
            rows,
        )
        conn.execute(
            "UPDATE archives SET file_count=(SELECT COUNT(*) FROM files WHERE archive_id=?), updated_at=? WHERE id=?",
            (archive_id, now, archive_id),
        )
    log.info(f"{len(rows)} files registered for archive id={archive_id}")


def get_archive(archive_id: int) -> ArchiveRecord | None:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM archives WHERE id=? AND is_deleted=0", (archive_id,)
    ).fetchone()
    return ArchiveRecord(**row) if row else None


def list_archives(deleted: bool = False, sort_by: str = "created_at",
                  sort_order: str = "DESC") -> list[ArchiveRecord]:
    sort_map = {
        "name": "name",
        "size_bytes": "size_bytes",
        "file_count": "file_count",
        "created_at": "created_at",
        "category": "category",
    }
    sort_col = sort_map.get(sort_by, "created_at")
    order = "ASC" if sort_order.upper() == "ASC" else "DESC"
    conn = _get_conn()
    rows = conn.execute(
        f"SELECT * FROM archives WHERE is_deleted=? ORDER BY {sort_col} {order}",
        (1 if deleted else 0,),
    ).fetchall()
    return [ArchiveRecord(**r) for r in rows]


def list_files(archive_id: int) -> list[FileRecord]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM files WHERE archive_id=? ORDER BY name", (archive_id,)
    ).fetchall()
    return [FileRecord(**r) for r in rows]


def search_files(query: str) -> list[tuple[ArchiveRecord, FileRecord]]:
    q = _sanitize(query)
    conn = _get_conn()
    rows = conn.execute(
        """SELECT a.*, f.id as fid, f.archive_id as faid, f.name as fname,
                  f.path as fpath, f.size_bytes as fsize, f.checksum as fchk,
                  f.created_at as fcreated
           FROM files f JOIN archives a ON a.id = f.archive_id
           WHERE a.is_deleted=0 AND (f.name LIKE ? OR f.path LIKE ?)
           ORDER BY f.name""",
        (f"%{q}%", f"%{q}%"),
    ).fetchall()
    results = []
    for r in rows:
        cat = r["category"] if "category" in r.keys() else ""
        a = ArchiveRecord(r["id"], r["name"], r["path"], r["format"],
                          r["size_bytes"], r["file_count"], r["checksum"],
                          r["signature"], r["notes"], cat,
                          r["created_at"], r["updated_at"], r["is_deleted"])
        f = FileRecord(r["fid"], r["faid"], r["fname"], r["fpath"],
                       r["fsize"], r["fchk"], r["fcreated"])
        results.append((a, f))
    return results


def search_archives(query: str, sort_by: str = "created_at",
                    sort_order: str = "DESC") -> list[ArchiveRecord]:
    q = _sanitize(query)
    sort_map = {
        "name": "a.name",
        "size_bytes": "a.size_bytes",
        "file_count": "a.file_count",
        "created_at": "a.created_at",
        "category": "a.category",
    }
    sort_col = sort_map.get(sort_by, "a.created_at")
    order = "ASC" if sort_order.upper() == "ASC" else "DESC"
    conn = _get_conn()
    rows = conn.execute(
        f"SELECT DISTINCT a.* FROM archives a "
        "LEFT JOIN files f ON f.archive_id = a.id "
        "WHERE a.is_deleted=0 AND (a.name LIKE ? OR a.notes LIKE ? "
        "OR f.name LIKE ? OR f.path LIKE ?) "
        f"ORDER BY {sort_col} {order}",
        (f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"),
    ).fetchall()
    return [ArchiveRecord(**r) for r in rows]


def list_categories() -> list[str]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT DISTINCT category FROM archives WHERE is_deleted=0 AND category != '' ORDER BY category"
    ).fetchall()
    return [r["category"] for r in rows]


def soft_delete_archive(archive_id: int) -> bool:
    now = datetime.now().isoformat()
    with _tx() as conn:
        cur = conn.execute(
            "UPDATE archives SET is_deleted=1, updated_at=? WHERE id=? AND is_deleted=0",
            (now, archive_id),
        )
        return cur.rowcount > 0


def update_archive_size(archive_id: int, size: int):
    now = datetime.now().isoformat()
    with _tx() as conn:
        conn.execute(
            "UPDATE archives SET size_bytes=?, updated_at=? WHERE id=?",
            (size, now, archive_id),
        )


def restore_archive(archive_id: int) -> bool:
    now = datetime.now().isoformat()
    with _tx() as conn:
        cur = conn.execute(
            "UPDATE archives SET is_deleted=0, updated_at=? WHERE id=? AND is_deleted=1",
            (now, archive_id),
        )
        return cur.rowcount > 0


def prune_archives() -> int:
    with _tx() as conn:
        cur = conn.execute("DELETE FROM archives WHERE is_deleted=1")
        count = cur.rowcount
    log.info(f"Pruned {count} archives")
    return count


def verify_signature(archive_id: int) -> bool:
    arch = get_archive(archive_id)
    if not arch or not arch.checksum or not arch.signature:
        return False
    expected = _sign(arch.checksum)
    return hmac.compare_digest(expected, arch.signature)


def export_db(dest_path: str):
    import shutil
    with _tx() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    src = cfg.DB_PATH
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dest))
    log.info(f"Database exported to {dest}")


def import_db(src_path: str):
    import shutil
    src = Path(src_path)
    if not src.exists():
        raise FileNotFoundError(f"Import file not found: {src_path}")
    # Validate it's a valid SQLite db
    try:
        test = sqlite3.connect(str(src))
        test.execute("SELECT COUNT(*) FROM archives").fetchone()
        test.close()
    except Exception as e:
        raise ValueError(f"Invalid database file: {e}")
    cfg.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(cfg.DB_PATH))
    if hasattr(_local, "conn") and _local.conn is not None:
        _local.conn.close()
        _local.conn = None
    log.info(f"Database imported from {src}")


def get_key_hash() -> str:
    h = hashlib.sha256(_get_or_create_key()).hexdigest()[:16]
    return h


# ─── Settings (key-value store) ──────────────────────────────────────────────


def set_setting(key: str, value: str):
    with _tx() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_setting(key: str, default: str | None = None) -> str | None:
    conn = _get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def get_all_settings() -> dict:
    conn = _get_conn()
    rows = conn.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
    return {r["key"]: r["value"] for r in rows}


# ─── License System ──────────────────────────────────────────────────────────

LICENSE_TYPES = {
    "5min":     {"name": "Trial 5 minutes",  "days": 0,     "minutes": 5},
    "7days":    {"name": "Trial 7 days",     "days": 7,     "minutes": 0},
    "monthly":  {"name": "Monthly",          "days": 30,    "minutes": 0},
    "yearly":   {"name": "Yearly",           "days": 365,   "minutes": 0},
    "lifetime": {"name": "Lifetime",         "days": 36500, "minutes": 0},
}


def _add_license_tables(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS licenses (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        code            TEXT UNIQUE NOT NULL,
        type            TEXT NOT NULL,
        created_at      TEXT NOT NULL,
        expires_at      TEXT,
        activated       INTEGER NOT NULL DEFAULT 0,
        hardware_id     TEXT,
        is_device_bound INTEGER NOT NULL DEFAULT 0,
        notes           TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS license_activations (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        license_code    TEXT NOT NULL,
        activation_date TEXT NOT NULL,
        hardware_id     TEXT,
        user_id         INTEGER
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        username        TEXT UNIQUE NOT NULL,
        password_hash   TEXT NOT NULL,
        role            TEXT NOT NULL DEFAULT 'user',
        full_name       TEXT,
        phone           TEXT,
        email           TEXT,
        created_at      TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS backups (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        filename        TEXT NOT NULL,
        path            TEXT NOT NULL,
        size_bytes      INTEGER NOT NULL DEFAULT 0,
        created_at      TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS settings (
        key             TEXT PRIMARY KEY,
        value           TEXT
    )""")
    # Migrations
    cols_usr = [r[1] for r in conn.execute("PRAGMA table_info(users)")]
    if "phone" not in cols_usr:
        conn.execute("ALTER TABLE users ADD COLUMN phone TEXT")
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
    if "password_salt" not in cols_usr:
        conn.execute("ALTER TABLE users ADD COLUMN password_salt TEXT DEFAULT NULL")


def get_hardware_id() -> str:
    import platform
    import uuid
    data = "|".join([platform.node(), platform.system(), platform.machine(), str(uuid.getnode())])
    h = hashlib.sha256(data.encode()).hexdigest()[:16].upper()
    return f"HW-{h}"


_LICENSE_SECRET: str | None = None
_LICENSE_SECRET_LOCK = threading.Lock()


def _get_license_secret() -> str:
    global _LICENSE_SECRET
    if _LICENSE_SECRET is not None:
        return _LICENSE_SECRET
    with _LICENSE_SECRET_LOCK:
        if _LICENSE_SECRET is not None:
            return _LICENSE_SECRET
        key = _get_or_create_key()
        _LICENSE_SECRET = hashlib.sha256(key + b"arch-license-v1").hexdigest()
        return _LICENSE_SECRET


def verify_license_code(code: str) -> tuple[bool, str]:
    try:
        parts = code.split("_")
        secret = _get_license_secret()
        if len(parts) == 4:
            hw_part, raw_part, type_part, sig_part = parts
            expected = hashlib.sha256((secret + hw_part + raw_part + type_part.lower()).encode()).hexdigest()[:6].upper()
            if sig_part != expected:
                return False, "Invalid signature"
            if type_part.lower() not in LICENSE_TYPES:
                return False, f"Unknown license type: {type_part}"
            return True, f"VALID — Device-Specific"
        elif len(parts) == 3:
            raw_part, type_part, sig_part = parts
            expected = hashlib.sha256((secret + raw_part + type_part.lower()).encode()).hexdigest()[:4].upper()
            if sig_part != expected:
                return False, "Invalid signature"
            if type_part.lower() not in LICENSE_TYPES:
                return False, f"Unknown license type: {type_part}"
            return True, f"VALID — General"
        else:
            return False, "Invalid license format"
    except Exception:
        return False, "Invalid license format"


def activate_license(code: str, hardware_id: str | None = None) -> tuple[bool, str]:
    valid, msg = verify_license_code(code)
    if not valid:
        return False, msg
    parts = code.split("_")
    license_type = parts[-2].lower() if len(parts) >= 3 else ""
    hw = hardware_id or get_hardware_id()
    lic_info = LICENSE_TYPES.get(license_type, {})
    now = datetime.now()
    expires = (now + timedelta(days=36500)).isoformat() if license_type == "lifetime" else (
        now + timedelta(days=lic_info.get("days", 0), minutes=lic_info.get("minutes", 0))
    ).isoformat()
    with _tx() as conn:
        row = conn.execute("SELECT * FROM licenses WHERE code=?", (code,)).fetchone()
        if row:
            conn.execute(
                "UPDATE licenses SET activated=1, hardware_id=?, expires_at=? WHERE id=?",
                (hw, expires, row["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO licenses (code,type,created_at,expires_at,activated,hardware_id,"
                "is_device_bound) VALUES (?,?,?,?,1,?,?)",
                (code, license_type, now.isoformat(), expires, hw,
                 1 if len(parts) == 4 else 0),
            )
        conn.execute(
            "INSERT INTO license_activations (license_code,activation_date,hardware_id) VALUES (?,?,?)",
            (code, now.isoformat(), hw),
        )
    return True, f"Activated — expires {expires}"


def check_license_status() -> tuple[bool, str, dict | None]:
    conn = _get_conn()
    lic = conn.execute("SELECT * FROM licenses WHERE activated=1 ORDER BY id DESC LIMIT 1").fetchone()
    if lic:
        try:
            expires_at = datetime.fromisoformat(lic["expires_at"])
        except Exception:
            return False, "Invalid expiry date", None
        now = datetime.now()
        if now > expires_at:
            return False, "License expired", {"expires_at": lic["expires_at"], "type": lic["type"], "remaining_days": 0}
        remaining = (expires_at - now).total_seconds()
        info = {
            "type": lic["type"],
            "expires_at": lic["expires_at"],
            "remaining_days": max(0, int(remaining // 86400)),
            "hardware_id": lic["hardware_id"],
            "is_device_bound": bool(lic["is_device_bound"]),
        }
        return True, "License valid", info

    trial = trial_guard.check_trial_status()
    if trial["status"] == "active":
        rem_sec = trial["remaining_seconds"] or 0
        info = {
            "type": trial["trial_type"],
            "expires_at": trial["expires_at"],
            "remaining_days": max(0, int(rem_sec // 86400)),
            "remaining_seconds": rem_sec,
            "mode": "trial",
        }
        return True, trial["message"], info

    if trial_guard.is_trial_reset_detected():
        return False, "Trial expired — reset detected. A valid license is required.", {
            "type": trial.get("trial_type"),
            "expires_at": trial.get("expires_at"),
            "remaining_days": 0,
            "mode": "trial_expired_reset",
        }

    if trial["status"] == "expired":
        return False, trial["message"], {
            "type": trial["trial_type"],
            "expires_at": trial["expires_at"],
            "remaining_days": 0,
            "mode": "trial_expired",
        }

    return False, "No active license or trial found", None


# ─── User System ─────────────────────────────────────────────────────────────

def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()


def add_user(username: str, password: str, role: str = "user", full_name: str = "") -> int | None:
    uname = _sanitize(username)
    salt = secrets.token_hex(16)
    pwh = _hash_password(password, salt)
    now = datetime.now().isoformat()
    with _tx() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users (username,password_hash,password_salt,role,full_name,created_at) VALUES (?,?,?,?,?,?)",
                (uname, pwh, salt, role, _sanitize(full_name), now),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


def authenticate_user(username: str, password: str) -> dict | None:
    uname = _sanitize(username)
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE username=?", (uname,),
    ).fetchone()
    if not row:
        return None
    try:
        salt = row["password_salt"] or ""
    except (KeyError, IndexError):
        salt = ""
    if salt:
        pwh = _hash_password(password, salt)
    else:
        pwh = hashlib.sha256(password.encode()).hexdigest()
    if not hmac.compare_digest(pwh, row["password_hash"]):
        return None
    if not salt:
        new_salt = secrets.token_hex(16)
        new_pwh = _hash_password(password, new_salt)
        try:
            conn.execute(
                "UPDATE users SET password_hash=?, password_salt=? WHERE id=?",
                (new_pwh, new_salt, row["id"]),
            )
        except Exception:
            pass
    return dict(row)


def list_users() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute("SELECT id,username,role,full_name,phone,email,created_at FROM users ORDER BY username").fetchall()
    return [dict(r) for r in rows]


def delete_user(user_id: int) -> bool:
    with _tx() as conn:
        cur = conn.execute("DELETE FROM users WHERE id=? AND role!='admin'", (user_id,))
        return cur.rowcount > 0


def update_user(user_id: int, username: str | None = None, role: str | None = None,
                full_name: str | None = None,
                phone: str | None = None, email: str | None = None) -> bool:
    with _tx() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            return False
        updates = {}
        if username is not None:
            updates["username"] = _sanitize(username)
        if role is not None:
            updates["role"] = role
        if full_name is not None:
            updates["full_name"] = _sanitize(full_name)
        if phone is not None:
            updates["phone"] = _sanitize(phone)
        if email is not None:
            updates["email"] = _sanitize(email)
        if not updates:
            return False
        sets = ", ".join(f"{k}=?" for k in updates)
        vals = list(updates.values()) + [user_id]
        conn.execute(f"UPDATE users SET {sets} WHERE id=?", vals)
        return True


def change_user_password(user_id: int, new_password: str) -> bool:
    if len(new_password) < 4:
        return False
    salt = secrets.token_hex(16)
    pwh = _hash_password(new_password, salt)
    with _tx() as conn:
        cur = conn.execute("UPDATE users SET password_hash=?, password_salt=? WHERE id=?", (pwh, salt, user_id))
        return cur.rowcount > 0


# ─── Backup System ───────────────────────────────────────────────────────────

def create_backup() -> str | None:
    from .config import BACKUP_DIR
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"arch_backup_{ts}.db"
    with _tx() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    import shutil
    shutil.copy2(str(cfg.DB_PATH), str(dest))
    with _tx() as conn:
        conn.execute(
            "INSERT INTO backups (filename,path,size_bytes,created_at) VALUES (?,?,?,?)",
            (dest.name, str(dest), dest.stat().st_size, datetime.now().isoformat()),
        )
    log.info(f"Backup created: {dest}")
    return str(dest)


def list_backups() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM backups ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def restore_backup(backup_id: int) -> str | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM backups WHERE id=?", (backup_id,)).fetchone()
    if not row:
        return None
    src = Path(row["path"])
    if not src.exists():
        return None
    import shutil
    shutil.copy2(str(src), str(cfg.DB_PATH))
    if hasattr(_local, "conn") and _local.conn is not None:
        _local.conn.close()
        _local.conn = None
    log.info(f"Backup restored: {src}")
    return str(src)
