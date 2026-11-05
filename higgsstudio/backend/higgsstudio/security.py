"""Cuentas, sesiones y claves de API.

Las contraseñas se guardan con PBKDF2-SHA256 (biblioteca estándar, sin
dependencias nativas). Las sesiones van en una cookie httpOnly; las claves de
API viajan en `Authorization: Bearer hs_...` y solo se muestran una vez.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from typing import Any

from fastapi import Depends, HTTPException, Request, status

from . import db
from .config import get_settings

ITERATIONS = 240_000
SESSION_COOKIE = "hs_session"


# ------------------------- Contraseñas -------------------------

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
    return hmac.compare_digest(digest.hex(), digest_hex)


# ------------------------- Usuarios -------------------------

def create_user(
    email: str,
    password: str,
    *,
    name: str = "",
    is_admin: bool = False,
    credits: int | None = None,
) -> dict[str, Any]:
    email = email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "El correo no es válido")
    if len(password) < 8:
        raise HTTPException(400, "La contraseña necesita al menos 8 caracteres")
    if db.query_one("SELECT id FROM users WHERE email = ?", (email,)):
        raise HTTPException(409, "Ya existe una cuenta con ese correo")

    settings = get_settings()
    uid = db.new_id("usr")
    ts = db.now()
    start_credits = settings.signup_credits if credits is None else credits
    db.insert("users", {
        "id": uid,
        "email": email,
        "name": name or email.split("@")[0],
        "password_hash": hash_password(password),
        "plan": "free",
        "credits": start_credits,
        "is_admin": int(is_admin),
        "created_at": ts,
        "updated_at": ts,
    })
    if start_credits:
        db.insert("credit_tx", {
            "id": db.new_id("ctx"),
            "user_id": uid,
            "amount": start_credits,
            "kind": "grant",
            "reason": "Créditos de bienvenida",
            "balance_after": start_credits,
            "created_at": ts,
        })
    user = db.row_to_dict(db.get("users", uid))
    assert user is not None
    return user


def authenticate(email: str, password: str) -> dict[str, Any]:
    row = db.query_one("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
    user = db.row_to_dict(row)
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(401, "Correo o contraseña incorrectos")
    return user


def bootstrap_admin() -> None:
    """Crea la primera cuenta si la base está vacía y hay credenciales."""
    settings = get_settings()
    if db.query_one("SELECT id FROM users LIMIT 1"):
        return
    email = settings.bootstrap_email
    password = settings.bootstrap_password
    if not (email and password):
        return
    create_user(email, password, name="Admin", is_admin=True, credits=100_000)


# ------------------------- Sesiones -------------------------

def create_session(user_id: str, user_agent: str = "") -> str:
    token = secrets.token_urlsafe(40)
    settings = get_settings()
    expires = time.gmtime(time.time() + settings.session_days * 86400)
    db.insert("sessions", {
        "token": token,
        "user_id": user_id,
        "user_agent": user_agent[:200],
        "created_at": db.now(),
        "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", expires),
    })
    return token


def destroy_session(token: str) -> None:
    db.execute("DELETE FROM sessions WHERE token = ?", (token,))


def user_from_session(token: str) -> dict[str, Any] | None:
    row = db.query_one(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token = ? AND s.expires_at > ?",
        (token, db.now()),
    )
    return db.row_to_dict(row)


# ------------------------- Claves de API -------------------------

def create_api_key(user_id: str, name: str = "", scopes: list[str] | None = None) -> tuple[dict, str]:
    raw = "hs_" + secrets.token_urlsafe(32)
    key_id = db.new_id("key")
    db.insert("api_keys", {
        "id": key_id,
        "user_id": user_id,
        "name": name or "Clave sin nombre",
        "prefix": raw[:11],
        "key_hash": hashlib.sha256(raw.encode()).hexdigest(),
        "scopes": scopes or ["*"],
        "created_at": db.now(),
    })
    record = db.row_to_dict(db.get("api_keys", key_id))
    assert record is not None
    record.pop("key_hash", None)
    return record, raw


def user_from_api_key(raw: str) -> dict[str, Any] | None:
    digest = hashlib.sha256(raw.encode()).hexdigest()
    row = db.query_one(
        "SELECT u.*, k.id AS key_id FROM api_keys k JOIN users u ON u.id = k.user_id "
        "WHERE k.key_hash = ? AND k.revoked = 0",
        (digest,),
    )
    user = db.row_to_dict(row)
    if user:
        db.update("api_keys", user.pop("key_id"), {"last_used_at": db.now()})
    return user


# ------------------------- Dependencias FastAPI -------------------------

def _resolve(request: Request) -> dict[str, Any] | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token.startswith("hs_"):
            return user_from_api_key(token)
        return user_from_session(token)
    if token := request.cookies.get(SESSION_COOKIE):
        return user_from_session(token)
    return None


async def current_user(request: Request) -> dict[str, Any]:
    user = _resolve(request)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Hace falta iniciar sesión")
    user.pop("password_hash", None)
    return user


async def optional_user(request: Request) -> dict[str, Any] | None:
    user = _resolve(request)
    if user:
        user.pop("password_hash", None)
    return user


async def admin_user(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if not user.get("is_admin"):
        raise HTTPException(403, "Solo para administradores")
    return user


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    """Versión segura para enviar al cliente."""
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user.get("name", ""),
        "avatar_url": user.get("avatar_url"),
        "plan": user.get("plan", "free"),
        "credits": user.get("credits", 0),
        "is_admin": bool(user.get("is_admin")),
        "prefs": user.get("prefs", {}),
        "created_at": user.get("created_at"),
    }
