import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def unwrap(response):
    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    return body["data"]


def require_tourapi_key():
    if not get_settings().tourapi_service_key:
        pytest.skip("TOURAPI_SERVICE_KEY is required for real TourAPI integration tests")


def test_tourapi_search_returns_real_items_and_logs_tool_call():
    require_tourapi_key()

    with TestClient(app) as client:
        run_payload = {
            "template_id": "default_product_planning",
            "input": {
                "message": "부산 외국인 야간 관광",
                "region": "부산",
                "period": "2026-05",
                "target_customer": "외국인",
                "product_count": 3,
                "preferences": ["야간 관광"],
            },
        }
        run = unwrap(client.post("/api/workflow-runs", json=run_payload))
        data = unwrap(
            client.get(
                "/api/data/tourism/search",
                params={
                    "region_code": "6",
                    "content_type": "accommodation",
                    "run_id": run["id"],
                    "limit": 5,
                },
            )
        )
        assert data["provider"] == "tourapi"
        assert data["region_code"] == "6"
        assert data["source_documents"] > 0
        assert data["indexed_documents"] > 0
        assert all(item["source"] == "tourapi" for item in data["items"])

        tool_calls = unwrap(client.get(f"/api/workflow-runs/{run['id']}/tool-calls"))
        matching_calls = [
            call
            for call in tool_calls
            if call["tool_name"] == "tourapi_search_stay" and call["source"] == "tourapi"
        ]
        assert matching_calls
        assert all(call["status"] == "succeeded" for call in matching_calls)

        rag_results = unwrap(
            client.post(
                "/api/rag/search",
                json={
                    "query": "부산 숙박",
                    "filters": {"region_code": "6", "source": "tourapi"},
                    "top_k": 5,
                },
            )
        )
        assert len(rag_results["results"]) > 0
        assert all(result["metadata"]["source"] == "tourapi" for result in rag_results["results"])


def test_tourapi_event_and_stay_search():
    require_tourapi_key()

    with TestClient(app) as client:
        events = unwrap(
            client.get(
                "/api/data/tourism/search",
                params={
                    "region_code": "6",
                    "content_type": "event",
                    "start_date": "2026-05-01",
                    "end_date": "2026-05-31",
                    "limit": 5,
                },
            )
        )
        assert events["provider"] == "tourapi"
        assert all(item["source"] == "tourapi" for item in events["items"])

        stays = unwrap(
            client.get(
                "/api/data/tourism/search",
                params={"region_code": "6", "content_type": "accommodation", "limit": 5},
            )
        )
        assert stays["provider"] == "tourapi"
        assert any(item["content_type"] == "accommodation" for item in stays["items"])
        assert all(item["source"] == "tourapi" for item in stays["items"])
