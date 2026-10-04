import importlib


def test_env_exports_webui_subpath(monkeypatch):
    monkeypatch.setenv('WEBUI_SECRET_KEY', 'test-secret')
    monkeypatch.setenv('WEBUI_SUBPATH', '/openwebui')

    env_module = importlib.import_module('open_webui.env')
    env_module = importlib.reload(env_module)

    assert env_module.WEBUI_SUBPATH == '/openwebui'
