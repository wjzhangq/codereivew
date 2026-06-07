"""core/security.py — 密码哈希、JWT、对称加密(deploy key/token 落库)"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import os
import secrets

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet

from app.core.config import get_settings

_ph = PasswordHasher()


# --------------------------------------------------------------------------- #
# 密码哈希
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #
def create_token(sub: str, role: str, extra: dict | None = None) -> str:
    s = get_settings()
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": sub,
        "role": role,
        "iat": now,
        "exp": now + dt.timedelta(hours=s.auth.session.ttl_hours),
        **(extra or {}),
    }
    return jwt.encode(payload, s.auth.session.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    s = get_settings()
    try:
        return jwt.decode(token, s.auth.session.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


# --------------------------------------------------------------------------- #
# API Key
# --------------------------------------------------------------------------- #
def generate_api_key() -> tuple[str, str]:
    """返回 (明文 key 仅展示一次, key_hash 落库)。"""
    raw = "crk_" + secrets.token_urlsafe(32)
    return raw, hash_api_key(raw)


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# --------------------------------------------------------------------------- #
# 对称加密(deploy key / 平台 token 落库)
# --------------------------------------------------------------------------- #
def _fernet() -> Fernet:
    key = os.getenv("CR_ENCRYPTION_KEY")
    if not key:
        # 开发回落:从 JWT secret 派生(生产必须显式设置 CR_ENCRYPTION_KEY)
        seed = get_settings().auth.session.jwt_secret.encode()
        key = base64.urlsafe_b64encode(hashlib.sha256(seed).digest()).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
