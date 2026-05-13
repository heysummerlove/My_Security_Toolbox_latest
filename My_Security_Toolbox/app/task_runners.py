import os
import platform
import re
import shlex
import subprocess
import sys
import time
from typing import Callable
from urllib.parse import urlparse

from app.report_builder import generate_report_package
from app.task_manager import (
    append_log,
    is_cancel_requested,
    register_handle,
    unregister_handle,
    update_task,
)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
NMAP_EXE = os.path.join(BASE_DIR, "tools", "nmap", "nmap.exe")
FSCAN_EXE = os.path.join(BASE_DIR, "tools", "fscan", "fscan.exe")
DATA_DIR = os.path.join(BASE_DIR, "data")
RESULT_DIRS = {
    "basic": os.path.join(DATA_DIR, "basic_results"),
    "nmap": os.path.join(DATA_DIR, "nmap_results"),
    "fscan": os.path.join(DATA_DIR, "fscan_results"),
    "nsfocus": os.path.join(DATA_DIR, "nsfocus_results"),
    "evaluation": os.path.join(DATA_DIR, "evaluation_results"),
    "nsfocus_report": os.path.join(DATA_DIR, "nsfocus_reports"),
    "report_compile": os.path.join(DATA_DIR, "generated_reports"),
}

EVALUATION_STAGE_TITLES = {
    "basic-ping": "基础连通性检测",
    "nmap": "Nmap 端口扫描",
    "fscan": "Fscan 综合漏扫",
    "nsfocus": "Web 漏扫下发",
}

NSFOCUS_BOOTSTRAP = (
    "import os, sys; "
    "sys.path.insert(0, os.getcwd()); "
    "from app.adapters.nsfocus_auto import auto_submit_task; "
    "auto_submit_task(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else '')"
)

NSFOCUS_REPORT_BOOTSTRAP = (
    "import os, sys; "
    "sys.path.insert(0, os.getcwd()); "
    "from app.adapters.nsfocus_auto import download_latest_report_only; "
    "path = download_latest_report_only(sys.argv[1] if len(sys.argv) > 1 else ''); "
    "print(path or '')"
)


def ensure_result_dirs() -> None:
    for path in RESULT_DIRS.values():
        os.makedirs(path, exist_ok=True)


def _safe_report_text(value: str) -> str:
    return value.strip() if value and value.strip() else "-"


def _trim_report_output(output: str, max_chars: int = 4000) -> str:
    output = output.strip()
    if not output:
        return "No output captured."
    if len(output) <= max_chars:
        return output
    return output[:max_chars] + "\n\n... (output truncated) ..."


def _write_evaluation_report(
    report_path: str,
    *,
    task_id: int,
    target: str,
    task_name: str,
    results: list[dict[str, str]],
) -> None:
    success_count = sum(1 for item in results if item["status_code"] == "COMPLETED")
    error_count = sum(1 for item in results if item["status_code"] == "ERROR")

    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("综合评估报告\n")
        fh.write("=" * 72 + "\n")
        fh.write(f"任务ID: {task_id}\n")
        fh.write(f"任务名称: {_safe_report_text(task_name)}\n")
        fh.write(f"评估目标: {target}\n")
        fh.write(f"成功阶段: {success_count}/{len(results)}\n")
        fh.write(f"失败阶段: {error_count}\n\n")

        for index, item in enumerate(results, start=1):
            stage_name = EVALUATION_STAGE_TITLES.get(item["name"], item["name"])
            fh.write(f"{index}. {stage_name}\n")
            fh.write("-" * 72 + "\n")
            fh.write(f"阶段标识: {item['name']}\n")
            fh.write(f"执行状态: {item['status_code']}\n")
            fh.write(f"阶段摘要: {item['message']}\n")
            fh.write(f"结果文件: {item['result_path']}\n")
            fh.write("输出摘录:\n")
            fh.write(_trim_report_output(item.get("output", "")) + "\n\n")


