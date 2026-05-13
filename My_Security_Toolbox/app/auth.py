import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from fastapi import Header

from app.ops_manager import append_history_record

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "toolbox.db")
TOKEN_TTL_HOURS = 12
CAPTCHA_TTL_MINUTES = 5
DEFAULT_USERNAME = os.getenv("MST_DEFAULT_USERNAME", "admin").strip() or "admin"
LOGIN_MAX_FAILURES = max(1, int(os.getenv("MST_LOGIN_MAX_FAILURES", "5")))
LOGIN_LOCK_MINUTES = max(1, int(os.getenv("MST_LOGIN_LOCK_MINUTES", "15")))
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
PASSWORD_MIN_LENGTH = 12
PASSWORD_SPECIAL_CHARS = set("!@#$%^&*()_+-=[]{}|;:,.<>?/~`\\'\"")


def format_dt(value: datetime) -> str:
    return value.strftime(DATETIME_FORMAT)


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, DATETIME_FORMAT)
    except ValueError:
        return None


def now_str() -> str:
    return format_dt(datetime.now())


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120000,
    ).hex()
    return salt, password_hash


def verify_password(password: str, salt: str, password_hash: str) -> bool:
    _, candidate_hash = hash_password(password, salt)
    return hmac.compare_digest(candidate_hash, password_hash)


def validate_password_strength(password: str) -> None:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"新密码长度不能少于 {PASSWORD_MIN_LENGTH} 位。")
    if not any(ch.islower() for ch in password):
        raise ValueError("新密码至少包含一个小写字母。")
    if not any(ch.isupper() for ch in password):
        raise ValueError("新密码至少包含一个大写字母。")
    if not any(ch.isdigit() for ch in password):
        raise ValueError("新密码至少包含一个数字。")
    if not any(ch in PASSWORD_SPECIAL_CHARS or not ch.isalnum() for ch in password):
        raise ValueError("新密码至少包含一个特殊字符。")


def _ensure_user_security_columns(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()
    }
    if "failed_login_attempts" not in columns:
        conn.execute(
            "ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER NOT NULL DEFAULT 0"
        )
    if "locked_until" not in columns:
        conn.execute(
            "ALTER TABLE users ADD COLUMN locked_until TEXT NOT NULL DEFAULT ''"
        )
    if "password_initialized" not in columns:
        conn.execute(
            "ALTER TABLE users ADD COLUMN password_initialized INTEGER NOT NULL DEFAULT 1"
        )


