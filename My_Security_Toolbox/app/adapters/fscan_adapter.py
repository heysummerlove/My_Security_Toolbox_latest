import asyncio
import os
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
EXE_PATH = os.path.join(BASE_DIR, 'tools', 'fscan', 'fscan.exe')
DB_PATH = os.path.join(BASE_DIR, 'data', 'toolbox.db')


def update_status(task_id, status_msg):
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("UPDATE tasks SET status = ?, update_time = ? WHERE id = ?", (status_msg, now, task_id))
    conn.commit()
    conn.close()


async def run_fscan(task_id: int, target: str):
    if not os.path.exists(EXE_PATH):
        update_status(task_id, "ERROR: 未找到 fscan.exe (请检查 /tools/fscan 目录)")
        return

    try:
        process = await asyncio.create_subprocess_exec(
            EXE_PATH, '-h', target, '-nop',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()

        # [防乱码装甲] 先尝试 GBK，失败则用 UTF-8
        try:
            output = stdout.decode('gbk')
        except UnicodeDecodeError:
            output = stdout.decode('utf-8', errors='ignore')

        vulns = [line.strip() for line in output.split('\n') if '[+]' in line]
        if vulns:
            result = f"COMPLETED: 发现 {len(vulns)} 个风险 (如: {vulns[0][:35]}...)"
        else:
            result = "COMPLETED: 扫描完成，未见明显高危漏洞"

        update_status(task_id, result)

    except Exception as e:
        update_status(task_id, f"ERROR: 执行异常 ({str(e)})")