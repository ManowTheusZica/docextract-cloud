# DocExtract Cloud

![CI](https://github.com/ManowTheusZica/docextract-cloud/actions/workflows/ci.yml/badge.svg) ![Python](https://img.shields.io/badge/python-3.12+-3776AB?logo=python&logoColor=white)

API que recebe um PDF/documento, extrai campos brasileiros (CPF, CNPJ, SEI, PA, CEP,
placa, datas) e devolve JSON estruturado com confianca por campo. Multi-usuario, com
autenticacao, historico, fila de processamento, metricas Prometheus e benchmark.

## O que funciona

- Cadastro e login com JWT (PBKDF2-SHA256 com salt por usuario)
- Upload e extracao com campos + score de confianca por campo
- Isolamento por usuario: cada um so ve os proprios documentos
- Fila em tres modos: `inline`, `thread` e **`redis`** (worker separado, escalavel)
- Worker sem estado: `python -m app.worker` (sobe quantas replicas quiser)
- `/metrics` no formato Prometheus (latencia por rota, uploads por tipo, resultado
  da extracao, profundidade da fila) - sem dependencia de `prometheus_client`
- `/jobs` e `/jobs/resumo` para painel e alerta (contagem por status, taxa de erro)
- 30 testes automatizados (`pytest`)
- `docker-compose` com API + Postgres + Redis + 2 workers + Prometheus
- Benchmark real medido: **p95 do upload cai de 923 ms para 474 ms** ao tirar a
  extracao do caminho da request ([docs/BENCHMARK.md](docs/BENCHMARK.md))

## Rodando

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Modo simples (sem Postgres/Redis), so para testar:

```bash
DATABASE_URL=sqlite:///./local.db QUEUE_MODE=inline uvicorn app.main:app --port 8000
```

Com fila de verdade:

```bash
docker compose up -d db redis
DATABASE_URL=postgresql+psycopg://docextract:docextract@localhost:5432/docextract \
QUEUE_MODE=redis REDIS_URL=redis://localhost:6379/0 uvicorn app.main:app --port 8000
QUEUE_MODE=redis REDIS_URL=redis://localhost:6379/0 python -m app.worker
```

## Endpoints

- `GET  /health` - status do servico e modo da fila
- `GET  /metrics` - metricas Prometheus
- `POST /auth/register` - cria usuario
- `POST /auth/login` - devolve token JWT
- `POST /documents` - upload (multipart), responde `202`
- `GET  /documents` - lista documentos do usuario (paginado)
- `GET  /documents/{id}` - detalhe com campos extraidos
- `GET  /documents/{id}/job` - job daquele documento
- `GET  /jobs` - fila do usuario (`?status=queued|running|done|error`)
- `GET  /jobs/resumo` - contagem por status + taxa de erro

## Exemplo

```bash
TOKEN=$(curl -s -X POST localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"a@b.com","senha":"senha123"}' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

curl -s -X POST localhost:8000/documents \
  -H "Authorization: Bearer $TOKEN" \
  -F "arquivo=@oficio.pdf"
```

## Metricas (amostra real do `/metrics`)

```
docextract_http_requisicoes_total{metodo="POST",rota="/documents",status="202"} 20
docextract_http_duracao_segundos_bucket{rota="/documents",le="0.5"} 18
docextract_documentos_total{tipo="txt"} 20
docextract_fila_pendentes 0
```

## Decisoes que valem explicar em entrevista

- **Extracao por camadas**: PDF com camada de texto usa `pypdf`; quando nao ha texto,
  cai para OCR. Sempre retorna o que conseguiu, com confianca, em vez de falhar inteiro.
- **Mascara antes da regex**: o numero SEI e mascarado antes de procurar CPF; sem isso
  `140.00386388/2026-87` virava falso positivo de CPF.
- **Fila por lista no Redis (`RPUSH`/`BLPOP`)** em vez de Celery: o payload e um JSON
  com o arquivo em base64, o worker fica sem estado e o restart dele nao perde trabalho.
  Celery traria broker + result backend + serializador para resolver um problema que
  aqui tem 40 linhas; se a carga crescer, o adapter e este arquivo.
- **Metricas a mao**: o formato de texto do Prometheus e simples e testavel; a API
  ficou sem dependencia extra e a contagem de requests ficou coberta por teste.
- **`/metrics` fora do rate limit e fora das proprias metricas**: senao o scrape do
  Prometheus infla o histograma e envenena o p95.
- **Benchmark versionado**: `bench/load.py` roda o mesmo cenario em qualquer modo de
  fila; a comparacao inline x thread esta em `docs/BENCHMARK.md`.

## Estrutura

```
app/
  config.py        variaveis de ambiente
  database.py      engine SQLAlchemy e sessao
  security.py      hash de senha e JWT
  extraction.py    texto do PDF (pypdf + fallback)
  fields.py        regex e validacao de campos brasileiros
  metrics.py       contadores/histograma + exposicao Prometheus
  queueing.py      pipeline e publicacao (inline | thread | redis)
  queue_redis.py   publicar / consumir / profundidade
  worker.py        consumidor da fila
  models.py        User, Document, DocumentField, Job
  main.py          app, rate limit, metricas, lifespan
  routers/         auth.py, documents.py, jobs.py
bench/             load.py (carga sem dependencia) e k6_upload.js
observability/     prometheus.yml
tests/             30 testes
```

## Proximos passos

- Painel web para upload em lote consumindo `/jobs`
- Alertas no Prometheus (fila crescendo, taxa de erro)
- Deploy em VPS com CI/CD publicando imagem no GHCR
