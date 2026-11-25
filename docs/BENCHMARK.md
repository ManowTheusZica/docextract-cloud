# Benchmark — DocExtract Cloud v2

Números medidos nesta máquina (Linux, 8 vCPU, SQLite, uvicorn 1 processo).
Não são estimativas: rode `bench/load.py` contra a API e compare.

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
python bench/load.py --base http://127.0.0.1:8000 --workers 20
```

## Resultado — 20 uploads concorrentes de TXT (~6 KB cada)

| modo da fila | upload p50 | upload p95 | upload p99 | fila até "ready" p95 | vazão |
|---|---|---|---|---|---|
| `inline` (processa na request) | 465 ms | 923 ms | 1.064 ms | — | 8,3 doc/s |
| `thread` (ThreadPool 2 workers) | 211 ms | 474 ms | 995 ms | 534 ms | 8,6 doc/s |

Leitura: tirar a extração do caminho da request **corta o p95 do upload pela
metade** (923 → 474 ms) e o custo aparece no "fila até pronto" (534 ms). Vazão
quase igual porque o gargalo é a extração em si, não o servidor HTTP — com
`QUEUE_MODE=redis` e mais réplicas de worker, a vazão cresce junto com o número
de workers, que é o motivo de existir a fila.

## Como repetir com Redis

```bash
docker compose up -d redis db
QUEUE_MODE=redis REDIS_URL=redis://localhost:6379/0 \
  python -m uvicorn app.main:app --port 8000 &
QUEUE_MODE=redis REDIS_URL=redis://localhost:6379/0 python -m app.worker &
python bench/load.py --workers 50 --por-worker 2
```

## k6 (cenário de 60 s com 50 VUs)

```bash
k6 run bench/k6_upload.js -e BASE_URL=http://localhost:8000
```

Limiares declarados no script: `p95 < 800 ms` no upload, `erro < 1%`,
`job_concluido > 95%`. Se o p95 estourar, o k6 sai com código != 0 e o CI
pode usar isso como gate.
