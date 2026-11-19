from app.fields import cpf_valido, extrair_campos

TEXTO = """
DEPARTAMENTO ESTADUAL DE TRANSITO
NOME DO CONDUTOR: MATHEUS AUGUSTO GONCALVES MENDES
CPF: 435.004.468-09
REGISTRO: 03508948972
Processo Administrativo PA: 3/2024
SEI 140.00386388/2026-87
CEP: 01014-010
Data de abertura: 09/08/2024
"""


def test_cpf_valido():
    assert cpf_valido("43500446809")
    assert cpf_valido("435.004.468-09")
    assert not cpf_valido("11111111111")
    assert not cpf_valido("12345678900")
    assert not cpf_valido("123")


def test_extrai_campos_do_documento():
    campos = {c["key"]: c["value"] for c in extrair_campos(TEXTO)}
    assert campos["cpf"] == "43500446809"
    assert campos["sei"] == "140.00386388/2026-87"
    assert campos["pa"] == "3/2024"
    assert campos["cep"] == "01014010"
    assert campos["registro"] == "03508948972"
    assert "MATHEUS" in campos["nome"]


def test_cpf_invalido_nao_vira_cpf():
    texto = "CPF: 123.456.789-00"
    chaves = [c["key"] for c in extrair_campos(texto)]
    assert "cpf" not in chaves
    assert "cpf_invalido" in chaves


def test_texto_sem_dados_nao_inventa():
    assert extrair_campos("apenas uma frase qualquer") == []


def test_sei_nao_vira_cpf_nem_cep():
    campos = extrair_campos("SEI 140.00386388/2026-87")
    chaves = [c["key"] for c in campos]
    assert chaves == ["sei"]
    assert campos[0]["value"] == "140.00386388/2026-87"


def test_nome_nao_engole_rotulo():
    campos = {c["key"]: c["value"] for c in extrair_campos("NOME DO CONDUTOR: JOAO DA SILVA CPF: 435.004.468-09")}
    assert campos["nome"] == "JOAO DA SILVA"
