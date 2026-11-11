import os
from typing import Optional
import jwt
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

JWT_SECRET = os.getenv("JWT_SECRET", "ibanking-dev-jwt-secret-change-me-0123456789")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "ibanking-dev-internal-key")

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user_id(credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme)) -> int:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Bạn chưa đăng nhập")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token không hợp lệ")
    return int(payload["sub"])


def verify_internal_key(x_internal_key: Optional[str] = Header(None)):
    if x_internal_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail="Chỉ dành cho service nội bộ")
