import os
import time
from datetime import datetime
from urllib.parse import urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DEBUG_DIR = os.path.join(BASE_DIR, "data", "nsfocus_debug")
NSFOCUS_REPORT_DIR = os.path.join(BASE_DIR, "data", "nsfocus_reports")

NSFOCUS_URL = os.environ.get("NSFOCUS_URL", "https://192.168.193.10/")
NSFOCUS_USERNAME = os.environ.get("NSFOCUS_USERNAME", "admin")
NSFOCUS_PASSWORD = os.environ.get("NSFOCUS_PASSWORD", "Nsfocus@123")
NSFOCUS_HEADLESS = os.environ.get("NSFOCUS_HEADLESS", "false").lower() == "true"


def ensure_debug_dir():
    os.makedirs(DEBUG_DIR, exist_ok=True)


def ensure_report_dir():
    os.makedirs(NSFOCUS_REPORT_DIR, exist_ok=True)


def debug_file(prefix: str, suffix: str) -> str:
    ensure_debug_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(DEBUG_DIR, f"{prefix}_{timestamp}.{suffix}")


def write_log(message: str):
    ensure_debug_dir()
    log_path = os.path.join(DEBUG_DIR, "run.log")
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {message}"
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(message)


def snapshot_step(page, name: str):
    save_debug_artifacts(page, name)
    export_visible_controls(page, name)


def save_debug_artifacts(page, prefix: str):
    png_path = debug_file(prefix, "png")
    html_path = debug_file(prefix, "html")
    page.screenshot(path=png_path, full_page=True)
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(page.content())
    write_log(f"[*] Saved screenshot: {png_path}")
    write_log(f"[*] Saved page snapshot: {html_path}")


def export_visible_controls(scope, prefix: str):
    txt_path = debug_file(prefix + "_controls", "txt")
    buttons = scope.locator(
        "button, [role='button'], a, .el-button, input[type='button'], input[type='submit']"
    ).all_inner_texts()
    inputs = scope.locator("input, textarea, select").evaluate_all(
        """
        elements => elements.map(el => ({
            tag: el.tagName,
            type: el.getAttribute('type') || '',
            name: el.getAttribute('name') || '',
            id: el.getAttribute('id') || '',
            placeholder: el.getAttribute('placeholder') || '',
            value: el.value || ''
        }))
        """
    )
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write("[Buttons]\n")
        for text in buttons:
            text = " ".join(text.split())
            if text:
                fh.write(text + "\n")
        fh.write("\n[Inputs]\n")
        for item in inputs:
            fh.write(
                f"{item['tag']} type={item['type']} name={item['name']} id={item['id']} "
                f"placeholder={item['placeholder']} value={item['value']}\n"
            )
    write_log(f"[*] Saved control list: {txt_path}")


def get_main_frame(page):
    frame = page.frame(name="mainFrame")
    if frame is None:
        raise RuntimeError("mainFrame iframe not found")
    return frame


def export_frame_snapshot(page, prefix: str):
    frame = get_main_frame(page)
    html_path = debug_file(prefix + "_frame", "html")
    txt_path = debug_file(prefix + "_frame_url", "txt")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(frame.content())
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write(frame.url)
    write_log(f"[*] Saved frame snapshot: {html_path}")
    write_log(f"[*] Saved frame URL: {txt_path}")
    export_visible_controls(frame, prefix + "_frame")


def click_first_visible(scope, candidates, timeout_ms=5000) -> bool:
    for candidate in candidates:
        locator = scope.locator(candidate).first
        try:
            locator.wait_for(state="visible", timeout=timeout_ms)
            locator.click()
            write_log(f"[*] Clicked element: {candidate}")
            return True
        except Exception:
            continue
    return False


def fill_first_visible(scope, selectors, value, timeout_ms=5000) -> bool:
    for selector in selectors:
        locator = scope.locator(selector).first
        try:
            locator.wait_for(state="visible", timeout=timeout_ms)
            locator.fill(value)
            write_log(f"[*] Filled input: {selector}")
            return True
        except Exception:
            continue
    return False