def decode_console_bytes(raw: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
FSCAN_PROGRESS_RE = re.compile(
    r"(端口扫描中|扫描中|ETA:|TCP:\d+/\d+|\d+/\d+\)\s+\d+/s|\[[=>\.\s]+\])",
    re.IGNORECASE,
)


def _write_output_file(output_path: str, cmd: list[str], output: str) -> None:
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("Command: " + subprocess.list2cmdline(cmd) + "\n\n")
        fh.write(output)


def _terminate_process(process: subprocess.Popen) -> None:
    try:
        if getattr(process, "pid", None) and os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            process.terminate()
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def _extract_network_target(target: str) -> str:
    parsed = urlparse(target)
    if parsed.scheme and parsed.hostname:
        return parsed.hostname
    return target


def _normalize_console_line(raw_line: bytes) -> str:
    text = decode_console_bytes(raw_line)
    text = ANSI_ESCAPE_RE.sub("", text)
    text = text.replace("\r", "").replace("\x00", "")
    return text.strip()


def _should_keep_log_line(label: str, line: str) -> bool:
    if not line:
        return False

    if label.endswith("fscan") or "/fscan" in label:
        if FSCAN_PROGRESS_RE.search(line):
            return False
        if line.startswith("[*]") or line.startswith("[+]") or line.startswith("[!]") or line.startswith("[-]"):
            return True
        keywords = (
            "漏洞",
            "开放",
            "发现",
            "成功",
            "失败",
            "错误",
            "爆破",
            "弱口令",
            "web title",
            "http",
            "redis",
            "smb",
            "rdp",
            "ssh",
            "mysql",
            "mssql",
            "oracle",
            "ftp",
        )
        return any(keyword.lower() in line.lower() for keyword in keywords)

    return True


def _build_fscan_command(raw_args: str) -> list[str]:
    raw_args = raw_args.strip()
    if not raw_args:
        raise ValueError("fscan args are empty")

    # Compatibility mode: if the user inputs only a host, expand it to the old default form.
    if not raw_args.startswith("-"):
        return [FSCAN_EXE, "-h", _extract_network_target(raw_args), "-nopg"]

    return [FSCAN_EXE, *shlex.split(raw_args, posix=False)]


def _extract_basic_summary(tool: str, output: str, return_code: int) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if tool == "ping":
        if return_code == 0:
            hit = next((line for line in lines if "TTL=" in line or "ttl=" in line), "")
            return "COMPLETED: ping finished successfully" + (f" | {hit}" if hit else "")
        return "ERROR: ping did not reach the target"
    if return_code == 0:
        hop_count = sum(1 for line in lines if line[:2].strip().isdigit())
        return f"COMPLETED: tracert finished, collected about {hop_count} hops"
    return "ERROR: tracert finished with an exception"


def _extract_nmap_summary(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    open_ports = [line for line in lines if "/tcp" in line or "/udp" in line]
    host_line = next((line for line in lines if "Nmap scan report for" in line), "")
    if open_ports:
        return f"COMPLETED: found {len(open_ports)} open ports"
    if "0 hosts up" in output:
        return "COMPLETED: target did not respond as alive"
    if "Host is up" in output:
        return "COMPLETED: host is alive, but no open ports were found in the fast scan"
    if host_line:
        return f"COMPLETED: {host_line}"
    return "COMPLETED: nmap finished"


def _build_nmap_command(raw_args: str) -> list[str]:
    raw_args = raw_args.strip()
    if not raw_args:
        raise ValueError("nmap args are empty")

    return [NMAP_EXE, "-Pn", "-T4", "-F", "-sV", "--open", *shlex.split(raw_args, posix=False)]


def _extract_fscan_summary(output: str) -> str:
    findings = [
        line.strip()
        for line in output.splitlines()
        if "[+]" in line or "[!]" in line
    ]
    if findings:
        return f"COMPLETED: found {len(findings)} notable lines"
    return "COMPLETED: fscan finished, no obvious high-risk finding was captured"


def _run_managed_process(
    task_id: int,
    *,
    label: str,
    cmd: list[str],
    output_path: str,
    summary_func: Callable[[str, int | None], str],
    cwd: str | None = None,
    running_message: str | None = None,
    missing_message: str | None = None,
    finalize_task: bool = True,
) -> dict[str, str]:
    ensure_result_dirs()

    if is_cancel_requested(task_id):
        message = f"CANCELED: {label} was paused before execution"
        if finalize_task:
            update_task(task_id, "CANCELED", message, result_path=output_path)
        else:
            append_log(task_id, f"[{label}] {message}")
        return {
            "status_code": "CANCELED",
            "message": message,
            "result_path": output_path,
            "output": "",
        }

    executable = cmd[0]
    if os.path.isabs(executable) and not os.path.exists(executable):
        message = missing_message or f"ERROR: missing executable: {executable}"
        if finalize_task:
            update_task(task_id, "ERROR", message, result_path=output_path)
        else:
            append_log(task_id, f"[{label}] {message}")
        return {
            "status_code": "ERROR",
            "message": message,
            "result_path": output_path,
            "output": "",
        }

    if finalize_task:
        update_task(
            task_id,
            "RUNNING",
            running_message or f"RUNNING: {label} is executing",
            result_path=output_path,
        )
    else:
        update_task(
            task_id,
            "RUNNING",
            running_message or f"RUNNING: stage {label} is executing",
            append_status_log=False,
        )
        append_log(task_id, f"[{label}] started")

    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
    )
    register_handle(task_id, process)

    output_lines: list[str] = []
    return_code = None
    canceled = False

    try:
        assert process.stdout is not None
        while True:
            raw_line = process.stdout.readline()
            if raw_line:
                line = _normalize_console_line(raw_line)
                if _should_keep_log_line(label, line):
                    output_lines.append(line)
                    append_log(task_id, f"[{label}] {line}")
                continue

            return_code = process.poll()
            if return_code is not None:
                break

            if is_cancel_requested(task_id):
                canceled = True
                _terminate_process(process)
                return_code = process.wait(timeout=10)
                break

            time.sleep(0.1)

        if is_cancel_requested(task_id):
            canceled = True
    finally:
        unregister_handle(task_id)

    output_text = "\n".join(output_lines).strip()
    _write_output_file(output_path, cmd, output_text)

    if canceled:
        message = f"CANCELED: {label} was paused by user"
        if finalize_task:
            update_task(task_id, "CANCELED", message, result_path=output_path)
        else:
            append_log(task_id, f"[{label}] {message}")
        return {
            "status_code": "CANCELED",
            "message": message,
            "result_path": output_path,
            "output": output_text,
        }

    if return_code not in (0, None):
        message = f"ERROR: {label} exited with code {return_code}"
        if finalize_task:
            update_task(task_id, "ERROR", message, result_path=output_path)
        else:
            append_log(task_id, f"[{label}] {message}")
        return {
            "status_code": "ERROR",
            "message": message,
            "result_path": output_path,
            "output": output_text,
        }

    message = summary_func(output_text, return_code)
    status_code = "COMPLETED" if message.startswith("COMPLETED") else "ERROR"
    if finalize_task:
        update_task(task_id, status_code, message, result_path=output_path)
    else:
        append_log(task_id, f"[{label}] {message}")
    return {
        "status_code": status_code,
        "message": message,
        "result_path": output_path,
        "output": output_text,
    }


def run_basic_task(task_id: int, tool: str, target: str) -> None:
    target = _extract_network_target(target)
    system = platform.system().lower()
    if tool == "ping":
        cmd = ["ping", "-n", "4", target] if system == "windows" else ["ping", "-c", "4", target]
    else:
        cmd = ["tracert", "-d", "-h", "15", target] if system == "windows" else ["traceroute", "-n", "-m", "15", target]

    output_path = os.path.join(RESULT_DIRS["basic"], f"basic_{tool}_task_{task_id}.txt")
    _run_managed_process(
        task_id,
        label=f"basic:{tool}",
        cmd=cmd,
        output_path=output_path,
        summary_func=lambda output, return_code: _extract_basic_summary(tool, output, 0 if return_code in (0, None) else return_code),
        running_message=f"RUNNING: {tool} is probing {target}",
        finalize_task=True,
    )


def run_nmap_task(task_id: int, target: str) -> None:
    cmd = _build_nmap_command(target)
    output_path = os.path.join(RESULT_DIRS["nmap"], f"nmap_task_{task_id}.txt")
    _run_managed_process(
        task_id,
        label="nmap",
        cmd=cmd,
        cwd=os.path.dirname(NMAP_EXE),
        output_path=output_path,
        summary_func=lambda output, _return_code: _extract_nmap_summary(output),
        running_message=f"RUNNING: nmap is scanning {target}",
        missing_message="ERROR: nmap.exe was not found",
        finalize_task=True,
    )


def run_fscan_task(task_id: int, raw_args: str) -> None:
    cmd = _build_fscan_command(raw_args)
    output_path = os.path.join(RESULT_DIRS["fscan"], f"fscan_task_{task_id}.txt")
    _run_managed_process(
        task_id,
        label="fscan",
        cmd=cmd,
        cwd=os.path.dirname(FSCAN_EXE),
        output_path=output_path,
        summary_func=lambda output, _return_code: _extract_fscan_summary(output),
        running_message=f"RUNNING: fscan is executing with args: {raw_args}",
        missing_message="ERROR: fscan.exe was not found",
        finalize_task=True,
    )


def run_nsfocus_task(task_id: int, target: str, task_name: str = "") -> None:
    cmd = [
        sys.executable,
        "-u",
        "-c",
        NSFOCUS_BOOTSTRAP,
        target,
        task_name,
    ]
    output_path = os.path.join(RESULT_DIRS["nsfocus"], f"nsfocus_task_{task_id}.txt")
    _run_managed_process(
        task_id,
        label="nsfocus",
        cmd=cmd,
        cwd=BASE_DIR,
        output_path=output_path,
        summary_func=lambda output, _return_code: "COMPLETED: nsfocus task was submitted"
        if "扫描任务已完成下发" in output or "task" in output.lower()
        else "COMPLETED: nsfocus automation finished",
        running_message=f"RUNNING: nsfocus is submitting target {target}",
        finalize_task=True,
    )


def run_nsfocus_report_task(task_id: int, task_name: str = "") -> None:
    ensure_result_dirs()
    output_path = os.path.join(RESULT_DIRS["nsfocus_report"], f"nsfocus_report_task_{task_id}.txt")
    cmd = [
        sys.executable,
        "-u",
        "-c",
        NSFOCUS_REPORT_BOOTSTRAP,
        task_name,
    ]
    result = _run_managed_process(
        task_id,
        label="nsfocus-report",
        cmd=cmd,
        cwd=BASE_DIR,
        output_path=output_path,
        summary_func=lambda output, _return_code: "COMPLETED: nsfocus report downloaded"
        if output.strip()
        else "ERROR: nsfocus report download returned empty path",
        running_message="RUNNING: downloading latest nsfocus report",
        finalize_task=False,
    )

    downloaded_path = ""
    for line in reversed(result["output"].splitlines()):
        candidate = line.strip()
        if candidate and os.path.exists(candidate):
            downloaded_path = candidate
            break

    if result["status_code"] == "COMPLETED" and downloaded_path:
        update_task(task_id, "COMPLETED", f"COMPLETED: nsfocus report downloaded to {downloaded_path}", result_path=downloaded_path)
        return

    final_message = result["message"] if result["message"] else "ERROR: nsfocus report download failed"
    update_task(task_id, "ERROR", final_message, result_path=output_path)


def run_evaluation_task(task_id: int, target: str, task_name: str = "") -> None:
    ensure_result_dirs()
    network_target = _extract_network_target(target)
    report_path = os.path.join(RESULT_DIRS["evaluation"], f"evaluation_task_{task_id}.txt")
    stages = [
        {
            "name": "basic-ping",
            "runner": lambda: _run_managed_process(
                task_id,
                label="evaluation/basic-ping",
                cmd=["ping", "-n", "4", network_target] if platform.system().lower() == "windows" else ["ping", "-c", "4", network_target],
                output_path=os.path.join(RESULT_DIRS["basic"], f"evaluation_basic_task_{task_id}.txt"),
                summary_func=lambda output, return_code: _extract_basic_summary(
                    "ping",
                    output,
                    0 if return_code in (0, None) else return_code,
                ),
                running_message=f"RUNNING: evaluation stage basic-ping for {target}",
                finalize_task=False,
            ),
        },
        {
            "name": "nmap",
            "runner": lambda: _run_managed_process(
                task_id,
                label="evaluation/nmap",
                cmd=_build_nmap_command(network_target),
                cwd=os.path.dirname(NMAP_EXE),
                output_path=os.path.join(RESULT_DIRS["nmap"], f"evaluation_nmap_task_{task_id}.txt"),
                summary_func=lambda output, _return_code: _extract_nmap_summary(output),
                running_message=f"RUNNING: evaluation stage nmap for {target}",
                missing_message="ERROR: nmap.exe was not found",
                finalize_task=False,
            ),
        },
        {
            "name": "fscan",
            "runner": lambda: _run_managed_process(
                task_id,
                label="evaluation/fscan",
                cmd=[FSCAN_EXE, "-h", network_target, "-nopg"],
                cwd=os.path.dirname(FSCAN_EXE),
                output_path=os.path.join(RESULT_DIRS["fscan"], f"evaluation_fscan_task_{task_id}.txt"),
                summary_func=lambda output, _return_code: _extract_fscan_summary(output),
                running_message=f"RUNNING: evaluation stage fscan for {target}",
                missing_message="ERROR: fscan.exe was not found",
                finalize_task=False,
            ),
        },
        {
            "name": "nsfocus",
            "runner": lambda: _run_managed_process(
                task_id,
                label="evaluation/nsfocus",
                cmd=[
                    sys.executable,
                    "-u",
                    "-c",
                    NSFOCUS_BOOTSTRAP,
                    target,
                    task_name,
                ],
                cwd=BASE_DIR,
                output_path=os.path.join(RESULT_DIRS["nsfocus"], f"evaluation_nsfocus_task_{task_id}.txt"),
                summary_func=lambda output, _return_code: "COMPLETED: nsfocus task was submitted"
                if "扫描任务已完成下发" in output or "task" in output.lower()
                else "COMPLETED: nsfocus automation finished",
                running_message=f"RUNNING: evaluation stage nsfocus for {target}",
                finalize_task=False,
            ),
        },
    ]

    results: list[dict[str, str]] = []
    update_task(
        task_id,
        "RUNNING",
        f"RUNNING: comprehensive evaluation started for {target}",
        result_path=report_path,
    )

    for stage in stages:
        if is_cancel_requested(task_id):
            _write_evaluation_report(
                report_path,
                task_id=task_id,
                target=target,
                task_name=task_name,
                results=results,
            )
            update_task(task_id, "CANCELED", "CANCELED: comprehensive evaluation was paused", result_path=report_path)
            return
        result = stage["runner"]()
        results.append({"name": stage["name"], **result})
        if result["status_code"] == "CANCELED":
            _write_evaluation_report(
                report_path,
                task_id=task_id,
                target=target,
                task_name=task_name,
                results=results,
            )
            update_task(task_id, "CANCELED", "CANCELED: comprehensive evaluation was paused", result_path=report_path)
            return

    success_count = sum(1 for item in results if item["status_code"] == "COMPLETED")
    error_count = sum(1 for item in results if item["status_code"] == "ERROR")

    _write_evaluation_report(
        report_path,
        task_id=task_id,
        target=target,
        task_name=task_name,
        results=results,
    )

    final_message = (
        f"COMPLETED: comprehensive evaluation finished, {success_count}/{len(results)} stages succeeded"
    )
    if error_count:
        final_message += f", {error_count} stages failed"
    update_task(task_id, "COMPLETED", final_message, result_path=report_path)


def run_report_compile_task(task_id: int, payload: dict[str, object]) -> None:
    ensure_result_dirs()
    if is_cancel_requested(task_id):
        update_task(task_id, "CANCELED", "CANCELED: report compile was paused before execution")
        return

    update_task(
        task_id,
        "RUNNING",
        "RUNNING: compiling report package from submitted form data",
    )

    try:
        zip_path = generate_report_package(
            task_id,
            payload,
            log=lambda message: append_log(task_id, f"[report-compile] {message}"),
        )
    except Exception as exc:
        update_task(task_id, "ERROR", f"ERROR: failed to compile report package ({exc})")
        return

    if is_cancel_requested(task_id):
        update_task(task_id, "CANCELED", "CANCELED: report compile was paused", result_path=str(zip_path))
        return

    update_task(
        task_id,
        "COMPLETED",
        "COMPLETED: report package is ready for download",
        result_path=str(zip_path),
    )
