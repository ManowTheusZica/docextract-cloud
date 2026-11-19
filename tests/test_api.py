def test_health(client):
    resposta = client.get("/health")
    assert resposta.status_code == 200
    assert resposta.json()["status"] == "ok"


def test_registro_e_login(client):
    email = "novo@exemplo.com"
    assert client.post("/auth/register", json={"email": email, "password": "12345678"}).status_code == 201
    duplicado = client.post("/auth/register", json={"email": email, "password": "12345678"})
    assert duplicado.status_code == 409

    ok = client.post("/auth/login", json={"email": email, "password": "12345678"})
    assert ok.status_code == 200
    assert ok.json()["access_token"]

    errado = client.post("/auth/login", json={"email": email, "password": "senhaerrada"})
    assert errado.status_code == 401


def test_senha_curta_recusada(client):
    resposta = client.post("/auth/register", json={"email": "curta@exemplo.com", "password": "123"})
    assert resposta.status_code == 422


def test_sem_token_da_401(client):
    assert client.get("/documents").status_code == 401


def test_upload_extrai_campos(client, usuario):
    conteudo = (
        "NOME DO CONDUTOR: JOAO DA SILVA\n"
        "CPF: 435.004.468-09\n"
        "SEI 140.00386388/2026-87\n"
        "PA 3/2024\n"
    ).encode("utf-8")

    resposta = client.post(
        "/documents",
        headers=usuario["headers"],
        files={"arquivo": ("doc.txt", conteudo, "text/plain")},
    )
    assert resposta.status_code == 202, resposta.text
    documento = resposta.json()
    assert documento["status"] == "ready"
    assert documento["text_chars"] > 0

    detalhe = client.get("/documents/%d" % documento["id"], headers=usuario["headers"]).json()
    campos = {c["key"]: c["value"] for c in detalhe["fields"]}
    assert campos["cpf"] == "43500446809"
    assert campos["sei"] == "140.00386388/2026-87"

    job = client.get("/documents/%d/job" % documento["id"], headers=usuario["headers"])
    assert job.status_code == 200
    assert job.json()["status"] == "done"


def test_formato_invalido(client, usuario):
    resposta = client.post(
        "/documents",
        headers=usuario["headers"],
        files={"arquivo": ("foto.jpg", b"\xff\xd8\xff", "image/jpeg")},
    )
    assert resposta.status_code == 415


def test_arquivo_vazio(client, usuario):
    resposta = client.post(
        "/documents",
        headers=usuario["headers"],
        files={"arquivo": ("vazio.txt", b"", "text/plain")},
    )
    assert resposta.status_code == 400


def test_documento_de_outro_usuario_da_404(client, usuario):
    conteudo = b"NOME DO CONDUTOR: MARIA SOUZA\nCPF: 435.004.468-09\n"
    dono = client.post(
        "/documents",
        headers=usuario["headers"],
        files={"arquivo": ("a.txt", conteudo, "text/plain")},
    ).json()

    client.post("/auth/register", json={"email": "intruso@exemplo.com", "password": "12345678"})
    token = client.post(
        "/auth/login", json={"email": "intruso@exemplo.com", "password": "12345678"}
    ).json()["access_token"]

    resposta = client.get(
        "/documents/%d" % dono["id"], headers={"Authorization": "Bearer %s" % token}
    )
    assert resposta.status_code == 404


def test_listagem_paginada(client, usuario):
    for i in range(3):
        client.post(
            "/documents",
            headers=usuario["headers"],
            files={"arquivo": ("p%d.txt" % i, b"CPF: 435.004.468-09", "text/plain")},
        )
    primeira = client.get("/documents?limite=2&pagina=1", headers=usuario["headers"]).json()
    segunda = client.get("/documents?limite=2&pagina=2", headers=usuario["headers"]).json()
    assert len(primeira) == 2
    assert len(segunda) >= 1
    assert {d["id"] for d in primeira}.isdisjoint({d["id"] for d in segunda})
