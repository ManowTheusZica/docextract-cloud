import os
import tempfile
from pathlib import Path

import pytest

BANCO = Path(tempfile.mkdtemp(prefix="docextract-teste-")) / "teste.db"
os.environ["DATABASE_URL"] = "sqlite:///%s" % BANCO
os.environ["SECRET_KEY"] = "chave-de-teste"
os.environ["QUEUE_MODE"] = "inline"
os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def usuario(client):
    email = "teste%d@exemplo.com" % id(object())
    senha = "senha-forte-123"
    client.post("/auth/register", json={"email": email, "password": senha})
    resposta = client.post("/auth/login", json={"email": email, "password": senha})
    token = resposta.json()["access_token"]
    return {"email": email, "senha": senha, "headers": {"Authorization": "Bearer %s" % token}}
