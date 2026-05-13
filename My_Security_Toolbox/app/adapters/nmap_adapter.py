import asyncio
import os
import sqlite3
import subprocess
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
EXE_PATH = os.path.join(BASE_DIR, "tools", "nmap", "nmap.exe")
DB_PATH = os.path.join(BASE_DIR, "data", "toolbox.db")
OUTPUT_DIR = os.path.join(BASE_DIR, "data", "nmap_results")


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def update_status(task_id, status_msg):
    conn = get_db_connection()
    conn.execute(
        "UPDATE tasks SET status = ?, update_time = ? WHERE id = ?",
        (status_msg, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), task_id),
    )
    conn.commit()
    conn.close()


def create_task(target: str) -> int:
    conn = get_db_connection()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute(
        "INSERT INTO tasks (target, tool, status, update_time) VALUES (?, ?, ?, ?)",
        (target, "nmap", "PENDING: 等待启动", now),
    )
    task_id = cur.lastrowid
    conn.commit()
    conn.close()
    return task_id


def decode_output(raw: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def build_nmap_command(target: str):
    return [
        EXE_PATH,
        "-Pn",
        "-T4",
        "-F",
        "-sV",
        "--open",
        target,
    ]


def extract_summary(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    open_ports = [line for line in lines if "/tcp" in line or "/udp" in line]
    host_line = next((line for line in lines if "Nmap scan report for" in line), "")
    if open_ports:
        return f"COMPLETED: 发现 {len(open_ports)} 个开放端口"
    if "0 hosts up" in output:
        return "COMPLETED: 未发现存活主机"
    if "Host is up" in output:
        return "COMPLETED: 主机存活，但未发现开放端口"
    if host_line:
        return f"COMPLETED: {host_line}"
    return "COMPLETED: 扫描完成"


async def run_nmap(target: str):
    ensure_output_dir()
    task_id = create_task(target)

    if not os.path.exists(EXE_PATH):
        update_status(task_id, "ERROR: 未找到 nmap.exe")
        return

    cmd = build_nmap_command(target)
    update_status(task_id, f"RUNNING: 正在扫描 {target}")

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=os.path.dirname(EXE_PATH),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await process.communicate()
        output = decode_output(stdout)

        output_path = os.path.join(OUTPUT_DIR, f"nmap_task_{task_id}.txt")
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write("Command: " + subprocess.list2cmdline(cmd) + "\n\n")
            fh.write(output)

        summary = extract_summary(output)
        update_status(task_id, f"{summary} | 结果文件: {output_path}")
    except Exception as exc:
        update_status(task_id, f"ERROR: Nmap 执行异常 ({str(exc)})")
