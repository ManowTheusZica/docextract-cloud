"""Fila em Redis: a API publica, o worker consome.

Formato da mensagem: JSON com document_id e o conteudo em base64.
Guardar o conteudo na fila (e nao no disco) mantem o worker sem estado:
ele pode rodar em outra maquina, e reiniciar o processo nao perde trabalho.

Chave: LPUSH/RPOP na lista `docextract:fila` (FIFO).
"""
from __future__ import annotations

import base64
import json

from .config import settings


def _redis():
    import redis

    return redis.Redis.from_url(settings.redis_url, decode_responses=False)


def publicar(document_id: int, conteudo: bytes) -> None:
    """Enfileira um documento. Levanta RedisError se o Redis estiver fora."""
    mensagem = json.dumps(
        {
            "document_id": document_id,
            "conteudo": base64.b64encode(conteudo).decode("ascii"),
        }
    )
    _redis().rpush(settings.queue_name, mensagem)


def consumir(timeout: int = 5) -> tuple[int, bytes] | None:
    """Bloqueia ate' `timeout` segundos esperando um trabalho.

    Retorna (document_id, conteudo) ou None se a fila estava vazia.
    """
    bruto = _redis().blpop([settings.queue_name], timeout=timeout)
    if not bruto:
        return None
    _, valor = bruto
    dados = json.loads(valor)
    return int(dados["document_id"]), base64.b64decode(dados["conteudo"])


def profundidade_fila() -> int:
    return int(_redis().llen(settings.queue_name))
