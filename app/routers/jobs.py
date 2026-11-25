"""Monitoracao da fila: o que o painel/alertas consomem.

Nao existe "reprocessar" aqui porque o conteudo do arquivo nao fica
guardado (so' o hash) - reenviar o arquivo e' o caminho honesto e barato.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Document, Job, User
from ..schemas import JobOut
from ..security import get_current_user

router = APIRouter(prefix="/jobs", tags=["jobs"])

STATUS_VALIDOS = ("queued", "running", "done", "error")


@router.get("", response_model=list[JobOut])
def listar(
    status_filtro: str | None = Query(None, alias="status"),
    limite: int = Query(50, ge=1, le=200),
    pagina: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    usuario: User = Depends(get_current_user),
):
    consulta = (
        select(Job)
        .join(Document, Document.id == Job.document_id)
        .where(Document.user_id == usuario.id)
        .order_by(Job.id.desc())
        .offset((pagina - 1) * limite)
        .limit(limite)
    )
    if status_filtro:
        if status_filtro not in STATUS_VALIDOS:
            from fastapi import HTTPException, status as codigos

            raise HTTPException(codigos.HTTP_400_BAD_REQUEST, "status invalido")
        consulta = consulta.where(Job.status == status_filtro)
    return list(db.execute(consulta).scalars())


@router.get("/resumo")
def resumo(db: Session = Depends(get_db), usuario: User = Depends(get_current_user)):
    """Contagem por status do usuario logado - usado no painel."""
    linhas = db.execute(
        select(Job.status, func.count(Job.id))
        .join(Document, Document.id == Job.document_id)
        .where(Document.user_id == usuario.id)
        .group_by(Job.status)
    ).all()
    contagem = {status: 0 for status in STATUS_VALIDOS}
    for status, total in linhas:
        contagem[status] = total
    return {
        "por_status": contagem,
        "total": sum(contagem.values()),
        "pendentes": contagem["queued"] + contagem["running"],
        "taxa_erro": (contagem["error"] / sum(contagem.values())) if sum(contagem.values()) else 0.0,
    }