def _ensure_auth_audit_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL DEFAULT '',
            user_id INTEGER DEFAULT NULL,
            event_type TEXT NOT NULL DEFAULT '',
            success INTEGER NOT NULL DEFAULT 0,
            message TEXT NOT NULL DEFAULT '',
            detail_data TEXT NOT NULL DEFAULT '{}',
            create_time TEXT NOT NULL DEFAULT ''
        )
        """
    )


def _ensure_default_admin_user(conn: sqlite3.Connection) -> None:
    now = now_str()
    existing_user = conn.execute(
        "SELECT id FROM users WHERE username = ?",
        (DEFAULT_USERNAME,),
    ).fetchone()
    if existing_user:
        return
    conn.execute(
        """
        INSERT INTO users (
            username,
            password_salt,
            password_hash,
            is_active,
            failed_login_attempts,
            locked_until,
            password_initialized,
            create_time,
            update_time
        )
        VALUES (?, '', '', 1, 0, '', 0, ?, ?)
        """,
        (DEFAULT_USERNAME, now, now),
    )


def ensure_auth_tables() -> None:
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            failed_login_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until TEXT NOT NULL DEFAULT '',
            password_initialized INTEGER NOT NULL DEFAULT 1,
            create_time TEXT NOT NULL,
            update_time TEXT NOT NULL
        )
        """
    )
    _ensure_user_security_columns(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_tokens (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expire_time TEXT NOT NULL,
            create_time TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS captcha_codes (
            captcha_id TEXT PRIMARY KEY,
            captcha_code TEXT NOT NULL,
            expire_time TEXT NOT NULL,
            create_time TEXT NOT NULL
        )
        """
    )
    _ensure_auth_audit_table(conn)
    _ensure_default_admin_user(conn)
    conn.commit()
    conn.close()


def _append_ops_audit(
    *,
    username: str,
    user_id: int | None,
    event_type: str,
    success: bool,
    message: str,
    detail_data: dict[str, Any] | None = None,
) -> None:
    status = "COMPLETED" if success else "ERROR"
    try:
        append_history_record(
            task_name=f"认证事件:{event_type}",
            executor=username or "anonymous",
            status=status,
            content=message,
            operation_type="认证安全",
            source_module="auth",
            detail_data={
                "event_type": event_type,
                "success": success,
                "user_id": user_id,
                **(detail_data or {}),
            },
        )
    except Exception:
        pass


def append_auth_audit_log(
    *,
    username: str,
    event_type: str,
    success: bool,
    message: str,
    user_id: int | None = None,
    detail_data: dict[str, Any] | None = None,
) -> None:
    ensure_auth_tables()
    payload = _encode_detail_data(detail_data)
    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO auth_audit_logs (username, user_id, event_type, success, message, detail_data, create_time)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            username or "",
            user_id,
            event_type,
            1 if success else 0,
            message,
            payload,
            now_str(),
        ),
    )
    conn.commit()
    conn.close()
    _append_ops_audit(
        username=username,
        user_id=user_id,
        event_type=event_type,
        success=success,
        message=message,
        detail_data=detail_data,
    )


def _encode_detail_data(detail_data: dict[str, Any] | None) -> str:
    import json

    return json.dumps(detail_data or {}, ensure_ascii=False)


def cleanup_expired_tokens() -> None:
    conn = get_db_connection()
    conn.execute(
        "DELETE FROM auth_tokens WHERE expire_time <= ?",
        (now_str(),),
    )
    conn.commit()
    conn.close()


def cleanup_expired_captchas() -> None:
    ensure_auth_tables()
    conn = get_db_connection()
    conn.execute(
        "DELETE FROM captcha_codes WHERE expire_time <= ?",
        (now_str(),),
    )
    conn.commit()
    conn.close()


def get_user_by_username(username: str):
    ensure_auth_tables()
    conn = get_db_connection()
    user = conn.execute(
        """
        SELECT
            id,
            username,
            password_salt,
            password_hash,
            is_active,
            failed_login_attempts,
            locked_until,
            password_initialized,
            create_time,
            update_time
        FROM users
        WHERE username = ?
        """,
        (username,),
    ).fetchone()
    conn.close()
    return user


def get_auth_bootstrap_status() -> dict[str, Any]:
    ensure_auth_tables()
    user = get_user_by_username(DEFAULT_USERNAME)
    initialized = bool(user and int(user["password_initialized"] or 0))
    return {
        "bootstrap_required": not initialized,
        "default_username": DEFAULT_USERNAME,
    }


def is_password_initialized(user) -> bool:
    return bool(user and int(user["password_initialized"] or 0))


def get_user_lock_state(user) -> tuple[bool, int]:
    if not user:
        return False, 0
    locked_until = parse_dt(user["locked_until"])
    if not locked_until:
        return False, 0
    now = datetime.now()
    if locked_until <= now:
        reset_login_failures(int(user["id"]))
        return False, 0
    remaining_seconds = int((locked_until - now).total_seconds())
    remaining_minutes = max(1, (remaining_seconds + 59) // 60)
    return True, remaining_minutes


def reset_login_failures(user_id: int) -> None:
    conn = get_db_connection()
    conn.execute(
        """
        UPDATE users
        SET failed_login_attempts = 0, locked_until = '', update_time = ?
        WHERE id = ?
        """,
        (now_str(), user_id),
    )
    conn.commit()
    conn.close()


def record_login_failure(user_id: int) -> tuple[bool, int, int]:
    conn = get_db_connection()
    user = conn.execute(
        "SELECT failed_login_attempts FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if not user:
        conn.close()
        return False, 0, LOGIN_MAX_FAILURES

    attempts = int(user["failed_login_attempts"] or 0) + 1
    now = datetime.now()
    locked = attempts >= LOGIN_MAX_FAILURES
    locked_until = format_dt(now + timedelta(minutes=LOGIN_LOCK_MINUTES)) if locked else ""
    persisted_attempts = 0 if locked else attempts
    conn.execute(
        """
        UPDATE users
        SET failed_login_attempts = ?, locked_until = ?, update_time = ?
        WHERE id = ?
        """,
        (persisted_attempts, locked_until, format_dt(now), user_id),
    )
    conn.commit()
    conn.close()
    remaining_attempts = 0 if locked else max(0, LOGIN_MAX_FAILURES - attempts)
    return locked, remaining_attempts, LOGIN_LOCK_MINUTES


def issue_token(user_id: int) -> tuple[str, str]:
    cleanup_expired_tokens()
    token = secrets.token_urlsafe(32)
    now = datetime.now()
    expire_time = now + timedelta(hours=TOKEN_TTL_HOURS)
    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO auth_tokens (token, user_id, expire_time, create_time)
        VALUES (?, ?, ?, ?)
        """,
        (
            token,
            user_id,
            format_dt(expire_time),
            format_dt(now),
        ),
    )
    conn.commit()
    conn.close()
    return token, format_dt(expire_time)


def revoke_user_tokens(user_id: int) -> None:
    conn = get_db_connection()
    conn.execute("DELETE FROM auth_tokens WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def revoke_token(token: str) -> None:
    if not token:
        return
    conn = get_db_connection()
    conn.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))
    conn.commit()
    conn.close()


