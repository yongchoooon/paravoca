from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import routes_posters
from app.core.config import get_settings
from app.db import models
from app.db.session import SessionLocal
from app.main import app
from app.posters.costs import estimate_poster_image_cost, output_image_token_estimate
from app.posters.openai_images import GeneratedPosterImage
from app.posters.prompt_builder import build_poster_prompt


def _sample_result(status: str = "completed") -> dict:
    return {
        "status": status,
        "normalized_request": {"location": "부산", "target_customer": "20대 친구 여행"},
        "geo_scope": {"locations": [{"name": "부산광역시", "keyword": "광안리"}]},
        "retrieved_documents": [
            {"doc_id": "doc_1", "title": "광안리 해변", "snippet": "야간 경관이 알려져 있습니다."}
        ],
        "products": [
            {
                "id": "product_1",
                "title": "광안리 야경 로컬 워크",
                "one_liner": "부산 바다와 골목 분위기를 가볍게 연결하는 저녁 산책 상품",
                "target_customer": "20대 친구 여행",
                "core_value": ["야경", "로컬 경험"],
                "itinerary": [{"title": "광안리 해변 산책"}, {"title": "로컬 카페 휴식"}],
                "source_ids": ["doc_1"],
                "assumptions": [],
                "not_to_claim": ["모든 매장이 영업 중이라고 단정"],
                "evidence_summary": "광안리 해변과 주변 야간 경관 근거를 사용했습니다.",
                "needs_review": ["방문 당일 운영시간 확인 필요"],
                "coverage_notes": [],
                "claim_limits": ["가격, 할인율, 예약 가능 여부 단정 금지"],
            }
        ],
        "marketing_assets": [
            {
                "product_id": "product_1",
                "sales_copy": {
                    "headline": "부산 밤바다를 천천히 걷는 시간",
                    "subheadline": "광안리의 풍경과 로컬 무드를 함께 담은 저녁 코스",
                    "sections": [],
                    "disclaimer": "운영 정보는 방문 전 확인이 필요합니다.",
                },
                "faq": [],
                "sns_posts": ["오늘 밤 광안리에서 가볍게 시작하는 로컬 산책"],
                "search_keywords": ["부산 야경", "광안리"],
                "evidence_disclaimer": "운영시간과 가격은 확인 필요",
                "claim_limits": ["예약 즉시 확정 표현 금지"],
            }
        ],
        "unresolved_gaps": [{"type": "hours", "message": "운영시간 확인 필요"}],
        "qa_report": {"overall_status": "pass", "issues": []},
        "cost_summary": {},
        "revision": {},
        "approval": {},
    }


