# DocExtract Cloud

API que recebe um PDF/documento, extrai campos brasileiros (CPF, CNPJ, SEI, PA, CEP,
placa, datas) e devolve JSON estruturado com confianca por campo. Multi-usuario, com
autenticacao, historico e fila de processamento.

## O que ja funciona

- Cadastro e login com JWT (senha via PBKDF2-SHA256 com salt por usuario)
- Upload de documento e extracao sincrona com retorno de campos + score
- Isolamento por usuario: cada um so ve os proprios documentos
- Rate limit por IP nos endpoints de autenticacao
- 17 testes automatizados (pytest) cobrindo auth, isolamento e extracao
- Dockerfile + docker-compose (API + Postgres + Redis) e CI no GitHub Actions

## Rodando

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Documentacao interativa: http://localhost:8000/docs

Modo simples (sem Postgres), so para testar:

```bash
DATABASE_URL=sqlite:///./local.db uvicorn app.main:app --port 8000
```

## Endpoints

- `GET  /health` - status do servico
- `POST /auth/register` - cria usuario
- `POST /auth/login` - devolve token JWT
- `POST /documents` - upload (multipart) e extracao
- `GET  /documents` - lista documentos do usuario
- `GET  /documents/{id}` - detalhe com campos extraidos

## Exemplo

```bash
TOKEN=$(curl -s -X POST localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"a@b.com","senha":"senha123"}' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

curl -s -X POST localhost:8000/documents \
  -H "Authorization: Bearer $TOKEN" \
  -F "arquivo=@oficio.pdf"
```

Resposta (campos reais do teste):

```json
{
  "id": 1,
  "nome_arquivo": "oficio.pdf",
  "campos": {
    "cpf": "435.004.468-09",
    "sei": "140.00386388/2026-87",
    "pa": "3/2024",
    "cep": "01014-010"
  }
}
```

## Decisoes que valem explicar em entrevista

- **Extracao por camadas**: PDF com camada de texto usa `pypdf`; quando nao ha texto,
  cai para OCR. Sempre retorna o que conseguiu, com confianca, em vez de falhar inteiro.
- **Mascara antes da regex**: o numero SEI e mascarado antes de procurar CPF; sem isso
  `140.00386388/2026-87` virava falso positivo de CPF.
- **Idempotencia**: o mesmo arquivo pode ser reprocessado sem duplicar registro.
- **Senha**: PBKDF2 com salt aleatorio e comparacao em tempo constante (`hmac.compare_digest`).
- **Fila**: Celery + Redis para documentos grandes; o endpoint aceita e devolve `202`
  quando o processamento e assincrono.

## Estrutura

```
app/
  config.py      variaveis de ambiente
  database.py    engine SQLAlchemy e sessao
  security.py    hash de senha e JWT
  extraction.py  texto do PDF (pypdf + fallback)
  fields.py      regex e validacao de campos brasileiros
  models.py      User, Document
  main.py        app, rate limit, lifespan
  routers/       auth.py, documents.py
tests/           conftest, test_auth, test_documents
```

## Proximos passos

- Fila Celery ligada de ponta a ponta (hoje o modo sincrono e o caminho principal)
- Painel web para upload em lote
- Metricas Prometheus
