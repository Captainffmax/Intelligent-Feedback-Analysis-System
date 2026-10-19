"""
auth.py
=======
Administrator authentication for the Intelligent Feedback Analysis System.

Provides:
  * bcrypt password hashing / verification (passlib) for the Administrator
    collection credentials (§3.10 stores a cryptographic hash, never plaintext).
  * JWT issuance + decoding (python-jose) for stateless admin sessions.
  * A FastAPI dependency (`get_current_admin`) that guards protected routes
    such as the Tier-D Gemini summarization endpoint.

No secrets are hardcoded — the signing key and expiry come from config/env.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from .config import get_settings
from .database import administrators_collection

logger = logging.getLogger("ifas.auth")

# bcrypt is the design-frozen hashing scheme for the Administrator collection.
# We use the `bcrypt` package directly (passlib is unmaintained and breaks
# against bcrypt >= 4.1). bcrypt operates on a max of 72 bytes of the secret.
_BCRYPT_MAX_BYTES = 72

# Token endpoint the interactive docs / clients post credentials to.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/admin/login")


# ==========================================================================
# Pydantic payloads
# ==========================================================================
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


class TokenData(BaseModel):
    username: str
    role: str


# ==========================================================================
# Password hashing
# ==========================================================================
def _encode_secret(plain_password: str) -> bytes:
    """UTF-8 encode and clamp to bcrypt's 72-byte limit (consistent hash/verify)."""
    return plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain_password: str) -> str:
    """Return a bcrypt hash (str) for storage in the Administrator document."""
    hashed = bcrypt.hashpw(_encode_secret(plain_password), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Constant-time verification of a plaintext password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(
            _encode_secret(plain_password), hashed_password.encode("utf-8")
        )
    except (ValueError, TypeError):
        # Malformed / non-bcrypt hash stored — treat as a failed match.
        return False


# ==========================================================================
# JWT issuance / decoding
# ==========================================================================
def create_access_token(username: str, role: str) -> str:
    """Mint a signed JWT carrying the admin's username + role claims."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload: Dict[str, Any] = {
        "sub": username,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _decode_token(token: str) -> TokenData:
    """Validate a JWT and extract its claims, raising 401 on any failure."""
    settings = get_settings()
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate administrator credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        username: Optional[str] = payload.get("sub")
        role: Optional[str] = payload.get("role")
        if not username:
            raise credentials_error
        return TokenData(username=username, role=role or "unknown")
    except JWTError as exc:
        logger.info("Rejected token: %s", exc)
        raise credentials_error from exc


# ==========================================================================
# Credential authentication (used by the login route)
# ==========================================================================
async def authenticate_admin(username: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Look up the administrator by username and verify the bcrypt password.
    Returns the admin document on success, otherwise None.
    """
    admin = await administrators_collection().find_one({"username": username})
    if not admin:
        return None
    if not verify_password(password, admin.get("password", "")):
        return None
    return admin


# ==========================================================================
# Route dependency
# ==========================================================================
async def get_current_admin(token: str = Depends(oauth2_scheme)) -> TokenData:
    """
    FastAPI dependency: resolve + validate the current administrator from the
    bearer token, confirming the account still exists in the database.
    """
    token_data = _decode_token(token)
    admin = await administrators_collection().find_one({"username": token_data.username})
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Administrator account no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_data
