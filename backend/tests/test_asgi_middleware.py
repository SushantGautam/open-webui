from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from open_webui.utils.asgi_middleware import RedirectMiddleware


async def ok(_request):
    return PlainTextResponse('ok')


def build_client(*, root_path: str = '') -> TestClient:
    app = Starlette(routes=[Route('/', ok), Route('/watch', ok)])
    app.add_middleware(RedirectMiddleware)
    return TestClient(app, root_path=root_path)


def test_redirect_middleware_keeps_root_path_for_watch_redirect():
    client = build_client(root_path='/openwebui')

    response = client.get('/watch?v=abc123', follow_redirects=False)

    assert response.status_code in (301, 302, 307, 308)
    assert response.headers['location'] == '/openwebui/?youtube=abc123'


def test_redirect_middleware_uses_root_when_no_root_path_is_set():
    client = build_client()

    response = client.get('/watch?v=abc123', follow_redirects=False)

    assert response.status_code in (301, 302, 307, 308)
    assert response.headers['location'] == '/?youtube=abc123'
