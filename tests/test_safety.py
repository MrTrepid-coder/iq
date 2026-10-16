"""Testes de segurança: execução real desativada, sem credenciais, sem rede.

Verifica em múltiplas camadas:
1. Nenhum código de execução real existe no pacote app/.
2. Nenhuma credencial embutida.
3. /api/health reporta modo simulação.
4. O adaptador real está indisponível e falha de forma segura.
5. O guard de execução real SEMPRE recusa, independentemente de ambiente.
6. O fluxo de simulação não existe caminho que chame operação real.
"""
import ast
import os

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")


def _source_files():
    for root, _, files in os.walk(APP_DIR):
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(root, f)


def test_no_order_execution_keywords():
    """Nenhum código de envio de ordem real deve existir no pacote app/."""
    forbidden = ("buy(", "place_order", "send_order", "execute_trade",
                 "api.iqoption", "websocket", "ssid", "password")
    for path in _source_files():
        with open(path, encoding="utf-8") as fh:
            content = fh.read().lower()
        for kw in forbidden:
            assert kw.lower() not in content, f"{os.path.basename(path)} contém '{kw}'"


def test_no_hardcoded_credentials():
    """Nenhuma credencial embutida no código-fonte."""
    suspicious = ("password=", "api_key=", "secret=", "token=")
    for path in _source_files():
        with open(path, encoding="utf-8") as fh:
            content = fh.read().lower()
        for kw in suspicious:
            assert kw not in content, f"{os.path.basename(path)} contém '{kw}'"


def test_health_reports_simulation_only():
    from app.ui.server import app
    client = app.test_client()
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.get_json()
    assert body["real_execution"] is False
    assert body["mode"] == "simulation"


def test_real_adapter_unavailable_and_fails_safe():
    from app.data.connectors import RealBrokerAdapter
    a = RealBrokerAdapter()
    assert a.is_available() is False
    import pytest
    with pytest.raises(RuntimeError):
        a.load("BTC")
    # tentativa de operação real é bloqueada, nunca simula sucesso
    from app.config import RealExecutionBlocked
    with pytest.raises(RealExecutionBlocked):
        a.submit_real_operation()


def test_execution_block_is_env_independent(monkeypatch):
    """Alterar variáveis de ambiente não libera execução real."""
    from app.config import ensure_real_execution_blocked, RealExecutionBlocked
    monkeypatch.setenv("SIMULATION_MODE", "false")
    monkeypatch.setenv("REAL_TRADING", "1")
    monkeypatch.setenv("LIVE", "yes")
    import pytest
    with pytest.raises(RealExecutionBlocked):
        ensure_real_execution_blocked("tentativa com env alterado")


def test_simulation_module_has_no_real_order_calls():
    """O módulo de simulação não deve importar/chamar adaptador real."""
    path = os.path.join(APP_DIR, "simulation", "__init__.py")
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
        if isinstance(node, ast.Name):
            names.append(node.id)
    joined = " ".join(names).lower()
    assert "connectors" not in joined
    assert "realbroker" not in joined
