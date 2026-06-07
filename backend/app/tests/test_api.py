from fastapi.testclient import TestClient
from app.main import app

def _c(): return TestClient(app)
def _tok(c):
    return c.post("/api/auth/login",json={"username":"admin","password":"admin12345"}).json()["token"]

def test_health():
    with _c() as c: assert c.get("/api/health").json()["status"]=="ok"

def test_login():
    with _c() as c:
        assert c.post("/api/auth/login",json={"username":"admin","password":"admin12345"}).status_code==200
        assert c.post("/api/auth/login",json={"username":"admin","password":"x"}).status_code==401

def test_projects_auth():
    with _c() as c:
        assert c.get("/api/projects").status_code==401
        h={"Authorization":f"Bearer {_tok(c)}"}
        assert c.get("/api/projects",headers=h).status_code==200
