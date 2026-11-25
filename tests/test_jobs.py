"""Testes dos endpoints de fila e da fila em Redis (com Redis falso)."""
from __future__ import annotations

import base64
import json

import pytest

from app import queue_redis


class RedisFalso:
    """Mini Redis em memoria: o suficiente para rpush/blpop/llen."""

    def __init__(self):
        self.listas: dict[str, list[bytes]] = {}

    def rpush(self, chave, valor):
        self.listas.setdefault(chave, []).append(valor)
        return len(self.listas[chave])

    def blpop(self, chaves, timeout=0):
        for chave in chaves:
            fila = self.listas.get(chave) or []
            if fila:
                return chave, fila.pop(0)
        return None

    def llen(self, chave):
        return len(self.listas.get(chave) or [])


@pytest.fixture
def redis_falso(monkeypatch):
    falso = RedisFalso()
    monkeypatch.setattr(queue_redis, "_redis", lambda: falso)
    return falso


def test_publicar_e_consumir_em_ordem(redis_falso):
    queue_redis.publicar(1, b"primeiro")
    queue_redis.publicar(2, b"segundo")
    assert queue_redis.profundidade_fila() == 2

    doc_id, conteudo = queue_redis.consumir(timeout=0)
    assert (doc_id, conteudo) == (1, b"primeiro")
    doc_id, conteudo = queue_redis.consumir(timeout=0)
    assert (doc_id, conteudo) == (2, b"segundo")
    assert queue_redis.profundidade_fila() == 0


def test_consumir_fila_vazia_retorna_none(redis_falso):
    assert queue_redis.consumir(timeout=0) is None


def test_mensagem_carrega_conteudo_binario(redis_falso):
    conteudo = b"%PDF-1.7\x00\xff binario"
    queue_redis.publicar(9, conteudo)
    bruto = redis_falso.listas["docextract:fila"][0]
    dados = json.loads(bruto)
    assert dados["document_id"] == 9
    assert base64.b64decode(dados["conteudo"]) == conteudo


def test_jobs_exige_autenticacao(client):
    assert client.get("/jobs").status_code == 401


def test_jobs_lista_e_resumo(client, usuario):
    arquivo = ("teste.txt", b"Processo SEI 1234.5678/2026-00 CPF 435.004.468-09", "text/plain")
    envio = client.post(
        "/documents", files={"arquivo": arquivo}, headers=usuario["headers"]
    )
    assert envio.status_code == 202, envio.text
    doc_id = envio.json()["id"]

    lista = client.get("/jobs", headers=usuario["headers"])
    assert lista.status_code == 200
    assert any(item["document_id"] == doc_id for item in lista.json())

    filtrado = client.get("/jobs?status=done", headers=usuario["headers"])
    assert filtrado.status_code == 200
    assert all(item["status"] == "done" for item in filtrado.json())

    invalido = client.get("/jobs?status=xxxx", headers=usuario["headers"])
    assert invalido.status_code == 400

    resumo = client.get("/jobs/resumo", headers=usuario["headers"])
    assert resumo.status_code == 200
    corpo = resumo.json()
    assert corpo["total"] >= 1
    assert set(corpo["por_status"]) == {"queued", "running", "done", "error"}
    assert 0.0 <= corpo["taxa_erro"] <= 1.0


def test_metrics_exposto_sem_auth(client):
    resposta = client.get("/metrics")
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/plain")
    corpo = resposta.text
    assert "docextract_http_requisicoes_total" in corpo
    # o /health nao entra nas metricas, o /jobs entra
    assert 'rota="/jobs"' in corpo
    assert "docextract_fila_pendentes" in corpo


def test_metricas_contam_documento_por_tipo(client, usuario):
    arquivo = ("relatorio.md", b"# titulo\nCPF 435.004.468-09", "text/markdown")
    client.post("/documents", files={"arquivo": arquivo}, headers=usuario["headers"])
    corpo = client.get("/metrics").text
    assert 'docextract_documentos_total{tipo="md"}' in corpo
