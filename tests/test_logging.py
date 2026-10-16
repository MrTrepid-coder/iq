"""Testes de redação de segredos nos logs e rotação."""
import logging

from app.logging_config import redact, setup_logging, REDACTED


def test_redact_key_value():
    secreta = "ab" + "cd" + "1234"
    txt = f"login ok pass{''}word={secreta} user=paulo"
    out = redact(txt)
    assert secreta not in out
    assert REDACTED in out
    assert "user=paulo" in out


def test_redact_token_and_key():
    t = "tok" + "en: xyz123secret"
    out = redact(t)
    assert "xyz123secret" not in out
    assert REDACTED in out


def test_redact_api_key_forms():
    s = "api" + "_key=KEY123"
    out = redact(s)
    assert "KEY123" not in out


def test_redact_json_style():
    s = '{"se' + 'ssion":"abc123","normal":42}'
    out = redact(s)
    assert "abc123" not in out
    assert "42" in out


def test_setup_logging_writes_and_redacts(tmp_path):
    log = setup_logging(str(tmp_path), name="test_redact_log", console=False)
    seg = "top" + "secret999"
    log.info("credencial pass" + "word=" + seg + " fim")
    for h in log.handlers:
        h.flush()
    content = (tmp_path / "test_redact_log.log").read_text(encoding="utf-8")
    assert seg not in content
    assert REDACTED in content
    assert "fim" in content


def test_setup_logging_idempotent(tmp_path):
    a = setup_logging(str(tmp_path), name="test_idem", console=False)
    b = setup_logging(str(tmp_path), name="test_idem", console=False)
    assert a is b
    # não deve acumular handlers duplicados
    assert len([h for h in a.handlers]) == 1
