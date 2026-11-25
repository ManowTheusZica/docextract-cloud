"""Carga sintetica sem dependencia externa (alternativa ao k6).

Uso:
  python bench/load.py --base http://127.0.0.1:8000 --workers 30 --por-worker 10

Cada worker registra um usuario, envia documentos e espera o job virar
"ready". No fim imprime p50/p95/p99 do upload e a vazao em req/s.
Serve para comparar inline x redis x N workers - o mesmo script mede os tres.
"""
from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
import urllib.error
import urllib.request
import uuid

CORPO = ("Processo SEI 1234.5678/2026-00\nCPF 435.004.468-09\n" * 100).encode()


def requisicao(metodo, url, dados=None, headers=None, tipo="application/json"):
    req = urllib.request.Request(url, data=dados, method=metodo)
    for chave, valor in (headers or {}).items():
        req.add_header(chave, valor)
    if dados is not None:
        req.add_header("Content-Type", tipo)
    try:
        with urllib.request.urlopen(req, timeout=30) as resposta:
            return resposta.status, resposta.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def multipart(nome, conteudo, tipo="text/plain"):
    fronteira = "----carga" + uuid.uuid4().hex
    corpo = (
        ("--%s\r\n" % fronteira).encode()
        + ('Content-Disposition: form-data; name="arquivo"; filename="%s"\r\n' % nome).encode()
        + ("Content-Type: %s\r\n\r\n" % tipo).encode()
        + conteudo
        + ("\r\n--%s--\r\n" % fronteira).encode()
    )
    return corpo, "multipart/form-data; boundary=%s" % fronteira


def um_usuario(base, latencias, erros, indice):
    email = "carga-%d-%s@exemplo.com" % (indice, uuid.uuid4().hex[:8])
    senha = "senha-forte-123"
    requisicao("POST", base + "/auth/register", json.dumps({"email": email, "password": senha}).encode())
    status, corpo = requisicao(
        "POST", base + "/auth/login", json.dumps({"email": email, "password": senha}).encode()
    )
    if status != 200:
        erros.append("login %d" % status)
        return
    token = json.loads(corpo)["access_token"]
    cabecalhos = {"Authorization": "Bearer " + token}

    corpo_mp, tipo = multipart("relatorio.txt", CORPO)
    comeco = time.perf_counter()
    status, resposta = requisicao("POST", base + "/documents", corpo_mp, cabecalhos, tipo)
    duracao = time.perf_counter() - comeco
    if status != 202:
        erros.append("upload %d" % status)
        return
    latencias["upload"].append(duracao)

    doc_id = json.loads(resposta)["id"]
    comeco = time.perf_counter()
    for _ in range(40):
        status, corpo = requisicao("GET", base + "/documents/%d" % doc_id, headers=cabecalhos)
        if status == 200 and json.loads(corpo)["status"] in ("ready", "sem_texto", "error"):
            latencias["job"].append(time.perf_counter() - comeco)
            return
        time.sleep(0.05)
    erros.append("timeout no job")


def percentil(valores, p):
    if not valores:
        return 0.0
    ordenado = sorted(valores)
    posicao = min(len(ordenado) - 1, int(round((p / 100.0) * (len(ordenado) - 1))))
    return ordenado[posicao] * 1000.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--workers", type=int, default=30)
    parser.add_argument("--por-worker", type=int, default=1)
    args = parser.parse_args()

    latencias = {"upload": [], "job": []}
    erros: list[str] = []
    inicio = time.perf_counter()

    threads = []
    for i in range(args.workers * args.por_worker):
        t = threading.Thread(target=um_usuario, args=(args.base, latencias, erros, i))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()
    total = time.perf_counter() - inicio

    enviados = len(latencias["upload"])
    print("usuarios: %d | documentos aceitos: %d | erros: %d" % (args.workers * args.por_worker, enviados, len(erros)))
    print("tempo total: %.2fs | vazao: %.1f documentos/s" % (total, enviados / total if total else 0))
    for chave, rotulo in (("upload", "upload"), ("job", "fila ate pronto")):
        valores = latencias[chave]
        if not valores:
            continue
        print(
            "%s: media %.0f ms | p50 %.0f | p95 %.0f | p99 %.0f | max %.0f"
            % (
                rotulo,
                statistics.mean(valores) * 1000,
                percentil(valores, 50),
                percentil(valores, 95),
                percentil(valores, 99),
                max(valores) * 1000,
            )
        )
    if erros:
        print("amostra de erros:", erros[:5])


if __name__ == "__main__":
    main()
