"""Autenticacao sem dependencia externa: scrypt para senha, JWT HS256 na mao."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

_bearer = HTTPBearer(auto_error=False)
_B64 = base64.urlsafe_b64encode


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$%s$%s" % (
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algoritmo, salt_b64, digest_b64 = stored.split("$")
        if algoritmo != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        esperado = base64.b64decode(digest_b64)
        obtido = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
        return hmac.compare_digest(esperado, obtido)
    except Exception:
        return False


def _b64url(data: bytes) -> str:
    return _B64(data).rstrip(b"=").decode()


def _unb64url(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def create_token(user_id: int, *, minutos: int | None = None) -> str:
    minutos = minutos or settings.token_minutes
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(
        json.dumps({"sub": str(user_id), "exp": int(time.time()) + minutos * 60}).encode()
    )
    assinatura = hmac.new(
        settings.secret_key.encode(), f"{header}.{payload}".encode(), hashlib.sha256
    ).digest()
    return f"{header}.{payload}.{_b64url(assinatura)}"


def decode_token(token: str) -> dict:
    try:
        header, payload, assinatura = token.split(".")
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token malformado")

    esperado = hmac.new(
        settings.secret_key.encode(), f"{header}.{payload}".encode(), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(esperado, _unb64url(assinatura)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Assinatura invalida")

    dados = json.loads(_unb64url(payload))
    if int(dados.get("exp", 0)) < int(time.time()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expirado")
    return dados


def get_current_user(
    credenciais: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credenciais is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Informe o token: Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    dados = decode_token(credenciais.credentials)
    usuario = db.get(User, int(dados["sub"]))
    if usuario is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario nao existe")
    return usuario
