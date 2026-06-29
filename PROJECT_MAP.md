# PROJECT_MAP — Professional Archiving System (Secure Edition)

## [TECH_STACK]

| Component      | Version    | Notes                              |
|---------------|------------|------------------------------------|
| Python        | 3.12+      | stdlib + optional `cryptography`   |
| SQLite        | 3.45.3     | WAL mode, foreign keys             |
| unittest      | stdlib     | 51 web tests, 14 core tests        |

**Runtime deps:** zero (stdlib). Optional: `cryptography` for `lock`/`unlock`.

**Web UI ports:** 8080 (default), no extra deps — stdlib `http.server`.
**Web UI features:** Dashboard stats, archives CRUD + upload + verify signature, unified Settings page (license activation/verify, user add/delete, backup create/restore, DB export, prune, general settings).

**License generation:** external standalone tool `gen_license.py` (stdlib). Generates HMAC-signed codes compatible with arch's `verify_license_code()`. Supports device-bound licenses, JSON export, and shared secret from `data/.arch_key` or `--secret` argument.

## [SYSTEM_FLOW]

```
User (Browser)
  │
  ▼
web.py (ArchHandler — http.server)
  │
  ├── GET / → dashboard
  ├── GET /archives → list+upload
  ├── GET /settings → unified settings (license, users, backup, security, general)
  ├── POST /api/archives/upload
  ├── GET /api/archives → JSON
  ├── GET|POST /api/settings → settings CRUD
  ├── ... (license, user, backup, auth)
  └────┬──────────────────────┘
       │
       ▼
  __main__.py  (argparse dispatch, 16 commands, global error wrapper)
  │                              │
  ├── add      → cmd_add       ←┘ (both use core.py)
  ├── list     → cmd_list      → core.list_archives / detail (+ --json, signature status)
  ├── extract  → cmd_extract   → _safe_extract (zip-slip protected)
  ├── search   → cmd_search    → core.search_files (sanitized query)
  ├── remove   → cmd_remove    → core.soft_delete_archive
  ├── restore  → cmd_restore   → core.restore_archive (undelete)
  ├── verify   → cmd_verify    → HMAC check + SHA256 checksum compare
  ├── prune    → cmd_prune     → core.prune_archives (permanent delete)
  ├── export   → cmd_export    → copy SQLite db (WAL checkpointed)
  ├── import   → cmd_import    → validate + replace SQLite db
  ├── scan     → cmd_scan      → batch archive subdirs via cmd_add
  ├── lock     → cmd_lock      → Fernet (AES-128-CBC + HMAC) encryption
  ├── unlock   → cmd_unlock    → Fernet decryption with password
   ├── license  → cmd_license_* → activate / verify / status (generate: see gen_license.py)
  ├── user     → cmd_user_*    → add / list / delete (SHA256 password)
  └── backup   → cmd_backup_*  → create / list / restore (SQLite snapshots)
         │
         ▼
     core.py (SQLite CRUD, HMAC-SHA256 signing, input sanitization,
              license verification/activation, user auth, backup/restore)
         │
         ▼
    data/
    ├── arch.db    (SQLite — WAL journal, foreign keys)
    ├── arch.log   (async queue-based logging)
    ├── .arch_key  (32-byte HMAC key, chmod 600)
    ├── archives/  (archive files, optional .enc)
    └── backups/   (SQLite backup snapshots)
```

## [SECURITY_AUDIT]

| CVE | Issue | File | Status | Fix |
|-----|-------|------|--------|-----|
| CVE-001 | Zip slip — path traversal in extract | `ops.py` | ✅ FIXED | `_safe_extract_zip` / `_safe_extract_tar` validate each path |
| CVE-002 | SHA256 stored without integrity | `core.py` | ✅ FIXED | HMAC-SHA256 signed checksums with 32-byte key |
| CVE-003 | SQL injection via `search_files` | `core.py` | ✅ AUDITED | Parameterized queries — safe by design |
| CVE-004 | No input sanitization | `core.py` | ✅ FIXED | `_sanitize` strips nulls, truncates; `_sanitize_path` blocks `..` |
| CVE-005 | No encryption at rest | `ops.py` | ✅ FIXED | `lock`/`unlock` via Fernet (AES-128-CBC + HMAC) |
| CVE-006 | Insecure DB import | `core.py` | ✅ FIXED | Validates SQLite format before overwriting |
| CVE-007 | Path leakage in logs | `log.py` | ✅ FIXED | Paths sanitized in log output |

## [ARCHITECTURE]

```
E:\ho\arch\
├── arch/
│   ├── __init__.py      # Package version
│   ├── __main__.py      # CLI dispatch (argparse, 16 commands, error wrapper)
│   ├── core.py          # SQLite CRUD, HMAC signing, sanitization, key management,
│   │                   #   license verify/activate, user auth, backup/restore
│   ├── ops.py           # All CLI commands + zip-slip protection + encryption
│   ├── web.py           # Built-in web UI (stdlib http.server, no deps)
│   ├── log.py           # Queue-based async logging → stderr + file
│   └── config.py        # Paths, defaults, KEY_PATH, BACKUP_DIR
├── data/                # Auto-created runtime data
├── tests/
│   ├── test_core.py     # 14 feature tests (+ settings, users, changepw)
│   ├── test_ops.py      # 14 feature tests
│   ├── test_security.py # 11 security tests (zip slip, HMAC, sanitize, import)
│   ├── test_license.py  # 16 tests (license, user, backup)
│   ├── test_web.py      # 50 tests (endpoints, pages, upload, settings, search, categories, sort)
│   └── run_all.py       # Sequential test runner with temp directories
├── gen_license.py       # Standalone license generator/verifier (stdlib, external tool)
└── PROJECT_MAP.md
```

