from app.main import limite_estourado


def test_limite_libera_ate_o_teto():
    assert not limite_estourado([100.0, 101.0], limite=3, agora=102.0)
    assert limite_estourado([100.0, 101.0, 102.0], limite=3, agora=102.5)


def test_janela_expira():
    assert not limite_estourado([1.0, 2.0, 3.0], limite=3, agora=70.0)
