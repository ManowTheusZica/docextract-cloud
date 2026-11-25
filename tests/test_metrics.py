"""Testes das metricas: formato do Prometheus e contagem correta."""
from __future__ import annotations

from app.metrics import BUCKETS, Counter, Histogram, Registro


def test_contador_simples():
    c = Counter("teste_total", "ajuda")
    c.inc()
    c.inc(2)
    assert c.valor() == 3
    linhas = c.linhas()
    assert "# TYPE teste_total counter" in linhas
    assert "teste_total 3" in linhas


def test_contador_com_label():
    c = Counter("teste_rotulado_total", "ajuda", ("modo",))
    c.inc(modo="redis")
    c.inc(3, modo="redis")
    c.inc(modo="thread")
    assert c.valor(modo="redis") == 4
    assert c.valor(modo="thread") == 1
    texto = "\n".join(c.linhas())
    assert 'teste_rotulado_total{modo="redis"} 4' in texto
    assert 'teste_rotulado_total{modo="thread"} 1' in texto


def test_label_faltando_levanta_erro():
    c = Counter("teste_erro_total", "ajuda", ("modo",))
    try:
        c.inc()
    except ValueError as exc:
        assert "espera 1 labels" in str(exc)
    else:                                   # pragma: no cover
        raise AssertionError("deveria ter levantado ValueError")


def test_histograma_buckets_acumulados():
    h = Histogram("teste_duracao_segundos", "ajuda")
    for valor in (0.003, 0.02, 0.3, 7.0):
        h.observe(valor)
    contagem, soma = h.valor()
    assert contagem == 4
    assert abs(soma - 7.323) < 1e-9

    texto = "\n".join(h.linhas())
    # 4 amostras <= 10s e nenhuma acima de 10
    assert 'teste_duracao_segundos_bucket{le="10"} 4' in texto
    assert 'teste_duracao_segundos_bucket{le="+Inf"} 4' in texto
    assert "teste_duracao_segundos_count 4" in texto
    # o bucket de 5s ja' pegou 3 das 4 amostras (7.0 ficou de fora)
    assert 'teste_duracao_segundos_bucket{le="5"} 3' in texto
    assert len(h.buckets) == len(BUCKETS)


def test_histograma_com_label_emite_le():
    h = Histogram("teste_lat_segundos", "ajuda", ("rota",), buckets=(0.1, 1.0))
    h.observe(0.05, rota="/documents")
    texto = "\n".join(h.linhas())
    assert 'teste_lat_segundos_bucket{rota="/documents",le="0.1"} 1' in texto


def test_registro_expoe_todos_os_coletores():
    texto = Registro().expor()
    for nome in (
        "docextract_http_requisicoes_total",
        "docextract_http_duracao_segundos",
        "docextract_documentos_total",
        "docextract_extracoes_total",
        "docextract_fila_publicados_total",
        "docextract_fila_pendentes",
    ):
        assert nome in texto
    assert texto.endswith("\n")
