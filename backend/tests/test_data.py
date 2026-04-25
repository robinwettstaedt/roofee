from fastapi.testclient import TestClient

from app.main import app


def test_list_datasets() -> None:
    client = TestClient(app)

    response = client.get("/api/data/datasets")

    assert response.status_code == 200
    assert isinstance(response.json(), list)
