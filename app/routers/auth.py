from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import Token, UserCreate, UserOut
from ..security import create_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def registrar(dados: UserCreate, db: Session = Depends(get_db)):
    existe = db.execute(select(User).where(User.email == dados.email)).scalar_one_or_none()
    if existe:
        raise HTTPException(status.HTTP_409_CONFLICT, "E-mail ja cadastrado")
    usuario = User(email=dados.email, password_hash=hash_password(dados.password))
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


@router.post("/login", response_model=Token)
def login(dados: UserCreate, db: Session = Depends(get_db)):
    usuario = db.execute(select(User).where(User.email == dados.email)).scalar_one_or_none()
    if usuario is None or not verify_password(dados.password, usuario.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciais invalidas")
    return Token(access_token=create_token(usuario.id))
