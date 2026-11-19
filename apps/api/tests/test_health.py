from asebe_api.main import create_app
from fastapi.testclient import TestClient

def test_health_endpoint():
    app = create_app()
    assert app is not None
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