def _create_run(status: str = "succeeded", result_status: str = "completed") -> str:
    with SessionLocal() as db:
        run = models.WorkflowRun(
            template_id="default_product_planning",
            status=status,
            input={"message": "부산 야경 여행 상품", "region": "부산"},
            final_output=_sample_result(status=result_status),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run.id


def _unwrap(response):
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["error"] is None
    return body["data"]


def test_poster_prompt_builder_separates_visible_text_and_constraints():
    result = _sample_result()
    prompt = build_poster_prompt(
        run_input={"message": "부산 야경 여행 상품", "region": "부산"},
        result=result,
        product=result["products"][0],
        marketing=result["marketing_assets"][0],
        included_sections=[
            "product_summary",
            "itinerary",
            "marketing_copy",
            "sns_copy",
            "evidence_summary",
            "claim_limits",
        ],
        style_preset="editorial_travel",
    )

    assert "Scene/background:" in prompt.prompt
    assert "Subject:" in prompt.prompt
    assert "Key details:" in prompt.prompt
    assert "Included text:" in prompt.prompt
    assert "Style:" in prompt.prompt
    assert "Constraints:" in prompt.prompt
    assert '"광안리 야경 로컬 워크"' in prompt.prompt
    assert any("가격, 할인율" in item for item in prompt.constraints)
    assert "Avoid claiming: 가격, 할인율" in prompt.prompt
    assert all("가격, 할인율" not in item for item in prompt.visible_text)


def test_poster_cost_estimate_uses_gpt_image_2_pricing():
    settings = get_settings()
    assert output_image_token_estimate(size="1024x1536", quality="medium") == 1584
    cost = estimate_poster_image_cost(
        prompt="A" * 2000,
        usage={
            "input_tokens": 1000,
            "input_tokens_details": {"text_tokens": 1000, "image_tokens": 0},
            "output_tokens": 1584,
        },
        size="1024x1536",
        quality="medium",
        settings=settings,
    )

    assert cost.basis == "openai_usage"
    assert cost.text_input_tokens == 1000
    assert cost.image_output_tokens == 1584
    assert cost.text_input_cost_usd == 0.005
    assert cost.image_output_cost_usd == 0.04752
    assert cost.total_cost_usd == 0.05252
    assert cost.usd_krw_rate == 1490
    assert cost.total_cost_krw == 78.25


def test_create_poster_without_openai_key_records_failed_poster():
    with TestClient(app) as client:
        run_id = _create_run()
        response = client.post(
            f"/api/workflow-runs/{run_id}/products/product_1/posters",
            json={
                "style_preset": "editorial_travel",
                "included_sections": ["product_summary", "claim_limits"],
            },
        )

        created = _unwrap(response)
        assert created["status"] == "running"
        with SessionLocal() as db:
            posters = (
                db.query(models.PosterAsset)
                .filter(models.PosterAsset.run_id == run_id)
                .all()
            )
            assert len(posters) == 1
            assert posters[0].status == "failed"
            assert posters[0].image_path is None
            assert posters[0].error["details"]["reason"] == "missing_openai_api_key"


def test_create_poster_with_monkeypatched_gateway_saves_asset_and_downloads(monkeypatch):
    def fake_generate_poster_image(*, prompt, settings):
        assert "Create one portrait travel promotion poster draft." in prompt
        return GeneratedPosterImage(
            image_bytes=b"poster-bytes",
            provider_response_summary={
                "request_id": "req_test",
                "model": settings.poster_image_model,
                "cost_breakdown": {
                    "total_cost_krw": 78.25,
                    "usd_krw_rate": 1490,
                    "basis": "openai_usage",
                    "tokens": {
                        "text_input": 1000,
                        "text_cached_input": 0,
                        "image_input": 0,
                        "image_cached_input": 0,
                        "image_output": 1584,
                        "total": 2584,
                    },
                },
            },
            latency_ms=123,
            cost_usd=0.05252,
        )

    monkeypatch.setattr(routes_posters, "generate_poster_image", fake_generate_poster_image)

    with TestClient(app) as client:
        run_id = _create_run()
        created = _unwrap(
            client.post(
                f"/api/workflow-runs/{run_id}/products/product_1/posters",
                json={
                    "style_preset": "minimal_event",
                    "included_sections": ["product_summary", "itinerary", "marketing_copy"],
                },
            )
        )
        assert created["status"] == "running"
        poster = _unwrap(client.get(f"/api/posters/{created['id']}"))

        assert poster["status"] == "succeeded"
        assert poster["prompt_language"] == "en"
        assert poster["image_url"] == f"/api/posters/{poster['id']}/download"
        assert poster["latency_ms"] == 123
        assert poster["cost_usd"] == 0.05252
        assert poster["provider_response_summary"]["cost_breakdown"]["tokens"]["image_output"] == 1584

        download = client.get(f"/api/posters/{poster['id']}/download")
        assert download.status_code == 200
        assert download.content == b"poster-bytes"

        settings = get_settings()
        log_path = routes_posters.Path(settings.poster_usage_log_dir) / "poster_usage.jsonl"
        if not log_path.is_absolute():
            log_path = routes_posters.Path(routes_posters.__file__).resolve().parents[2] / log_path
        assert log_path.exists()
        assert poster["id"] in log_path.read_text(encoding="utf-8")

        prompt_dir = routes_posters.Path(settings.poster_prompt_log_dir) / run_id
        if not prompt_dir.is_absolute():
            prompt_dir = routes_posters.Path(routes_posters.__file__).resolve().parents[2] / prompt_dir
        prompt_json = prompt_dir / f"{poster['id']}.json"
        prompt_md = prompt_dir / f"{poster['id']}.md"
        assert prompt_json.exists()
        assert prompt_md.exists()
        assert "Create one portrait travel promotion poster draft." in prompt_json.read_text(encoding="utf-8")
        assert "## Prompt" in prompt_md.read_text(encoding="utf-8")

        deleted = _unwrap(client.delete(f"/api/posters/{poster['id']}"))
        assert deleted["deleted_poster_id"] == poster["id"]
        assert client.get(f"/api/posters/{poster['id']}").status_code == 404


def test_poster_generation_validates_product_and_blocked_result_status(monkeypatch):
    monkeypatch.setattr(
        routes_posters,
        "generate_poster_image",
        lambda **kwargs: GeneratedPosterImage(b"ok", {}, 1, 0),
    )

    with TestClient(app) as client:
        run_id = _create_run()
        missing_product = client.post(
            f"/api/workflow-runs/{run_id}/products/missing_product/posters",
            json={"style_preset": "night_city", "included_sections": ["product_summary"]},
        )
        assert missing_product.status_code == 404

        blocked_run_id = _create_run(result_status="insufficient_source_data")
        blocked = client.post(
            f"/api/workflow-runs/{blocked_run_id}/products/product_1/posters",
            json={"style_preset": "night_city", "included_sections": ["product_summary"]},
        )
        assert blocked.status_code == 409


def test_product_poster_limit_counts_running_and_succeeded(monkeypatch):
    monkeypatch.setattr(
        routes_posters,
        "generate_poster_image",
        lambda **kwargs: GeneratedPosterImage(b"ok", {}, 1, 0),
    )

    with TestClient(app) as client:
        run_id = _create_run()
        poster_ids: list[str] = []
        for style in ["editorial_travel", "night_city", "minimal_event"]:
            poster = _unwrap(
                client.post(
                    f"/api/workflow-runs/{run_id}/products/product_1/posters",
                    json={"style_preset": style, "included_sections": ["product_summary"]},
                )
            )
            poster_ids.append(poster["id"])

        limited = client.post(
            f"/api/workflow-runs/{run_id}/products/product_1/posters",
            json={"style_preset": "editorial_travel", "included_sections": ["itinerary"]},
        )
        assert limited.status_code == 409
        assert "최대 3개" in limited.json()["detail"]

        _unwrap(client.delete(f"/api/posters/{poster_ids[0]}"))
        next_poster = _unwrap(
            client.post(
                f"/api/workflow-runs/{run_id}/products/product_1/posters",
                json={"style_preset": "editorial_travel", "included_sections": ["itinerary"]},
            )
        )
        assert next_poster["status"] == "running"
