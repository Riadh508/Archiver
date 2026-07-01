from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "arch.db"
LOG_PATH = DATA_DIR / "arch.log"
KEY_PATH = DATA_DIR / ".arch_key"

ARCHIVES_DIR = DATA_DIR / "archives"
BACKUP_DIR = DATA_DIR / "backups"

DEFAULT_FORMAT = "zip"
SUPPORTED_FORMATS = ("zip", "tar", "gztar", "bztar", "xztar")