def normalize_web_target(target: str) -> str:
    value = (target or "").strip()
    if not value:
        raise RuntimeError("target is empty")
    if "://" not in value:
        value = f"http://{value}"
    return value


def fill_task_name(page, task_name):
    if not task_name:
        return
    frame = get_main_frame(page)
    selectors = [
        "input#task_name",
        "input[name='task_name']",
        "input[placeholder*='任务']",
    ]
    if fill_first_visible(frame, selectors, task_name, timeout_ms=5000):
        page.wait_for_timeout(500)
        snapshot_step(page, "step_04_fill_task_name")
        export_frame_snapshot(page, "step_04_fill_task_name")
        return
    raise RuntimeError("task name input not found")


def enable_all_report_options(page):
    frame = get_main_frame(page)
    frame.evaluate(
        """
        () => {
            const setChecked = (selector) => {
                const el = document.querySelector(selector);
                if (!el) return;
                el.checked = true;
                el.dispatchEvent(new Event('click', { bubbles: true }));
            };
            ['#report_type_html', '#report_type_doc', '#report_type_xls', '#summarizeReport', '#oneSiteReport']
                .forEach(setChecked);
            const autoExport = document.querySelector('#auto_export');
            if (autoExport) {
                autoExport.checked = true;
                autoExport.dispatchEvent(new Event('click', { bubbles: true }));
            }
            const table = document.querySelector('#sendReport_email_table');
            if (table) {
                table.style.display = '';
            }
        }
        """
    )
    page.wait_for_timeout(500)
    snapshot_step(page, "step_05_enable_report_options")
    export_frame_snapshot(page, "step_05_enable_report_options")


def capture_progress(page, prefix: str):
    try:
        export_frame_snapshot(page, prefix)
    except Exception as exc:
        write_log(f"[-] Failed to export frame snapshot: {exc}")
    try:
        snapshot_step(page, prefix)
    except Exception as exc:
        write_log(f"[-] Failed to export page snapshot: {exc}")


def wait_for_post_login(page, timeout_ms=15000):
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        try:
            if "/accounts/login" not in page.url:
                frame = page.frame(name="mainFrame")
                if frame is not None:
                    write_log("[+] Post-login page is ready: mainFrame found")
                    return
                if page.locator("a[href*='/accounts/logout/']").count() > 0:
                    write_log("[+] Post-login page is ready: logout link found")
                    return
        except Exception:
            pass
        page.wait_for_timeout(1000)
    raise RuntimeError("post-login main frame was not detected")


