import importlib
import os
import socket
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TOOLS_DIR = BASE_DIR / "tools"
RUNTIME_DIR = BASE_DIR / "runtime"
PORT = 8080
REQUIRED_PACKAGES = ("fastapi", "pydantic", "uvicorn", "playwright")

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def ok(message: str) -> None:
    print(f"   [OK] {message}")


def info(message: str) -> None:
    print(f"   [INFO] {message}")


def warn(message: str) -> None:
    print(f"   [WARN] {message}")


def error(message: str) -> None:
    print(f"   [ERROR] {message}")


def check_python_runtime() -> int:
    print("-> Checking Python runtime...")
    ok(f"Interpreter: {sys.executable}")
    ok(f"Version: {sys.version.split()[0]}")
    if sys.version_info[:2] != (3, 10):
        warn("This project was packaged with Python 3.10; other versions are not fully validated")
    if os.name != "nt":
        error("This offline package currently targets Windows because runtime and tools are bundled as .exe")
        return 1
    return 0


def check_python_dependencies() -> int:
    print("-> Checking Python runtime dependencies...")
    import app  # noqa: F401

    failures = 0
    for package_name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(package_name)
            package_version = version(package_name)
            ok(f"{package_name}=={package_version}")
        except ImportError as exc:
            error(f"Missing dependency: {exc.name}")
            failures += 1
        except PackageNotFoundError:
            warn(f"Package metadata not found for {package_name}")
    return failures


def check_api_port() -> int:
    print("-> Checking API port 8080...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if sock.connect_ex(("127.0.0.1", PORT)) == 0:
            error(f"Port {PORT} is already in use")
            return 1
    ok(f"Port {PORT} is available")
    return 0


def _ensure_writable_dir(path: Path) -> int:
    path.mkdir(parents=True, exist_ok=True)
    probe_path = path / ".write_test.tmp"
    probe_path.write_text("ok", encoding="utf-8")
    probe_path.unlink()
    ok(f"Writable directory: {path.relative_to(BASE_DIR)}")
    return 0


def check_runtime_layout() -> int:
    print("-> Checking local runtime layout...")
    failures = 0

    runtime_python = RUNTIME_DIR / "python.exe"
    if runtime_python.exists():
        ok("Bundled runtime/python.exe exists")
    else:
        error("Missing runtime/python.exe")
        failures += 1

    for path in (DATA_DIR, TOOLS_DIR, BASE_DIR / "frontend", BASE_DIR / "app"):
        if path.exists():
            ok(f"Directory exists: {path.relative_to(BASE_DIR)}")
        else:
            error(f"Missing directory: {path.relative_to(BASE_DIR)}")
            failures += 1

    for writable_dir in (
        DATA_DIR,
        DATA_DIR / "basic_results",
        DATA_DIR / "nmap_results",
        DATA_DIR / "fscan_results",
        DATA_DIR / "nsfocus_results",
        DATA_DIR / "generated_reports",
    ):
        try:
            failures += _ensure_writable_dir(writable_dir)
        except Exception as exc:
            error(f"Directory is not writable: {writable_dir.relative_to(BASE_DIR)} ({exc})")
            failures += 1

    return failures


def check_tools() -> int:
    print("-> Checking bundled external tools...")
    failures = 0

    expected_paths = [
        TOOLS_DIR / "nmap" / "nmap.exe",
        TOOLS_DIR / "nmap" / "nmap-service-probes",
        TOOLS_DIR / "nmap" / "scripts" / "script.db",
        TOOLS_DIR / "fscan" / "fscan.exe",
    ]
    for path in expected_paths:
        if path.exists():
            ok(f"Found {path.relative_to(BASE_DIR)}")
        else:
            error(f"Missing {path.relative_to(BASE_DIR)}")
            failures += 1

    return failures


def check_playwright_browser() -> int:
    print("-> Checking Playwright browser bundle...")
    failures = 0
    browser_bins_dir = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", BASE_DIR / "browser_bins"))
    if browser_bins_dir.exists():
        ok(f"Browser cache path: {browser_bins_dir}")
    else:
        error(f"Browser cache path does not exist: {browser_bins_dir}")
        return 1

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        error(f"Playwright import failed: {exc}")
        return 1

    try:
        with sync_playwright() as playwright:
            executable_path = Path(playwright.chromium.executable_path)
            ok(f"Chromium executable: {executable_path}")
            if BASE_DIR not in executable_path.parents:
                warn("Playwright is not using the project-local browser cache; offline portability may be reduced")
    except Exception as exc:
        error(f"Unable to resolve bundled Chromium: {exc}")
        failures += 1

    return failures


def check_report_templates() -> int:
    print("-> Checking report template sources...")
    failures = 0
    try:
        from app.report_builder import TEMPLATE_FILES, TEMPLATE_SOURCE_DIRS
    except Exception as exc:
        error(f"Unable to import report builder: {exc}")
        return 1

    existing_dirs = [path for path in TEMPLATE_SOURCE_DIRS if path.exists()]
    if existing_dirs:
        for path in existing_dirs:
            ok(f"Template directory available: {path}")
    else:
        warn("No template directory is currently available; report generation features will fail until templates are copied")

    missing_files = []
    for filename in TEMPLATE_FILES.values():
        if any((root / filename).exists() for root in TEMPLATE_SOURCE_DIRS):
            continue
        missing_files.append(filename)

    if missing_files:
        warn(f"Missing {len(missing_files)} report template files")
        for filename in missing_files[:5]:
            warn(f"Template not found: {filename}")
        if len(missing_files) > 5:
            warn(f"...and {len(missing_files) - 5} more template files")
    else:
        ok("All report template files were found")

    return failures


def check_env_file() -> int:
    print("-> Checking optional project configuration...")
    dotenv_path = BASE_DIR / ".env"
    if dotenv_path.exists():
        ok("Local .env file exists")
    else:
        info("No .env file found; built-in defaults will be used")

    if os.environ.get("NSFOCUS_URL"):
        ok(f"NSFOCUS_URL is set to {os.environ['NSFOCUS_URL']}")
    else:
        info("NSFOCUS_URL is not set; NSFOCUS automation will use the built-in default target")

    return 0


def main() -> int:
    checks = [
        check_python_runtime,
        check_python_dependencies,
        check_api_port,
        check_runtime_layout,
        check_tools,
        check_playwright_browser,
        check_report_templates,
        check_env_file,
    ]

    failures = 0
    for check in checks:
        failures += check()

    print()
    if failures:
        error(f"Environment check failed with {failures} blocking issue(s)")
        return 1

    ok("Environment check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
