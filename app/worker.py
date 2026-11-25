"""Worker da fila: consome do Redis e roda o mesmo pipeline da API.

Rodar:  python -m app.worker            (loop infinito)
        python -m app.worker --uma-vez  (processa 1 e sai, usado em teste)

O worker fica sem estado: documento e conteudo vem na mensagem, o banco
compartilhado guarda o resultado. Escalar e' subir mais replicas.
"""
from __future__ import annotations

import argparse
import logging
import sys

from .config import settings
from .database import init_db
from .metrics import registro
from .queue_redis import consumir
from .queueing import process_document

log = logging.getLogger("docextract.worker")


def rodar(uma_vez: bool = False, timeout: int = 5) -> int:
    if settings.queue_mode != "redis":
        log.warning("QUEUE_MODE=%s; o worker so faz sentido com redis", settings.queue_mode)
        return 0

    init_db()
    processados = 0
    while True:
        tarefa = consumir(timeout=timeout)
        if tarefa is None:
            if uma_vez:
                return processados
            continue
        document_id, conteudo = tarefa
        log.info("processando documento %s (%d bytes)", document_id, len(conteudo))
        process_document(document_id, conteudo)
        processados += 1
        registro.extracoes.inc(resultado="worker")
        if uma_vez:
            return processados


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Worker da fila do DocExtract")
    parser.add_argument("--uma-vez", action="store_true", help="processa um trabalho e sai")
    parser.add_argument("--timeout", type=int, default=5, help="segundos de espera por trabalho")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    return rodar(uma_vez=args.uma_vez, timeout=args.timeout)


if __name__ == "__main__":      # pragma: no cover
    sys.exit(main())
