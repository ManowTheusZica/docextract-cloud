"""Processamento de documentos: inline (testes/dev) ou thread (API local).

Em producao, o gancho e o mesmo: troque `submit` por um enfileirador
(Celery/RQ/SQS) e mantenha `process_document` como unica fonte de verdade.
"""
from __future__ import annotations

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import select

from .config import settings
from .database import SessionLocal
from .extraction import ExtracaoError, extrair_texto
from .fields import extrair_campos
from .models import Document, DocumentField, Job

log = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="docextract")


def process_document(document_id: int, conteudo: bytes) -> None:
    """Roda o pipeline e atualiza o banco. Nunca levanta excecao."""
    db = SessionLocal()
    try:
        documento = db.get(Document, document_id)
        if documento is None:
            return
        trabalho = db.execute(
            select(Job).where(Job.document_id == document_id)
        ).scalar_one_or_none()

        if trabalho:
            trabalho.status = "running"
            db.commit()

        try:
            texto, paginas = extrair_texto(documento.filename, conteudo)
            campos = extrair_campos(texto)

            documento.pages = paginas
            documento.text_chars = len(texto)
            documento.status = "ready" if texto.strip() else "sem_texto"
            documento.error = None

            db.query(DocumentField).filter(DocumentField.document_id == document_id).delete()
            for campo in campos:
                db.add(
                    DocumentField(
                        document_id=document_id,
                        key=campo["key"],
                        value=campo["value"],
                        confidence=campo["confidence"],
                    )
                )

            if trabalho:
                trabalho.status = "done"
                trabalho.finished_at = datetime.now(timezone.utc)
        except ExtracaoError as exc:
            documento.status = "error"
            documento.error = str(exc)
            if trabalho:
                trabalho.status = "error"
                trabalho.error = str(exc)
                trabalho.finished_at = datetime.now(timezone.utc)
        except Exception as exc:  # pragma: no cover - salvaguarda
            log.exception("falha inesperada no documento %s", document_id)
            documento.status = "error"
            documento.error = "falha interna: %s" % exc
            if trabalho:
                trabalho.status = "error"
                trabalho.error = str(exc)
                trabalho.finished_at = datetime.now(timezone.utc)

        db.commit()
    finally:
        db.close()


def submit(document_id: int, conteudo: bytes) -> None:
    if settings.queue_mode == "thread":
        _executor.submit(process_document, document_id, conteudo)
    else:
        process_document(document_id, conteudo)


def hash_conteudo(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()
