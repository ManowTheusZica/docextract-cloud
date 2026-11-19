"""Extracao de campos por regex + validacao de digito verificador."""
from __future__ import annotations

import re

CPF_RE = re.compile(r"\b(\d{3}\.?\d{3}\.?\d{3}-?\d{2})\b")
SEI_RE = re.compile(r"\b(140\.\d{8}/\d{4}-\d{2})\b")
PA_RE = re.compile(r"\b(\d{1,6}/\d{4})\b")
CEP_RE = re.compile(r"\b(\d{5}-?\d{3})\b")
CNH_RE = re.compile(r"(?:CNH|REGISTRO|REG\.?)\s*[:.]?\s*(\d{9,11})", re.IGNORECASE)
NOME_RE = re.compile(
    r"(?:NOME(?:\s+DO\s+CONDUTOR)?|NOME\s+COMPLETO)\s*[:.]?\s*([A-ZÀ-Ú][A-ZÀ-Ú\s]{6,80})"
)
DATA_RE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")


def cpf_valido(cpf: str) -> bool:
    numeros = re.sub(r"\D", "", cpf)
    if len(numeros) != 11 or numeros == numeros[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(numeros[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11 % 10
        if digito != int(numeros[tamanho]):
            return False
    return True


CORTES_NOME = re.compile(
    r"\b(CPF|RG|CNH|REGISTRO|SEI|PA|CEP|DATA|ENDERECO|MUNICIPIO|UF|NASCIMENTO|FILIACAO|MAE|PAI)\b"
)


def _limpar_nome(bruto: str) -> str:
    """Corta o nome no primeiro rotulo que aparecer depois dele."""
    pedaco = CORTES_NOME.split(bruto)[0]
    texto = re.sub(r"\s+", " ", pedaco).strip(" :.-")
    return texto[:80]


def _mascarar_sei(texto: str) -> str:
    """Troca o SEI por espacos para ele nao virar CPF/CEP falso."""
    return SEI_RE.sub(lambda m: " " * len(m.group(0)), texto)


def extrair_campos(texto: str) -> list[dict]:
    """Devolve lista de {key, value, confidence}. Nao inventa: so o que casar."""
    achados: list[dict] = []
    vistos: set[tuple[str, str]] = set()

    def add(chave: str, valor: str, confianca: float) -> None:
        valor = valor.strip()
        if not valor or (chave, valor) in vistos:
            return
        vistos.add((chave, valor))
        achados.append({"key": chave, "value": valor, "confidence": confianca})

    limpo = _mascarar_sei(texto)

    for bruto in CPF_RE.findall(limpo):
        if cpf_valido(bruto):
            add("cpf", re.sub(r"\D", "", bruto), 1.0)
        else:
            add("cpf_invalido", re.sub(r"\D", "", bruto), 0.3)

    for sei in SEI_RE.findall(texto):
        add("sei", sei, 1.0)

    for pa in PA_RE.findall(texto):
        ano = int(pa.split("/")[1])
        if 1990 <= ano <= 2100:
            add("pa", pa, 0.9)

    for cep in CEP_RE.findall(limpo):
        add("cep", re.sub(r"\D", "", cep), 0.9)

    for cnh in CNH_RE.findall(texto):
        add("registro", cnh, 0.85)

    for nome in NOME_RE.findall(texto):
        add("nome", _limpar_nome(nome), 0.8)

    for data in DATA_RE.findall(texto)[:3]:
        add("data", data, 0.6)

    ordem = {"nome": 0, "cpf": 1, "cpf_invalido": 2, "registro": 3, "sei": 4, "pa": 5, "cep": 6, "data": 7}
    return sorted(achados, key=lambda item: (ordem.get(item["key"], 99), item["value"]))
