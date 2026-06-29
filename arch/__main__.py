"""CLI entry point — argparse dispatch"""

import argparse
import sys

from . import ops, web
from .config import SUPPORTED_FORMATS


def main():
    parser = argparse.ArgumentParser(
        prog="arch",
        description="Professional Archiving System (secure edition)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # add
    p_add = sub.add_parser("add", help="Add file(s)/dir(s) to archive database")
    p_add.add_argument("paths", nargs="+", help="Files or directories to archive")
    p_add.add_argument("--format", "-f", default=None, choices=SUPPORTED_FORMATS,
                       help="Archive format (default: zip)")
    p_add.add_argument("--name", "-n", help="Archive name (default: source basename)")
    p_add.add_argument("--notes", "-m", default="", help="Notes for this archive")
    p_add.add_argument("--glob", "-g", help="Glob pattern to filter files (e.g. '*.txt')")
    p_add.add_argument("--level", type=int, choices=range(0, 10),
                       help="Compression level 0-9 (format-dependent)")
    p_add.add_argument("--category", "-c", default="", help="Category/folder for this archive")

    # list
    p_list = sub.add_parser("list", help="List archives or archive contents")
    p_list.add_argument("id", nargs="?", type=int, help="Archive ID to inspect")
    p_list.add_argument("--json", action="store_true", help="Output as JSON")

    # extract
    p_extract = sub.add_parser("extract", help="Extract an archive (zip-slip protected)")
    p_extract.add_argument("id", type=int, help="Archive ID")
    p_extract.add_argument("output", nargs="?", help="Output directory")

    # search
    p_search = sub.add_parser("search", help="Search files in archives")
    p_search.add_argument("query", help="Search term")

    # remove
    p_remove = sub.add_parser("remove", help="Soft-delete an archive")
    p_remove.add_argument("id", type=int, help="Archive ID")

    # verify
    p_verify = sub.add_parser("verify", help="Verify archive integrity (checksum + HMAC)")
    p_verify.add_argument("id", type=int, help="Archive ID")

    # restore
    p_restore = sub.add_parser("restore", help="Restore a soft-deleted archive")
    p_restore.add_argument("id", type=int, help="Archive ID")

    # prune
    sub.add_parser("prune", help="Permanently delete all soft-deleted archives")

    # export
    p_export = sub.add_parser("export", help="Export SQLite database to a file")
    p_export.add_argument("dest", help="Destination path")

    # import
    p_import = sub.add_parser("import", help="Import SQLite database from a file")
    p_import.add_argument("src", help="Source path")

    # scan
    p_scan = sub.add_parser("scan", help="Archive each subdirectory in a folder")
    p_scan.add_argument("dir", help="Directory containing subfolders to archive")
    p_scan.add_argument("--format", "-f", default=None, choices=SUPPORTED_FORMATS,
                       help="Archive format (default: zip)")
    p_scan.add_argument("--glob", "-g", help="Glob pattern to filter files")
    p_scan.add_argument("--notes", "-m", default="", help="Notes for each archive")

    # lock (encrypt)
    p_lock = sub.add_parser("lock", help="Encrypt an archive with a password")
    p_lock.add_argument("id", type=int, help="Archive ID")
    p_lock.add_argument("password", help="Encryption password")

    # unlock (decrypt)
    p_unlock = sub.add_parser("unlock", help="Decrypt an archive with a password")
    p_unlock.add_argument("id", type=int, help="Archive ID")
    p_unlock.add_argument("password", help="Decryption password")
    p_unlock.add_argument("output", nargs="?", help="Output path (default: original ext)")

    # license
    p_lic = sub.add_parser("license", help="License management")
    lic_sub = p_lic.add_subparsers(dest="license_cmd", required=True)
    p_lic_gen = lic_sub.add_parser("generate", help="Generate a license code")
    p_lic_gen.add_argument("type", choices=["5min","7days","monthly","yearly","lifetime"], help="License type")
    p_lic_gen.add_argument("--hardware", "-hw", help="Hardware ID for device-specific license")
    p_lic_gen.add_argument("--device-bound", action="store_true", help="Generate device-specific license")
    p_lic_gen.add_argument("--count", "-c", type=int, default=1, help="Number of licenses")
    p_lic_act = lic_sub.add_parser("activate", help="Activate a license code")
    p_lic_act.add_argument("code", help="License code")
    p_lic_vfy = lic_sub.add_parser("verify", help="Verify a license code")
    p_lic_vfy.add_argument("code", help="License code")
    lic_sub.add_parser("status", help="Check active license status")

    # user
    p_user = sub.add_parser("user", help="User management")
    user_sub = p_user.add_subparsers(dest="user_cmd", required=True)
    p_user_add = user_sub.add_parser("add", help="Add a user")
    p_user_add.add_argument("username", help="Username")
    p_user_add.add_argument("password", help="Password")
    p_user_add.add_argument("--role", default="user", choices=["admin","user"], help="Role")
    p_user_add.add_argument("--full-name", help="Full name")
    user_sub.add_parser("list", help="List users")
    p_user_del = user_sub.add_parser("delete", help="Delete a user")
    p_user_del.add_argument("id", type=int, help="User ID")

    # backup
    p_bak = sub.add_parser("backup", help="Backup management")
    bak_sub = p_bak.add_subparsers(dest="backup_cmd", required=True)
    bak_sub.add_parser("create", help="Create a database backup")
    bak_sub.add_parser("list", help="List backups")
    p_bak_rest = bak_sub.add_parser("restore", help="Restore from a backup")
    p_bak_rest.add_argument("id", type=int, help="Backup ID")

    # web
    p_web = sub.add_parser("web", help="Start web UI")
    p_web.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    p_web.add_argument("--port", "-p", type=int, default=8080, help="Port (default: 8080)")

    args = parser.parse_args()

    try:
        match args.command:
            case "add":
                ops.cmd_add(args.paths, args.format, args.name,
                            args.notes, args.glob, args.level, args.category)
            case "list":
                ops.cmd_list(args.id, json=args.json)
            case "extract":
                ops.cmd_extract(args.id, args.output)
            case "search":
                ops.cmd_search(args.query)
            case "remove":
                ops.cmd_remove(args.id)
            case "verify":
                ops.cmd_verify(args.id)
            case "restore":
                ops.cmd_restore(args.id)
            case "prune":
                ops.cmd_prune()
            case "export":
                ops.cmd_export(args.dest)
            case "import":
                ops.cmd_import(args.src)
            case "scan":
                ops.cmd_scan(args.dir, args.format, args.glob, args.notes)
            case "lock":
                ops.cmd_lock(args.id, args.password)
            case "unlock":
                ops.cmd_unlock(args.id, args.password, args.output)
            case "license":
                match args.license_cmd:
                    case "generate":
                        ops.cmd_license_generate(args.type, args.hardware, args.device_bound, args.count)
                    case "activate":
                        ops.cmd_license_activate(args.code)
                    case "verify":
                        ops.cmd_license_verify(args.code)
                    case "status":
                        ops.cmd_license_status()
            case "user":
                match args.user_cmd:
                    case "add":
                        ops.cmd_user_add(args.username, args.password, args.role, args.full_name or "")
                    case "list":
                        ops.cmd_user_list()
                    case "delete":
                        ops.cmd_user_delete(args.id)
            case "backup":
                match args.backup_cmd:
                    case "create":
                        ops.cmd_backup()
                    case "list":
                        ops.cmd_backup_list()
                    case "restore":
                        ops.cmd_backup_restore(args.id)
            case "web":
                web.serve(host=args.host, port=args.port)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