def initialize_admin_password(username: str, new_password: str) -> None:
    username = (username or "").strip()
    new_password = (new_password or "").strip()
    if not username:
        raise ValueError("用户名不能为空。")
    if username != DEFAULT_USERNAME:
        raise ValueError("仅允许初始化默认管理员账号。")
    validate_password_strength(new_password)

    conn = get_db_connection()
    user = conn.execute(
        """
        SELECT id, username, password_initialized
        FROM users
        WHERE username = ?
        """,
        (username,),
    ).fetchone()
    if not user:
        conn.close()
        raise LookupError("管理员账号不存在。")
    if int(user["password_initialized"] or 0):
        conn.close()
        raise ValueError("管理员密码已初始化，请直接登录。")

    salt, password_hash = hash_password(new_password)
    now = now_str()
    conn.execute(
        """
        UPDATE users
        SET password_salt = ?, password_hash = ?, password_initialized = 1, update_time = ?
        WHERE id = ?
        """,
        (salt, password_hash, now, int(user["id"])),
    )
    conn.commit()
    conn.close()
    append_auth_audit_log(
        username=username,
        user_id=int(user["id"]),
        event_type="bootstrap_password_init",
        success=True,
        message="管理员账号已完成首次密码初始化。",
    )


def change_user_password(user_id: int, old_password: str, new_password: str) -> None:
    old_password = (old_password or "").strip()
    new_password = (new_password or "").strip()
    if not old_password or not new_password:
        raise ValueError("旧密码和新密码不能为空。")
    validate_password_strength(new_password)
    if new_password == old_password:
        raise ValueError("新密码不能与旧密码相同。")

    conn = get_db_connection()
    user = conn.execute(
        """
        SELECT id, username, password_salt, password_hash
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    ).fetchone()
    if not user:
        conn.close()
        raise LookupError("用户不存在。")
    if not verify_password(old_password, user["password_salt"], user["password_hash"]):
        conn.close()
        raise ValueError("旧密码错误。")

    salt, password_hash = hash_password(new_password)
    now = now_str()
    conn.execute(
        """
        UPDATE users
        SET password_salt = ?, password_hash = ?, password_initialized = 1, update_time = ?
        WHERE id = ?
        """,
        (salt, password_hash, now, user_id),
    )
    conn.execute("DELETE FROM auth_tokens WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    append_auth_audit_log(
        username=user["username"],
        user_id=int(user["id"]),
        event_type="password_change",
        success=True,
        message="用户修改密码成功，已强制旧会话失效。",
    )


def issue_captcha() -> tuple[str, str]:
    ensure_auth_tables()
    cleanup_expired_captchas()
    captcha_id = secrets.token_urlsafe(16)
    captcha_code = "".join(
        secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(4)
    )
    now = datetime.now()
    expire_time = now + timedelta(minutes=CAPTCHA_TTL_MINUTES)
    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO captcha_codes (captcha_id, captcha_code, expire_time, create_time)
        VALUES (?, ?, ?, ?)
        """,
        (
            captcha_id,
            captcha_code,
            format_dt(expire_time),
            format_dt(now),
        ),
    )
    conn.commit()
    conn.close()
    return captcha_id, captcha_code