def login(page):
    write_log(f"[*] Opening scanner: {NSFOCUS_URL}")
    page.goto(NSFOCUS_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    snapshot_step(page, "step_01_open_login")

    username_selectors = [
        "input[name='username']",
        "input[name='userName']",
        "input[id='username']",
        "input[type='text']",
    ]
    password_selectors = [
        "input[name='password']",
        "input[id='password']",
        "input[type='password']",
    ]
    login_button_candidates = [
        "input.submit",
        "#loginForm input[type='button']",
        "button:has-text('登录')",
        "text=登录",
        ".login-btn",
        ".el-button--primary",
    ]

    if not fill_first_visible(page, username_selectors, NSFOCUS_USERNAME):
        raise RuntimeError("username input not found")
    if not fill_first_visible(page, password_selectors, NSFOCUS_PASSWORD):
        raise RuntimeError("password input not found")
    clicked = click_first_visible(page, login_button_candidates)
    if not clicked:
        try:
            page.evaluate("submitFormEncrypt()")
            write_log("[*] Triggered submitFormEncrypt()")
            clicked = True
        except Exception:
            pass
    if not clicked:
        raise RuntimeError("login button not found")

    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    wait_for_post_login(page)
    snapshot_step(page, "step_02_after_login")
    write_log("[+] Login successful")


def open_task_creation(page):
    frame = get_main_frame(page)
    task_url = NSFOCUS_URL.rstrip("/") + "/task/index/8"
    write_log(f"[*] Opening web scan task page: {task_url}")
    frame.goto(task_url, wait_until="domcontentloaded", timeout=30000)
    try:
        frame.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    page.wait_for_timeout(1000)
    snapshot_step(page, "step_03_open_task_entry")
    export_frame_snapshot(page, "step_03_open_task_entry")


def fill_target(page, target):
    frame = get_main_frame(page)
    normalized_target = normalize_web_target(target)
    target_selectors = [
        "textarea#task_target",
        "textarea[name='task_target']",
        "textarea#ipList",
        "textarea[name='ipList']",
        "textarea",
        "input[type='text']",
    ]
    if fill_first_visible(frame, target_selectors, normalized_target, timeout_ms=5000):
        try:
            frame.locator("textarea#task_target, textarea#ipList").first.blur()
        except Exception:
            pass
        try:
            frame.evaluate(
                """
                () => {
                    if (typeof web_check_tasktarget === 'function') {
                        web_check_tasktarget();
                        return;
                    }
                    if (typeof valTargets === 'function') {
                        valTargets();
                    }
                    const btn = document.querySelector('#submitButton');
                    if (btn) {
                        btn.disabled = false;
                    }
                }
                """
            )
            write_log("[*] Triggered target validation and attempted to enable submit button")
        except Exception:
            pass
        page.wait_for_timeout(4000)
        snapshot_step(page, "step_04_fill_target")
        export_frame_snapshot(page, "step_04_fill_target")
        return normalized_target
    raise RuntimeError("target input not found")


def submit_task(page):
    frame = get_main_frame(page)
    submit_candidates = [
        "#submitButton",
        "input#submitButton",
        "button:has-text('确定')",
        "button:has-text('提交')",
        ".el-button--primary",
    ]

    try:
        frame.evaluate(
            """
            () => {
                if (typeof webscan_submit === 'function') {
                    webscan_submit();
                    return;
                }
                const btn = document.querySelector('#submitButton');
                if (btn) {
                    btn.disabled = false;
                    btn.click();
                    return;
                }
                if (typeof vulTaskSubmit === 'function') {
                    vulTaskSubmit();
                }
            }
            """
        )
        write_log("[*] Triggered submission via page script")
        page.wait_for_timeout(3000)
        snapshot_step(page, "step_05_submit_task")
        export_frame_snapshot(page, "step_05_submit_task")
        return
    except Exception:
        pass
    if click_first_visible(frame, submit_candidates, timeout_ms=4000):
        snapshot_step(page, "step_05_submit_task")
        export_frame_snapshot(page, "step_05_submit_task")
        return
    raise RuntimeError("submit button not found")


def wait_for_task_progress(page):
    frame = get_main_frame(page)
    deadline = time.time() + 30
    while time.time() < deadline:
        current_url = frame.url
        if "/list/getProcess/id/" in current_url:
            write_log(f"[+] Progress page reached: {current_url}")
            capture_progress(page, "step_06_progress_page")
            return current_url
        try:
            if frame.locator("text=任务列表").count() > 0 or frame.locator("text=扫描进度").count() > 0:
                write_log(f"[+] Task-related page reached: {current_url}")
                capture_progress(page, "step_06_progress_page")
                return current_url
        except Exception:
            pass
        page.wait_for_timeout(1000)
    write_log(f"[*] No progress page redirect after submission, frame URL: {frame.url}")
    capture_progress(page, "step_06_progress_wait")
    return ""


def get_submit_validation_error(page) -> str:
    frame = get_main_frame(page)
    selectors = [
        "#task_target_error",
        "#task_name_error",
        "#dispatchLevel_error",
        "#report_type_error",
        "#auto_export_validate",
        "#proxy_conf_error",
        "#email_address_error",
    ]
    for selector in selectors:
        try:
            locator = frame.locator(selector).first
            if locator.count() <= 0:
                continue
            text = " ".join(locator.inner_text().split()).strip()
            style = (locator.get_attribute("style") or "").replace(" ", "").lower()
            hidden = "display:none" in style
            if text and not hidden:
                return text
        except Exception:
            continue
    return ""


def open_report_list(page):
    frame = get_main_frame(page)
    report_url = NSFOCUS_URL.rstrip("/") + "/report/list/"
    write_log(f"[*] Opening report list page: {report_url}")
    frame.goto(report_url, wait_until="domcontentloaded", timeout=30000)
    try:
        frame.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(1500)
    snapshot_step(page, "step_07_open_report_list")
    export_frame_snapshot(page, "step_07_open_report_list")
    return frame


def _choose_report_link(frame, preferred_types=None):
    preferred_types = preferred_types or ("html", "doc", "xls", "pdf")
    for report_type in preferred_types:
        locator = frame.locator(f"a[href*='/report/download/'][href*='/type/{report_type}/']").first
        try:
            if locator.count() > 0:
                href = locator.get_attribute("href")
                if href:
                    return urljoin(NSFOCUS_URL, href), report_type
        except Exception:
            continue
    return "", ""


def download_latest_report(page, task_name=""):
    ensure_report_dir()
    frame = open_report_list(page)

    report_url, report_type = _choose_report_link(frame)
    if not report_url:
        raise RuntimeError("downloadable report link not found")

    write_log(f"[*] Preparing to download latest report: {report_url}")
    with page.expect_download(timeout=30000) as download_info:
        try:
            page.goto(report_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            if "Download is starting" not in str(exc):
                raise
    download = download_info.value

    suggested_name = download.suggested_filename or f"nsfocus_report.{report_type or 'dat'}"
    safe_task_name = "".join(
        ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in (task_name or "").strip()
    ).strip("_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_name = f"{safe_task_name}_{timestamp}_{suggested_name}" if safe_task_name else f"{timestamp}_{suggested_name}"
    final_path = os.path.join(NSFOCUS_REPORT_DIR, final_name)
    download.save_as(final_path)
    write_log(f"[+] Latest report downloaded: {final_path}")
    return final_path


def auto_submit_task(target_ip, task_name=""):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=NSFOCUS_HEADLESS)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        page.set_default_timeout(8000)

        try:
            write_log(f"[*] Preparing web scan submission for target: {target_ip}")
            login(page)
            open_task_creation(page)
            normalized_target = fill_target(page, target_ip)
            if task_name:
                fill_task_name(page, task_name)
            enable_all_report_options(page)
            submit_task(page)
            progress_url = wait_for_task_progress(page)
            if not progress_url:
                error_message = get_submit_validation_error(page)
                if error_message:
                    raise RuntimeError(f"task submission rejected: {error_message}")
                raise RuntimeError("task submission did not reach the progress page")
            snapshot_step(page, "step_06_submit_success")
            export_frame_snapshot(page, "step_06_submit_success")
            write_log(f"[+] Target {normalized_target} was submitted successfully, progress page: {progress_url}")
        except PlaywrightTimeoutError as exc:
            write_log(f"[-] Page timeout: {exc}")
            snapshot_step(page, "timeout_error")
            export_frame_snapshot(page, "timeout_error")
            raise
        except Exception as exc:
            write_log(f"[-] Automation failed: {exc}")
            snapshot_step(page, "submit_error")
            export_frame_snapshot(page, "submit_error")
            raise
        finally:
            browser.close()


def download_latest_report_only(task_name=""):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=NSFOCUS_HEADLESS)
        context = browser.new_context(ignore_https_errors=True, accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(10000)

        try:
            write_log("[*] Preparing to download the latest web scan report")
            login(page)
            report_path = download_latest_report(page, task_name=task_name)
            print(report_path)
            return report_path
        finally:
            browser.close()


if __name__ == "__main__":
    auto_submit_task("192.168.193.100")
