"""
Simple session-based authentication for AutoOverlay AI.

Security model:
- Single hardcoded user: ADIT_IT_BOYS / ADIT_HATERS_99 (hackathon scope)
- Session cookie: HttpOnly, Secure (when HTTPS), SameSite=Lax, 24h TTL
- CSRF: Double-submit cookie pattern for mutating endpoints
- Login rate-limited: 5 attempts per minute per IP
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# ──────────────────────────────────────────────────────────────────────────
# Credentials (hardcoded for hackathon — do not commit real secrets)
# ──────────────────────────────────────────────────────────────────────────
VALID_USERNAME = "ADIT_IT_BOYS"
VALID_PASSWORD_HASH = hashlib.pbkdf2_hmac(
    "sha256", b"ADIT_HATERS_99", b"autooverlay-salt-2026", 100_000
).hex()

# ──────────────────────────────────────────────────────────────────────────
# Session store (in-process — fine for single-instance hackathon)
# ──────────────────────────────────────────────────────────────────────────
SESSION_TTL_SECONDS = 24 * 60 * 60  # 24 hours
LOGIN_RATE_LIMIT = 5  # max attempts
LOGIN_WINDOW_SECONDS = 60

_sessions: dict[str, dict] = {}  # session_id -> {user, created, csrf_token}
_login_attempts: dict[str, list[float]] = {}  # ip -> [timestamps]


def _clean_expired() -> None:
    now = time.time()
    expired = [sid for sid, s in _sessions.items() if now - s["created"] > SESSION_TTL_SECONDS]
    for sid in expired:
        _sessions.pop(sid, None)


def _verify_password(password: str) -> bool:
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), b"autooverlay-salt-2026", 100_000
    ).hex()
    return hmac.compare_digest(candidate, VALID_PASSWORD_HASH)


def _check_login_rate_limit(ip: str) -> bool:
    now = time.time()
    attempts = [t for t in _login_attempts.get(ip, []) if now - t < LOGIN_WINDOW_SECONDS]
    if len(attempts) >= LOGIN_RATE_LIMIT:
        return False
    attempts.append(now)
    _login_attempts[ip] = attempts
    return True


def _record_login_failure(ip: str) -> None:
    now = time.time()
    _login_attempts.setdefault(ip, []).append(now)


def create_session(user: str) -> tuple[str, str]:
    """Returns (session_id, csrf_token)."""
    _clean_expired()
    session_id = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    _sessions[session_id] = {
        "user": user,
        "created": time.time(),
        "csrf_token": csrf_token,
    }
    return session_id, csrf_token


def validate_session(session_id: Optional[str]) -> Optional[dict]:
    if not session_id:
        return None
    _clean_expired()
    session = _sessions.get(session_id)
    if not session:
        return None
    if time.time() - session["created"] > SESSION_TTL_SECONDS:
        _sessions.pop(session_id, None)
        return None
    return session


def validate_csrf(session_id: str, csrf_token: str) -> bool:
    session = _sessions.get(session_id)
    if not session:
        return False
    return hmac.compare_digest(session["csrf_token"], csrf_token)


def delete_session(session_id: str) -> None:
    _sessions.pop(session_id, None)


# ──────────────────────────────────────────────────────────────────────────
# FastAPI dependencies
# ──────────────────────────────────────────────────────────────────────────

SESSION_COOKIE_NAME = "ao_session"
CSRF_COOKIE_NAME = "ao_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"


def get_session_id(
    session_cookie: Optional[str] = Cookie(None, alias=SESSION_COOKIE_NAME),
) -> Optional[str]:
    return session_cookie


def get_current_user(
    session_id: Optional[str] = Depends(get_session_id),
) -> dict:
    session = validate_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"username": session["user"]}


def require_csrf(
    request: Request,
    session_id: Optional[str] = Depends(get_session_id),
    csrf_header: Optional[str] = Header(None, alias=CSRF_HEADER_NAME),
) -> None:
    """Dependency for mutating endpoints — validates CSRF token."""
    if not session_id:
        raise HTTPException(status_code=401, detail="No session")
    token = csrf_header
    if not token:
        # Also check form body for multipart
        # But for JSON APIs, header is the way
        raise HTTPException(status_code=403, detail="CSRF token required")
    if not validate_csrf(session_id, token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


# ──────────────────────────────────────────────────────────────────────────
# Auth router (login, logout, me)
# ──────────────────────────────────────────────────────────────────────────

from pydantic import BaseModel, Field

router = APIRouter()


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class LoginResponse(BaseModel):
    user: str
    csrf_token: str


@router.post("/auth/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
) -> LoginResponse:
    ip = request.client.host if request.client else "unknown"
    if not _check_login_rate_limit(ip):
        raise HTTPException(status_code=429, detail="Too many login attempts")

    if body.username != VALID_USERNAME or not _verify_password(body.password):
        _record_login_failure(ip)
        # Delay to slow brute force
        import asyncio
        await asyncio.sleep(0.5)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    session_id, csrf_token = create_session(body.username)
    # Set cookies
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=False,  # True in production behind HTTPS
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,  # JS needs to read it for header
        secure=False,
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
        path="/",
    )
    return LoginResponse(user=body.username, csrf_token=csrf_token)


@router.post("/auth/logout")
async def logout(
    response: Response,
    session_id: Optional[str] = Depends(get_session_id),
) -> dict:
    if session_id:
        delete_session(session_id)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")
    return {"status": "logged_out"}


@router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)) -> dict:
    return {"authenticated": True, "user": user["username"]}


@router.get("/auth/csrf")
async def get_csrf(session_id: Optional[str] = Depends(get_session_id)) -> dict:
    if not session_id:
        raise HTTPException(status_code=401, detail="No session")
    session = validate_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired")
    return {"csrf_token": session["csrf_token"]}


# ──────────────────────────────────────────────────────────────────────────
# Helpers for integrating with existing routers
# ──────────────────────────────────────────────────────────────────────────

def get_csrf_token(session_id: Optional[str] = Depends(get_session_id)) -> Optional[str]:
    """Returns the CSRF token for the current session (for UI to include in forms)."""
    if not session_id:
        return None
    session = _sessions.get(session_id)
    return session["csrf_token"] if session else None


# Re-export for other modules
__all__ = [
    "router",
    "get_current_user",
    "require_csrf",
    "get_csrf_token",
    "SESSION_COOKIE_NAME",
    "CSRF_COOKIE_NAME",
    "CSRF_HEADER_NAME",
]