def verify_captcha(captcha_id: str | None, captcha_code: str | None) -> bool:
    if not captcha_id or not captcha_code:
        return False
    cleanup_expired_captchas()
    conn = get_db_connection()
    row = conn.execute(
        "SELECT captcha_code FROM captcha_codes WHERE captcha_id = ?",
        (captcha_id,),
    ).fetchone()
    if row:
        conn.execute("DELETE FROM captcha_codes WHERE captcha_id = ?", (captcha_id,))
        conn.commit()
    conn.close()
    return bool(row) and row["captcha_code"].lower() == captcha_code.strip().lower()


def build_captcha_svg(captcha_code: str) -> str:
    width, height = 160, 54
    lines = []
    for _ in range(4):
        x1 = secrets.randbelow(width)
        y1 = secrets.randbelow(height)
        x2 = secrets.randbelow(width)
        y2 = secrets.randbelow(height)
        lines.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#9db4c9" stroke-width="1"/>'
        )

    dots = []
    for _ in range(14):
        x = secrets.randbelow(width)
        y = secrets.randbelow(height)
        r = 1 + secrets.randbelow(2)
        dots.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#b8c9da"/>')

    chars = []
    for index, ch in enumerate(captcha_code):
        x = 22 + index * 32 + secrets.randbelow(6)
        y = 32 + secrets.randbelow(6)
        rotate = secrets.randbelow(21) - 10
        chars.append(
            f'<text x="{x}" y="{y}" fill="#163a5f" font-size="28" font-family="Arial, sans-serif" '
            f'font-weight="700" transform="rotate({rotate} {x} {y})">{ch}</text>'
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        f'<rect width="100%" height="100%" rx="10" ry="10" fill="#f3f7fb"/>'
        + "".join(lines)
        + "".join(dots)
        + "".join(chars)
        + "</svg>"
    )


def get_token_from_header(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        return None
    return parts[1]


def get_current_user_by_token(token: str | None):
    if not token:
        return None
    cleanup_expired_tokens()
    conn = get_db_connection()
    user = conn.execute(
        """
        SELECT users.id, users.username, users.is_active, users.password_initialized, auth_tokens.expire_time
        FROM auth_tokens
        JOIN users ON users.id = auth_tokens.user_id
        WHERE auth_tokens.token = ?
        """,
        (token,),
    ).fetchone()
    conn.close()
    if not user or not user["is_active"] or not int(user["password_initialized"] or 0):
        return None
    return user


def require_current_user(authorization: str | None = Header(default=None)):
    token = get_token_from_header(authorization)
    current_user = get_current_user_by_token(token)
    if not current_user:
        return None
    return current_user
