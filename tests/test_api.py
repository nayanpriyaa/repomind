"""HTTP surface, exercised through the real routes with stub backends."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from repomind.api.main import create_app  # noqa: E402


@pytest.fixture()
def client(container, sample_repository: Path):
    app = create_app(container=container)
    with TestClient(app) as test_client:
        test_client.repository = str(sample_repository.resolve())
        yield test_client


def test_health_is_cheap_and_always_ok(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready_reports_each_dependency(client) -> None:
    body = client.get("/ready").json()
    assert body["ready"] is True
    assert body["database"] is True and body["vector_store"] is True
    assert body["llm_configured"] is False


def test_index_endpoint_indexes_a_repository(client) -> None:
    response = client.post("/repositories/index", json={"repository_path": client.repository})
    assert response.status_code == 200
    body = response.json()
    assert body["files_indexed"] > 0 and body["chunks_indexed"] > 0


def test_index_endpoint_is_incremental(client) -> None:
    client.post("/repositories/index", json={"repository_path": client.repository})
    body = client.post("/repositories/index", json={"repository_path": client.repository}).json()
    assert body["files_indexed"] == 0 and body["files_unchanged"] > 0


def test_status_endpoint_reports_counts(client) -> None:
    client.post("/repositories/index", json={"repository_path": client.repository})
    body = client.get("/repositories/status", params={"repository_path": client.repository}).json()
    assert body["indexed"] is True and body["chunk_count"] > 0


def test_query_endpoint_returns_answer_and_sources(client) -> None:
    client.post("/repositories/index", json={"repository_path": client.repository})
    response = client.post(
        "/repositories/query",
        json={"repository_path": client.repository, "question": "Where is authentication implemented?", "top_k": 3, "mode": "hybrid"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is True
    assert body["sources"] and "file_path" in body["sources"][0]
    assert body["sources"][0]["end_line"] >= body["sources"][0]["start_line"]


def test_search_endpoint_returns_raw_hits(client) -> None:
    client.post("/repositories/index", json={"repository_path": client.repository})
    body = client.post(
        "/repositories/search",
        json={"repository_path": client.repository, "query": "authenticate", "mode": "keyword", "top_k": 5},
    ).json()
    assert body["hits"] and body["hits"][0]["match_type"] == "keyword"


def test_path_traversal_is_rejected(client) -> None:
    response = client.post("/repositories/index", json={"repository_path": "../../etc"})
    assert response.status_code == 400
    assert "accessible repository" in response.json()["detail"]


def test_absolute_paths_outside_the_root_are_rejected(client) -> None:
    assert client.post("/repositories/index", json={"repository_path": "/etc"}).status_code == 400


def test_error_messages_do_not_leak_filesystem_details(client) -> None:
    detail = client.get("/repositories/status", params={"repository_path": "/etc/shadow"}).json()["detail"]
    assert "/etc/shadow" not in detail


def test_unknown_fields_are_rejected(client) -> None:
    response = client.post(
        "/repositories/index",
        json={"repository_path": client.repository, "unexpected": True},
    )
    assert response.status_code == 422


def test_invalid_mode_is_rejected(client) -> None:
    response = client.post(
        "/repositories/query",
        json={"repository_path": client.repository, "question": "what is this", "mode": "telepathy"},
    )
    assert response.status_code == 422


def test_top_k_is_bounded(client) -> None:
    response = client.post(
        "/repositories/query",
        json={"repository_path": client.repository, "question": "what is this", "top_k": 5000},
    )
    assert response.status_code == 422


def test_short_questions_are_rejected(client) -> None:
    response = client.post(
        "/repositories/query",
        json={"repository_path": client.repository, "question": "a"},
    )
    assert response.status_code == 422


def test_cors_headers_are_present_for_allowed_origins(client) -> None:
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
