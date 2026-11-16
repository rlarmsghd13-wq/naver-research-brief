import os
import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
DATA_DIR = os.path.join(DOCS_DIR, "data")
ARCHIVE_DIR = os.path.join(DATA_DIR, "archive")
CHARTS_DIR = os.path.join(DOCS_DIR, "assets", "charts")
TMP_PDF_DIR = os.path.join(BASE_DIR, ".tmp_pdfs")

KST = datetime.timezone(datetime.timedelta(hours=9))


def load_dotenv():
    """프로젝트 루트의 .env 파일을 읽어 환경변수로 등록 (기존 env 우선)."""
    env_path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


load_dotenv()


def get_kst_now():
    return datetime.datetime.now(KST)


def get_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()
