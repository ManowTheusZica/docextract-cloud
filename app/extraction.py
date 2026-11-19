"""Extracao de texto: PDF (com camada de texto), TXT e fallback de OCR documentado."""
from __future__ import annotations

import io


class ExtracaoError(Exception):
    pass


def texto_de_pdf(dados: bytes) -> tuple[str, int]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - depende do ambiente
        raise ExtracaoError("pypdf nao instalado: pip install pypdf") from exc

    try:
        leitor = PdfReader(io.BytesIO(dados))
    except Exception as exc:
        raise ExtracaoError("PDF invalido ou protegido: %s" % exc) from exc

    paginas = []
    for pagina in leitor.pages:
        try:
            paginas.append(pagina.extract_text() or "")
        except Exception:
            paginas.append("")
    return "\n".join(paginas), len(leitor.pages)


def texto_de_txt(dados: bytes) -> tuple[str, int]:
    for codificacao in ("utf-8", "latin-1"):
        try:
            return dados.decode(codificacao), 1
        except UnicodeDecodeError:
            continue
    raise ExtracaoError("Nao consegui decodificar o texto do arquivo")


def extrair_texto(nome_arquivo: str, dados: bytes) -> tuple[str, int]:
    """Devolve (texto, paginas). PDF sem camada de texto volta vazio - use OCR."""
    nome = (nome_arquivo or "").lower()
    if nome.endswith(".pdf"):
        return texto_de_pdf(dados)
    if nome.endswith((".txt", ".csv", ".md")):
        return texto_de_txt(dados)
    raise ExtracaoError("Formato nao suportado: use PDF ou TXT")
