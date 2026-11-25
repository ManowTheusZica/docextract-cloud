from __future__ import annotations

import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from .config import settings
from .database import init_db
from .metrics import registro
from .routers import auth, documents, jobs


def limite_estourado(janela: list[float], limite: int, agora: float) -> bool:
    """True se o cliente ja usou o limite dentro da janela de 60s."""
    recentes = [t for t in janela if agora - t <= 60]
    janela[:] = recentes
    return len(recentes) >= limite


def rota_normalizada(request: Request) -> str:
    """Troca ids por {} para nao explodir a cardinalidade das metricas."""
    rota = request.scope.get("route")
    caminho = getattr(rota, "path", None) or request.url.path
    partes = []
    for parte in caminho.split("/"):
        partes.append("{}" if parte.isdigit() else parte)
    return "/".join(partes)


@asynccontextmanager
async def _ciclo_de_vida(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        lifespan=_ciclo_de_vida,
        title="DocExtract Cloud",
        description="API de extracao de campos de documentos com fila, auth e testes.",
        version="0.2.0",
    )

    _historico: dict[str, deque] = defaultdict(deque)

    @app.middleware("http")
    async def instrumentacao(request: Request, call_next):
        if request.url.path in ("/health", "/docs", "/openapi.json", "/metrics"):
            return await call_next(request)

        cliente = request.client.host if request.client else "anon"
        agora = time.time()
        janela = _historico[cliente]
        while janela and agora - janela[0] > 60:
            janela.popleft()
        if limite_estourado(list(janela), settings.rate_limit_per_minute, agora):
            registro.http_requisicoes.inc(metodo=request.method, rota="limite", status="429")
            return JSONResponse(
                status_code=429,
                content={"detail": "Muitas requisicoes. Tente de novo em 1 minuto."},
            )
        janela.append(agora)

        comeco = time.perf_counter()
        resposta = await call_next(request)
        duracao = time.perf_counter() - comeco
        rota = rota_normalizada(request)
        registro.http_requisicoes.inc(
            metodo=request.method, rota=rota, status=str(resposta.status_code)
        )
        registro.http_duracao.observe(duracao, rota=rota)
        return resposta

    @app.get("/health", tags=["infra"])
    def health():
        return {"status": "ok", "versao": app.version, "fila": settings.queue_mode}

    @app.get("/metrics", tags=["infra"], response_class=PlainTextResponse)
    def metrics():
        """Formato de exposicao do Prometheus (pode ser raspado direto)."""
        return PlainTextResponse(registro.expor(), media_type="text/plain; version=0.0.4")

    app.include_router(auth.router)
    app.include_router(documents.router)
    app.include_router(jobs.router)
    return app


app = create_app()
