from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from . import config
from .database import get_db
from .models import AppUser


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(
    user: AppUser, *, expire_minutes: int | None = None
) -> tuple[str, datetime]:
    minutes = config.ACCESS_TOKEN_EXPIRE_MINUTES if expire_minutes is None else expire_minutes
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    token = jwt.encode(
        {"sub": user.id, "username": user.username, "role": user.role, "exp": expires_at},
        config.SECRET_KEY,
        algorithm=ALGORITHM,
    )
    return token, expires_at


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> AppUser:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="尚未登录。")
    try:
        payload = jwt.decode(credentials.credentials, config.SECRET_KEY, algorithms=[ALGORITHM])
        user_id = str(payload.get("sub") or "")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录令牌无效。") from None
    user = db.get(AppUser, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不可用。")
    return user


def require_writer(user: AppUser = Depends(current_user)) -> AppUser:
    if user.role not in {"admin", "editor", "entry"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号只读，不能修改数据。")
    return user


def require_change_permission(user: AppUser = Depends(current_user)) -> AppUser:
    """Accounts allowed to inspect the immutable non-admin change history."""
    if user.role not in {"admin", "editor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要修改权限或管理员权限。")
    return user


def require_admin(user: AppUser = Depends(current_user)) -> AppUser:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限。")
    return user
