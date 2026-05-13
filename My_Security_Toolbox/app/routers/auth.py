from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from app.auth import (
    DEFAULT_USERNAME,
    append_auth_audit_log,
    build_captcha_svg,
    change_user_password,
    get_auth_bootstrap_status,
    get_current_user_by_token,
    get_token_from_header,
    get_user_by_username,
    get_user_lock_state,
    initialize_admin_password,
    is_password_initialized,
    issue_captcha,
    issue_token,
    record_login_failure,
    require_current_user,
    reset_login_failures,
    revoke_token,
    verify_captcha,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str
    captcha_id: str | None = None
    captcha_code: str | None = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class BootstrapPasswordRequest(BaseModel):
    username: str
    new_password: str
    confirm_password: str
    captcha_id: str | None = None
    captcha_code: str | None = None


@router.get("/captcha")
def auth_captcha():
    captcha_id, captcha_code = issue_captcha()
    return {
        "code": 200,
        "message": "验证码已生成",
        "data": {
            "captcha_id": captcha_id,
            "captcha_svg": build_captcha_svg(captcha_code),
        },
    }


@router.get("/bootstrap-status")
def bootstrap_status():
    return {
        "code": 200,
        "message": "查询成功",
        "data": get_auth_bootstrap_status(),
    }


@router.post("/bootstrap-password")
def bootstrap_password(req: BootstrapPasswordRequest):
    username = req.username.strip()
    if not username:
        return {"code": 400, "message": "用户名不能为空。", "data": ""}
    if username != DEFAULT_USERNAME:
        return {"code": 400, "message": "仅允许初始化默认管理员账号。", "data": ""}
    if not verify_captcha(req.captcha_id, req.captcha_code):
        return {"code": 400, "message": "验证码错误或已过期。", "data": ""}
    if req.new_password != req.confirm_password:
        return {"code": 400, "message": "两次输入的新密码不一致。", "data": ""}

    try:
        initialize_admin_password(username, req.new_password)
    except LookupError as exc:
        append_auth_audit_log(
            username=username,
            user_id=None,
            event_type="bootstrap_password_init",
            success=False,
            message=str(exc),
        )
        return {"code": 404, "message": str(exc), "data": ""}
    except ValueError as exc:
        append_auth_audit_log(
            username=username,
            user_id=None,
            event_type="bootstrap_password_init",
            success=False,
            message=str(exc),
        )
        return {"code": 400, "message": str(exc), "data": ""}

    return {"code": 200, "message": "管理员密码初始化成功，请使用新密码登录。", "data": ""}


@router.get("/status")
def auth_status(authorization: str | None = Header(default=None)):
    token = get_token_from_header(authorization)
    current_user = get_current_user_by_token(token)
    if not current_user:
        return {"code": 401, "message": "未登录", "data": {"authenticated": False}}
    return {
        "code": 200,
        "message": "登录状态有效",
        "data": {
            "authenticated": True,
            "username": current_user["username"],
            "expire_time": current_user["expire_time"],
        },
    }


@router.post("/login")
def login(req: LoginRequest):
    username = req.username.strip()
    password = req.password
    if not username or not password:
        return {"code": 400, "message": "用户名和密码不能为空。", "data": ""}
    if not verify_captcha(req.captcha_id, req.captcha_code):
        append_auth_audit_log(
            username=username,
            user_id=None,
            event_type="login",
            success=False,
            message="登录失败，验证码错误或已过期。",
        )
        return {"code": 400, "message": "验证码错误或已过期。", "data": ""}

    user = get_user_by_username(username)
    if not user or not user["is_active"]:
        append_auth_audit_log(
            username=username,
            user_id=None,
            event_type="login",
            success=False,
            message="登录失败，用户名或密码错误。",
        )
        return {"code": 401, "message": "用户名或密码错误。", "data": ""}

    if not is_password_initialized(user):
        append_auth_audit_log(
            username=username,
            user_id=int(user["id"]),
            event_type="login",
            success=False,
            message="登录失败，管理员账号尚未初始化密码。",
        )
        return {
            "code": 403,
            "message": "管理员账号尚未初始化密码，请先完成首次密码设置。",
            "data": {"bootstrap_required": True, "username": user["username"]},
        }

    is_locked, remaining_minutes = get_user_lock_state(user)
    if is_locked:
        append_auth_audit_log(
            username=username,
            user_id=int(user["id"]),
            event_type="login",
            success=False,
            message=f"登录失败，账号已锁定，剩余 {remaining_minutes} 分钟。",
            detail_data={"locked": True, "remaining_minutes": remaining_minutes},
        )
        return {
            "code": 423,
            "message": f"登录失败次数过多，账号已被临时锁定，请约 {remaining_minutes} 分钟后再试。",
            "data": {"locked": True, "remaining_minutes": remaining_minutes},
        }

    if not verify_password(password, user["password_salt"], user["password_hash"]):
        locked, remaining_attempts, lock_minutes = record_login_failure(int(user["id"]))
        if locked:
            append_auth_audit_log(
                username=username,
                user_id=int(user["id"]),
                event_type="login",
                success=False,
                message=f"登录失败次数过多，账号已锁定 {lock_minutes} 分钟。",
                detail_data={"locked": True, "remaining_minutes": lock_minutes},
            )
            return {
                "code": 423,
                "message": f"登录失败次数过多，账号已被临时锁定 {lock_minutes} 分钟。",
                "data": {"locked": True, "remaining_minutes": lock_minutes},
            }

        append_auth_audit_log(
            username=username,
            user_id=int(user["id"]),
            event_type="login",
            success=False,
            message=f"登录失败，用户名或密码错误，还可再尝试 {remaining_attempts} 次。",
            detail_data={"locked": False, "remaining_attempts": remaining_attempts},
        )
        return {
            "code": 401,
            "message": f"用户名或密码错误。还可再尝试 {remaining_attempts} 次。",
            "data": {"locked": False, "remaining_attempts": remaining_attempts},
        }

    reset_login_failures(int(user["id"]))
    token, expire_time = issue_token(int(user["id"]))
    append_auth_audit_log(
        username=user["username"],
        user_id=int(user["id"]),
        event_type="login",
        success=True,
        message="登录成功。",
        detail_data={"expire_time": expire_time},
    )
    return {
        "code": 200,
        "message": "登录成功",
        "data": {
            "token": token,
            "username": user["username"],
            "expire_time": expire_time,
        },
    }


@router.post("/logout")
def logout(authorization: str | None = Header(default=None)):
    token = get_token_from_header(authorization)
    current_user = get_current_user_by_token(token)
    if token:
        revoke_token(token)
    if current_user:
        append_auth_audit_log(
            username=current_user["username"],
            user_id=int(current_user["id"]),
            event_type="logout",
            success=True,
            message="用户已退出登录。",
        )
    return {"code": 200, "message": "已退出登录", "data": ""}


@router.post("/change-password")
def change_password(req: ChangePasswordRequest, current_user=Depends(require_current_user)):
    if not current_user:
        return {"code": 401, "message": "未登录或登录已过期，请重新登录。", "data": ""}
    try:
        change_user_password(int(current_user["id"]), req.old_password, req.new_password)
    except LookupError as exc:
        append_auth_audit_log(
            username=current_user["username"],
            user_id=int(current_user["id"]),
            event_type="password_change",
            success=False,
            message=str(exc),
        )
        return {"code": 404, "message": str(exc), "data": ""}
    except ValueError as exc:
        append_auth_audit_log(
            username=current_user["username"],
            user_id=int(current_user["id"]),
            event_type="password_change",
            success=False,
            message=str(exc),
        )
        return {"code": 400, "message": str(exc), "data": ""}
    return {"code": 200, "message": "密码修改成功，请重新登录", "data": ""}
