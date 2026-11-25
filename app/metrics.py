"""Metricas no formato de exposicao do Prometheus, sem dependencia externa.

Por que nao usar prometheus_client: a API precisa de 4 tipos (counter,
gauge, histogram) e o formato de texto e' simples. Escrever aqui deixa o
registro testavel e o container 3 MB menor. Se o projeto crescer, trocar
por prometheus_client e' um adapter deste modulo.
"""
from __future__ import annotations

import threading
from collections import defaultdict

BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


class _Base:
    def __init__(self, nome: str, ajuda: str, labels: tuple[str, ...] = ()):
        self.nome = nome
        self.ajuda = ajuda
        self.labels = labels
        self._lock = threading.Lock()

    def _chave(self, rotulos: dict) -> tuple[str, ...]:
        faltando = [rotulo for rotulo in self.labels if rotulo not in rotulos]
        if faltando:
            raise ValueError(
                "%s espera %d labels (%s), faltou: %s"
                % (self.nome, len(self.labels), ",".join(self.labels) or "-", ",".join(faltando))
            )
        return tuple(rotulos[rotulo] for rotulo in self.labels)

    def _rotulos(self, chave: tuple[str, ...]) -> str:
        if not self.labels:
            return ""
        pares = ",".join('%s="%s"' % (k, v) for k, v in zip(self.labels, chave))
        return "{%s}" % pares


class Counter(_Base):
    def __init__(self, nome: str, ajuda: str, labels: tuple[str, ...] = ()):
        super().__init__(nome, ajuda, labels)
        self._valores: dict[tuple[str, ...], float] = defaultdict(float)

    def inc(self, valor: float = 1.0, **rotulos: str) -> None:
        chave = self._chave(rotulos)
        with self._lock:
            self._valores[chave] += valor

    def valor(self, **rotulos: str) -> float:
        chave = self._chave(rotulos)
        return self._valores.get(chave, 0.0)

    def linhas(self) -> list[str]:
        saida = ["# HELP %s %s" % (self.nome, self.ajuda), "# TYPE %s counter" % self.nome]
        with self._lock:
            itens = sorted(self._valores.items())
        for chave, valor in itens:
            saida.append("%s%s %s" % (self.nome, self._rotulos(chave), _num(valor)))
        if not itens:
            saida.append("%s 0" % self.nome)
        return saida


class Gauge(_Base):
    """Gauge alimentado por uma funcao no momento da coleta (pull)."""

    def __init__(self, nome: str, ajuda: str, coletor, labels: tuple[str, ...] = ()):
        super().__init__(nome, ajuda, labels)
        self._coletor = coletor

    def linhas(self) -> list[str]:
        saida = ["# HELP %s %s" % (self.nome, self.ajuda), "# TYPE %s gauge" % self.nome]
        dados = self._coletor() or {}
        for chave, valor in sorted(dados.items()):
            if isinstance(chave, str) and self.labels:
                chave = (chave,)
            saida.append("%s%s %s" % (self.nome, self._rotulos(tuple(chave) if isinstance(chave, tuple) else ()), _num(valor)))
        return saida


class Histogram(_Base):
    def __init__(self, nome: str, ajuda: str, labels: tuple[str, ...] = (), buckets=BUCKETS):
        super().__init__(nome, ajuda, labels)
        self.buckets = tuple(sorted(buckets))
        self._baldes: dict[tuple[str, ...], list[int]] = defaultdict(lambda: [0] * len(self.buckets))
        self._soma: dict[tuple[str, ...], float] = defaultdict(float)
        self._contagem: dict[tuple[str, ...], int] = defaultdict(int)

    def observe(self, valor: float, **rotulos: str) -> None:
        chave = self._chave(rotulos)
        with self._lock:
            baldes = self._baldes[chave]
            for i, limite in enumerate(self.buckets):
                if valor <= limite:
                    baldes[i] += 1
            self._soma[chave] += valor
            self._contagem[chave] += 1

    def valor(self, **rotulos: str) -> tuple[int, float]:
        chave = self._chave(rotulos)
        return self._contagem.get(chave, 0), self._soma.get(chave, 0.0)

    def linhas(self) -> list[str]:
        saida = ["# HELP %s %s" % (self.nome, self.ajuda), "# TYPE %s histogram" % self.nome]
        with self._lock:
            chaves = sorted(self._baldes)
        for chave in chaves:
            baldes = self._baldes[chave]
            for i, limite in enumerate(self.buckets):
                saida.append('%s_bucket%s %d' % (
                    self.nome,
                    self._rotulos_com_le(chave, 'le="%s"' % _num(limite)),
                    baldes[i],
                ))
            saida.append('%s_bucket%s %d' % (
                self.nome,
                self._rotulos_com_le(chave, 'le="+Inf"'),
                self._contagem[chave],
            ))
            saida.append("%s_sum%s %s" % (self.nome, self._rotulos(chave), _num(self._soma[chave])))
            saida.append("%s_count%s %d" % (self.nome, self._rotulos(chave), self._contagem[chave]))
        return saida

    def _rotulos_com_le(self, chave: tuple[str, ...], le: str) -> str:
        pares = ['%s="%s"' % (k, v) for k, v in zip(self.labels, chave)]
        pares.append(le)
        return "{%s}" % ",".join(pares)


def _num(valor: float) -> str:
    if isinstance(valor, int) or float(valor).is_integer():
        return str(int(valor))
    return ("%.6f" % valor).rstrip("0").rstrip(".")


class Registro:
    def __init__(self) -> None:
        self.http_requisicoes = Counter(
            "docextract_http_requisicoes_total",
            "Requisicoes HTTP por metodo, rota e status",
            ("metodo", "rota", "status"),
        )
        self.http_duracao = Histogram(
            "docextract_http_duracao_segundos",
            "Latencia das requisicoes HTTP",
            ("rota",),
        )
        self.documentos = Counter(
            "docextract_documentos_total",
            "Documentos enviados por tipo de arquivo",
            ("tipo",),
        )
        self.extracoes = Counter(
            "docextract_extracoes_total",
            "Resultado da extracao",
            ("resultado",),
        )
        self.fila = Counter(
            "docextract_fila_publicados_total",
            "Trabalhos publicados na fila",
            ("modo",),
        )
        self.fila_espera = Gauge(
            "docextract_fila_pendentes",
            "Trabalhos pendentes na fila (consulta no Redis)",
            self._ler_fila,
        )

    def _ler_fila(self) -> dict:
        from .config import settings

        if settings.queue_mode != "redis":
            return {"redis": 0}
        try:
            from .queue_redis import profundidade_fila

            return {"redis": profundidade_fila()}
        except Exception:      # pragma: no cover - Redis fora do ar nao derruba a API
            return {"redis": -1}

    def expor(self) -> str:
        linhas: list[str] = []
        for coletor in (
            self.http_requisicoes,
            self.http_duracao,
            self.documentos,
            self.extracoes,
            self.fila,
            self.fila_espera,
        ):
            linhas.extend(coletor.linhas())
        return "\n".join(linhas) + "\n"


registro = Registro()
