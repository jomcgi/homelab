from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(name="client")
def client_fixture():
    return TestClient(app, raise_server_exceptions=False)


def test_create_note_success(client):
    with patch(
        "notes.router.create_fleeting_note",
        new_callable=AsyncMock,
        return_value={"path": "Fleeting/2026-03-31 1423.md"},
    ):
        response = client.post("/api/notes", json={"content": "Quick thought"})
    assert response.status_code == 201
    assert response.json()["path"] == "Fleeting/2026-03-31 1423.md"


def test_create_note_empty_content(client):
    response = client.post("/api/notes", json={"content": ""})
    assert response.status_code == 400


def test_create_note_missing_content(client):
    response = client.post("/api/notes", json={})
    assert response.status_code == 422


def test_create_note_vault_error(client):
    with patch(
        "notes.router.create_fleeting_note",
        new_callable=AsyncMock,
        side_effect=Exception("vault down"),
    ):
        response = client.post("/api/notes", json={"content": "A thought"})
    assert response.status_code == 502
