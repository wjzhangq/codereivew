"""tests/test_api.py — API 鉴权 + 项目/用户/分支白名单"""
from fastapi.testclient import TestClient

from app.main import app


def _client():
    return TestClient(app)


def _admin_token(c):
    r = c.post("/api/auth/login", json={"username": "admin", "password": "admin12345"})
    return r.json()["token"]


def test_health():
    with _client() as c:
        assert c.get("/api/health").json()["status"] == "ok"


def test_login_and_auth():
    with _client() as c:
        # 正确密码
        r = c.post("/api/auth/login", json={"username": "admin", "password": "admin12345"})
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "admin"
        # 错误密码
        assert c.post("/api/auth/login",
                      json={"username": "admin", "password": "x"}).status_code == 401
        # 未认证访问
        assert c.get("/api/projects").status_code == 401


def test_user_management():
    with _client() as c:
        h = {"Authorization": f"Bearer {_admin_token(c)}"}
        r = c.post("/api/users", json={"username": "tu", "password": "pw123456",
                                       "name": "TU", "role": "user"}, headers=h)
        assert r.status_code == 200
        users = c.get("/api/users", headers=h).json()["data"]
        assert any(u["username"] == "tu" for u in users)