## [ORPHANS & PENDING]

- **`arch sign` standalone** — currently HMAC signing is automatic on `add`; could add explicit `sign <id>` command
- **`arch audit`** — full audit log of all operations with HMAC chain
- **Hardware-backed keys** — TPM/HSM integration for key storage
- **Scheduled auto-backup** — background timer for periodic backups (from HotelSystem TaskManager)
- **License trial guard** — hidden `.arch_trial` marker file with HMAC signature (from HotelSystem TrialGuard)
- **Registry persistence for trial/guard** — Windows Registry backup for guard data (from HotelSystem)
- **Web UI auth for API endpoints** — currently only HTML pages check cookie auth; API POST endpoints (backup, user add, license activate) are unauthenticated
- **Web UI `arch web` CLI command** — no `__main__.py` subcommand to start web server; must use `python -c "from arch.web import serve; serve()"`
- **Support tar/other formats in web upload** — currently only `.zip` accepted via upload form
- **RSA-4096 license signing** — from sandsoft-final-v5; requires `cryptography` package (optional)
- **Pre-existing security test failures (3)** — `test_key_file_created_with_restricted_perms` (key not created on `init_db` alone), `test_hmac_detects_tampered_checksum` (thread-local connection issue), `test_verify_command_fails_with_tampered_data` (verify passes after tamper)
- **Pre-existing core test isolation failure (4)** — `test_search_files`, user CRUD tests, password change tests fail when run alongside other tests due to shared DB

### ✅ Recently Added — Wave 2 (Search + Categories + Sort)

| Feature | Source | Status |
|---------|--------|--------|
| Archive search in web UI (`/archives?q=...`) | HotelSystem `templates/main/search.html` | ✅ 54 tests pass |
| Archive categories/folders | HotelSystem (folder concept) | ✅ `category` column + upload form + create-new |
| Sort archives by name/size/files/date/category | HotelSystem (sort concept) | ✅ Sort UI + API params |
| CLI `--category` / `-c` for `arch add` | — | ✅ `cmd_add` accepts `category=` |

### ✅ Recently Added (from HotelSystem v2.1.0)

| Feature | Source | Status |
|---------|--------|--------|
| Unified Settings page (`/settings`) | HotelSystem `routes/settings.py` | ✅ 51 web tests pass |
| User update / change password | HotelSystem `routes/users.py` | ✅ `update_user()`, `change_user_password()` |
| `phone` / `email` fields on users | HotelSystem `routes/users.py` | ✅ Columns added via migration |
| Settings key-value store | HotelSystem `db.py` | ✅ `settings` table + `set_setting()`/`get_setting()` |
| Backup display in settings | HotelSystem `templates/settings/index.html` | ✅ Integrated into `/settings` page |
| **Search archives** in web UI | HotelSystem `templates/main/search.html` | ✅ Search box + `/api/archives/search` endpoint |
| **Categories/folders** for archives | HotelSystem (folder concept) | ✅ `category` column, upload form selector, create-new |
| **Sort/order** archives | HotelSystem (sort concept) | ✅ Sort by name/size/files/date/category, ASC/DESC |
| CLI `--category` flag for `arch add` | — | ✅ `ops.cmd_add` accepts `category=` param |

### ❌ Removed in Wave 3

| Feature | Reason | Details |
|---------|--------|---------|
| NTP time verification | Slowness on Windows | Removed `get_ntp_time()`, `verify_time_integrity()`, NTP constants from `core.py`. No more DNS/socket hangs. |
| License max_activations | User request (external generation) | Removed `max_activations`/`activation_count` from `activate_license()`, `licenses` table, web UI. |
| User `can_generate_license` permission | User request (only external tool generates) | Removed column/users table, checkbox from web UI, `update_user()` parameter. |
| Security events display | User request (simplify settings) | Removed `log_security_event()`, `get_security_events()`, security card from settings page. |
| `generate_license_code()` in core.py | Moved to external tool | Replaced by `gen_license.py` standalone script. |

### ✅ Added in Wave 4

| Feature | Details |
|---------|---------|
| Upload performance | SHA256 + zip scan from memory (no disk I/O for validate/scan). `init_db()` removed from API hot paths (called once at server start). |
| Accept any file type | Non-zip files (images, PDFs, etc.) are accepted and registered as archives with format from extension. Zip files still scanned for file listing. |
| `gen_license.py` standalone tool | Generate/verify/export license codes with shared key from `data/.arch_key` or `--secret` |
| Archive verify in web UI | Verify HMAC signature button on archive detail page |
| Database export from web UI | Download SQLite DB from advanced tools card in settings |
| Prune deleted archives from web UI | Permanently delete all soft-deleted archives with confirmation |
| Restore soft-deleted archives from web UI | REST API endpoint `/api/archives/<id>/restore` |
| Currency field removed | Removed from general settings card (field and API parameter) |

### ✅ Fixed in Wave 5 (System Audit & Bug Fixes)

| Fix | Details |
|-----|---------|
| `_get_conn()` double-connect | Removed wasteful second connection — was creating 2 connections per thread, now 1 |
| Unused imports removed | `import time`, `from contextlib import suppress` — dead code after NTP removal |
| Unused `_extract_hw_part` removed | Dead function after `generate_license_code` moved to `gen_license.py` |
| `core.init_db()` in API routes | Added to `do_GET`/`do_POST` top — ensures DB initialized even without `serve()` |
| `list_users()` now returns phone/email | Previously only returned id/username/role/full_name/created_at |
| Users page shows phone/email | Added columns to table + input fields in add form |
| `/api/users/add` accepts phone/email | New fields sent from UI, stored via `update_user()` after creation |
