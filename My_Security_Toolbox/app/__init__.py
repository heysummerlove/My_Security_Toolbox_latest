import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DOTENV_PATH = BASE_DIR / ".env"
BROWSER_BINS_DIR = BASE_DIR / "browser_bins"


def _load_dotenv() -> None:
    if not DOTENV_PATH.exists():
        return

    for raw_line in DOTENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[key] = value


def _configure_playwright_browsers() -> None:
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return
    if BROWSER_BINS_DIR.exists():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSER_BINS_DIR)


_load_dotenv()
_configure_playwright_browsers()
