# Offline Deployment Guide

## Scope

This package is currently prepared for `Windows x64` offline deployment.
The bundled runtime, `nmap`, and `fscan` are all Windows executables.

## What To Deliver

Copy the whole `My_Security_Toolbox` directory, then confirm these paths are present on the target machine:

- `app/`
- `frontend/`
- `runtime/`
- `tools/nmap/`
- `tools/fscan/`
- `browser_bins/`
- `data/`
- `run.bat`
- `env_check.py`

## What Must Be Checked Before Handover

Run:

```powershell
cd E:\My_Security_Toolbox\My_Security_Toolbox
.\runtime\python.exe env_check.py
```

The check now validates:

- bundled Python runtime
- required Python packages
- local port `8080`
- writable `data/` subdirectories
- bundled `nmap` and `fscan`
- Playwright Chromium from the project-local browser cache
- report template availability
- optional `.env` configuration

## Minimal Delivery Rules

- Keep `runtime/`, `tools/`, and `browser_bins/` together with the project.
- Do not rely on internet access for Playwright browser download.
- Do not rely on system Python.
- Do not rely on `%LOCALAPPDATA%\ms-playwright` on the target machine.

## Configuration

The application now auto-loads a local `.env` file if present.
You can copy `.env.example` to `.env` and adjust values before delivery.

Important variables:

- `MST_ALLOWED_ORIGINS`
- `MST_DEFAULT_USERNAME`
- `NSFOCUS_URL`
- `NSFOCUS_USERNAME`
- `NSFOCUS_PASSWORD`
- `NSFOCUS_HEADLESS`
- `PLAYWRIGHT_BROWSERS_PATH`
- `MST_TEMPLATE_DIRS`

## Report Templates

Report generation depends on template files.
Recommended offline layout:

- Put the official template files under `templates/`
- Or point `MST_TEMPLATE_DIRS` to the template directory

The app will search in this order:

1. `MST_TEMPLATE_DIRS`
2. `./templates`
3. `./data/template_extract`
4. legacy absolute paths kept for backward compatibility

If templates are missing, scanning and basic data features can still run, but report generation will fail.

## Data Strategy

Choose one delivery mode before migration testing:

1. Fresh deployment
   Delete or ignore the old `data/toolbox.db` and let the app create tables on first start.
2. Data-carrying deployment
   Deliver `data/toolbox.db` together with the package and verify old data opens correctly.

Do not mix test data and formal delivery data unless that is intentional.

## Recommended Minimal Test Flow

1. Run `.\runtime\python.exe env_check.py`
2. Run `run.bat`
3. Open `http://127.0.0.1:8080/`
4. Verify login
5. Verify one basic task such as `ping`
6. Verify one `nmap` task
7. Verify one `fscan` task
8. If used in production, verify NSFOCUS automation
9. If used in production, verify report generation

## Files Usually Not Needed In A Clean Delivery Copy

You can exclude these if you are packaging a clean handoff bundle:

- `.idea/`
- `app/__pycache__/`
- existing debug snapshots under `data/nsfocus_debug/`
- historical outputs under `data/*_results/`
- temporary generated exports under `data/generated_reports/`

Keep them only if you intentionally want to preserve test history.
