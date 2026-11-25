from __future__ import annotations

import math

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Document, Job, User
from ..queueing import hash_conteudo, submit
from ..schemas import DocumentOut, JobOut
from ..security import get_current_user

router = APIRouter(prefix="/documents", tags=["documents"])

TIPOS_ACEITOS = (".pdf", ".txt", ".csv", ".md")


@router.post("", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
def enviar(
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario: User = Depends(get_current_user),
):
    nome = arquivo.filename or "arquivo"
    if not nome.lower().endswith(TIPOS_ACEITOS):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Formato nao suportado. Envie PDF ou TXT.",
        )

    conteudo = arquivo.file.read()
    limite = settings.max_upload_mb * 1024 * 1024
    if len(conteudo) > limite:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "Arquivo maior que %d MB" % settings.max_upload_mb,
        )
    if not conteudo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Arquivo vazio")

    documento = Document(
        user_id=usuario.id,
        filename=nome,
        sha256=hash_conteudo(conteudo),
        size_bytes=len(conteudo),
        status="queued",
    )
    db.add(documento)
    db.commit()
    db.refresh(documento)

    db.add(Job(document_id=documento.id, status="queued"))
    db.commit()

    from ..metrics import registro

    registro.documentos.inc(tipo=nome.rsplit(".", 1)[-1].lower())
    submit(documento.id, conteudo)

    db.refresh(documento)
    return documento


@router.get("", response_model=list[DocumentOut])
def listar(
    db: Session = Depends(get_db),
    usuario: User = Depends(get_current_user),
    limite: int = Query(20, ge=1, le=100),
    pagina: int = Query(1, ge=1),
):
    consulta = (
        select(Document)
        .where(Document.user_id == usuario.id)
        .order_by(Document.id.desc())
        .offset((pagina - 1) * limite)
        .limit(limite)
    )
    return list(db.execute(consulta).scalars())


@router.get("/{documento_id}", response_model=DocumentOut)
def detalhar(
    documento_id: int,
    db: Session = Depends(get_db),
    usuario: User = Depends(get_current_user),
):
    documento = db.get(Document, documento_id)
    if documento is None or documento.user_id != usuario.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento nao encontrado")
    return documento


@router.get("/{documento_id}/job", response_model=JobOut)
def trabalho(
    documento_id: int,
    db: Session = Depends(get_db),
    usuario: User = Depends(get_current_user),
):
    documento = db.get(Document, documento_id)
    if documento is None or documento.user_id != usuario.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento nao encontrado")
    tarefa = db.execute(select(Job).where(Job.document_id == documento_id)).scalar_one_or_none()
    if tarefa is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job nao encontrado")
    return tarefa


@router.delete("/{documento_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(
    documento_id: int,
    db: Session = Depends(get_db),
    usuario: User = Depends(get_current_user),
):
    documento = db.get(Document, documento_id)
    if documento is None or documento.user_id != usuario.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento nao encontrado")
    db.delete(documento)
    db.commit()
