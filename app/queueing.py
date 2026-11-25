"""Processamento de documentos: inline (testes/dev) ou thread (API local).

Em producao com mais de uma replica, use QUEUE_MODE=redis: a API publica na
lista do Redis e o worker (`python -m app.worker`) consome. `process_document`
continua sendo a unica fonte de verdade do pipeline.
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
from .metrics import registro
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
            registro.extracoes.inc(resultado=documento.status)
        except ExtracaoError as exc:
            documento.status = "error"
            documento.error = str(exc)
            if trabalho:
                trabalho.status = "error"
                trabalho.error = str(exc)
                trabalho.finished_at = datetime.now(timezone.utc)
            registro.extracoes.inc(resultado="erro")
        except Exception as exc:  # pragma: no cover - salvaguarda
            log.exception("falha inesperada no documento %s", document_id)
            documento.status = "error"
            documento.error = "falha interna: %s" % exc
            if trabalho:
                trabalho.status = "error"
                trabalho.error = str(exc)
                trabalho.finished_at = datetime.now(timezone.utc)
            registro.extracoes.inc(resultado="falha_interna")

        db.commit()
    finally:
        db.close()


def submit(document_id: int, conteudo: bytes) -> None:
    """Publica o trabalho conforme QUEUE_MODE: inline, thread ou redis."""
    modo = settings.queue_mode
    if modo == "thread":
        _executor.submit(process_document, document_id, conteudo)
    elif modo == "redis":
        from .queue_redis import publicar

        publicar(document_id, conteudo)
    else:
        process_document(document_id, conteudo)
    registro.fila.inc(modo=modo)


def hash_conteudo(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()
