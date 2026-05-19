import json
import logging
import os

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db import models
from app.db.session import SessionLocal, init_db
from app.evals.metrics import EvalOptions, evaluate_case
from app.evals.reporting import list_evaluation_reports, read_evaluation_report, write_evaluation_report
from app.evals import runner as eval_runner
from app.evals.run_eval import EvaluationLogFormatter, _eval_log_tag, _is_eval_log_noise
from app.evals.runner import load_dataset, run_evaluation
from app.main import app


def test_product_source_id_validity_flags_missing_document_id():
    case = {"case_id": "source_id", "name": "source id", "expected_min_products": 1}
    context = {
        "run_id": "run_eval_source",
        "status": "awaiting_approval",
        "final_output": {
            "retrieved_documents": [{"doc_id": "doc:1", "title": "근거"}],
            "products": [{"id": "product_1", "source_ids": ["doc:missing"]}],
            "qa_report": {"issues": []},
        },
        "cost_total_usd": 0,
        "latency_ms": 10,
        "enrichment_tool_calls": [],
    }

    result = evaluate_case(case, context, EvalOptions(usd_krw_rate=1460))

    metric = next(item for item in result["metrics"] if item["name"] == "product_source_id_validity")
    assert metric["passed"] is False
    assert result["status"] == "failed"


def test_eval_logging_suppresses_non_problem_eval_noise_only():
    kto_success = logging.LogRecord(
        "httpx",
        logging.INFO,
        "",
        0,
        'HTTP Request: GET https://apis.data.go.kr/B551011/KorService2/areaBasedList2 "HTTP/1.1 200 OK"',
        (),
        None,
    )
    gemini_success = logging.LogRecord(
        "httpx",
        logging.INFO,
        "",
        0,
        'HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/models/gemini "HTTP/1.1 200 OK"',
        (),
        None,
    )
    kto_failure = logging.LogRecord(
        "httpx",
        logging.INFO,
        "",
        0,
        'HTTP Request: GET https://apis.data.go.kr/B551011/KorService2/areaBasedList2 "HTTP/1.1 503 Service Unavailable"',
        (),
        None,
    )
    huggingface_success = logging.LogRecord(
        "httpx",
        logging.INFO,
        "",
        0,
        'HTTP Request: HEAD https://huggingface.co/sentence-transformers/model "HTTP/1.1 200 OK"',
        (),
        None,
    )
    sentence_transformer_info = logging.LogRecord(
        "sentence_transformers.base.model",
        logging.INFO,
        "",
        0,
        "Loading SentenceTransformer model from sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2.",
        (),
        None,
    )
    dropped_warning = logging.LogRecord(
        "uvicorn.error",
        logging.WARNING,
        "",
        0,
        "Dropped 47 off-region TourAPI items",
        (),
        None,
    )

    assert _is_eval_log_noise(kto_success) is True
    assert _is_eval_log_noise(gemini_success) is True
    assert _is_eval_log_noise(kto_failure) is False
    assert _is_eval_log_noise(huggingface_success) is True
    assert _is_eval_log_noise(sentence_transformer_info) is True
    assert _is_eval_log_noise(dropped_warning) is False


def test_eval_logging_tags_remaining_log_groups():
    records = [
        (
            logging.LogRecord(
                "eval.runner",
                logging.INFO,
                "",
                0,
                "Evaluation case started eval_id=eval_1 case=case_1 index=1/2",
                (),
                None,
            ),
            "EVAL-CASE",
        ),
        (
            logging.LogRecord(
                "uvicorn.error",
                logging.WARNING,
                "",
                0,
                "Gemini retryable response. run_id=run_1 purpose=planner status_code=503 attempt=1/4",
                (),
                None,
            ),
            "LLM-RETRY",
        ),
        (
            logging.LogRecord(
                "uvicorn.error",
                logging.ERROR,
                "",
                0,
                "Gemini JSON handling failed. run_id=run_1 purpose=data_gap_profile finish_reason=MAX_TOKENS",
                (),
                None,
            ),
            "LLM-JSON",
        ),
        (
            logging.LogRecord(
                "httpx",
                logging.INFO,
                "",
                0,
                'HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/models/gemini "HTTP/1.1 503 Service Unavailable"',
                (),
                None,
            ),
            "HTTP-GEMINI",
        ),
        (
            logging.LogRecord(
                "httpx",
                logging.INFO,
                "",
                0,
                'HTTP Request: GET https://apis.data.go.kr/B551011/KorService2/areaBasedList2 "HTTP/1.1 503 Service Unavailable"',
                (),
                None,
            ),
            "HTTP-KTO",
        ),
        (
            logging.LogRecord(
                "uvicorn.error",
                logging.WARNING,
                "",
                0,
                "Dropped 47 off-region TourAPI items",
                (),
                None,
            ),
            "GEO-FILTER",
        ),
        (
            logging.LogRecord(
                "uvicorn.error",
                logging.ERROR,
                "",
                0,
                "[workflow-run-failed] run_id=run_1 type=RuntimeError message=failed",
                (),
                None,
            ),
            "WORKFLOW-FAIL",
        ),
    ]

    for record, expected_tag in records:
        assert _eval_log_tag(record) == expected_tag


def test_eval_log_formatter_adds_tag_without_color_when_disabled():
    record = logging.LogRecord(
        "uvicorn.error",
        logging.WARNING,
        "",
        0,
        "Dropped 8 off-region retrieved documents",
        (),
        None,
    )

    formatted = EvaluationLogFormatter(use_color=False).format(record)

    assert formatted.startswith("[EVAL][GEO-FILTER] ")


def test_code_metrics_do_not_score_claim_language_with_keyword_matching():
    case = {
        "case_id": "claim",
        "name": "claim",
        "expected_claim_limits": ["가격 단정 표현"],
        "expected_min_products": 1,
    }
    context = {
        "run_id": "run_eval_claim",
        "status": "awaiting_approval",
        "final_output": {
            "retrieved_documents": [{"doc_id": "doc:1", "title": "근거"}],
            "products": [
                {
                    "id": "product_1",
                    "source_ids": ["doc:1"],
                    "one_liner": "가격 1만원으로 즐기는 상품",
                    "not_to_claim": [],
                    "claim_limits": [],
                }
            ],
            "marketing_assets": [],
            "qa_report": {"issues": []},
        },
        "cost_total_usd": 0,
        "latency_ms": 10,
        "enrichment_tool_calls": [],
    }

    result = evaluate_case(case, context)

    metric_names = {item["name"] for item in result["metrics"]}
    assert "claim_limit_compliance" not in metric_names
    assert "qa_issue_detection" not in metric_names
    assert result["status"] == "passed"


def test_controlled_exit_does_not_penalize_retrieval_metrics():
    case = {
        "case_id": "foreign_exit",
        "name": "foreign exit",
        "expected_geo": {"status": "unsupported"},
        "expected_min_products": 0,
    }
    context = {
        "run_id": "run_eval_foreign_exit",
        "status": "failed",
        "final_output": {
            "status": "unsupported_destination",
            "geo_scope": {"status": "unsupported"},
            "retrieved_documents": [],
        },
        "cost_total_usd": 0,
        "latency_ms": 10,
        "enrichment_tool_calls": [],
    }

    result = evaluate_case(case, context)

    retrieval_metric = next(item for item in result["metrics"] if item["name"] == "retrieval_result_count")
    indexed_metric = next(item for item in result["metrics"] if item["name"] == "source_document_indexed_count")
    assert retrieval_metric["score"] is None
    assert retrieval_metric["value"] == "not_applicable"
    assert retrieval_metric["not_applicable_reason"]
    assert retrieval_metric["evaluator_type"] == "code"
    assert indexed_metric["score"] is None
    assert indexed_metric["value"] == "not_applicable"
    assert indexed_metric["not_applicable_reason"]
    product_metric = next(item for item in result["metrics"] if item["name"] == "product_count_satisfaction")
    assert product_metric["score"] is None
    assert product_metric["value"] == "not_applicable"


def test_clarification_metric_does_not_pass_on_unrelated_candidate_text():
    case = {
        "case_id": "ambiguous_junggu",
        "name": "ambiguous junggu",
        "expected_geo": {"status": "needs_clarification"},
        "expected_min_products": 0,
    }
    context = {
        "run_id": "run_eval_ambiguous_junggu",
        "status": "awaiting_approval",
        "final_output": {
            "geo_scope": {
                "status": "resolved",
                "needs_clarification": False,
                "locations": [
                    {
                        "ldong_regn_cd": "11",
                        "ldong_signgu_cd": "140",
                    }
                ],
            },
            "products": [{"title": "후보 상품", "source_ids": []}],
            "retrieved_documents": [],
        },
        "cost_total_usd": 0,
        "latency_ms": 10,
        "enrichment_tool_calls": [],
    }

    result = evaluate_case(case, context)

    metric = next(item for item in result["metrics"] if item["name"] == "unsupported_or_clarification_accuracy")
    assert metric["passed"] is False
    assert metric["score"] == 0.0


def test_geo_keyword_uses_exact_token_match_not_substring():
    context = {
        "run_id": "run_eval_geo_keyword",
        "status": "awaiting_approval",
        "final_output": {
            "geo_scope": {
                "status": "resolved",
                "locations": [{"keyword": "대청도", "sub_area_terms": ["대청도"]}],
                "keywords": ["대청도"],
            }
        },
        "cost_total_usd": 0,
        "latency_ms": 10,
        "enrichment_tool_calls": [],
    }

    passing = evaluate_case({"case_id": "geo_ok", "expected_geo": {"keyword_contains": "대청도"}}, context)
    failing = evaluate_case({"case_id": "geo_bad", "expected_geo": {"keyword_contains": "청도"}}, context)

    passing_metric = next(item for item in passing["metrics"] if item["name"] == "geo_resolution_accuracy")
    failing_metric = next(item for item in failing["metrics"] if item["name"] == "geo_resolution_accuracy")
    assert passing_metric["passed"] is True
    assert failing_metric["passed"] is False


def test_partial_retrieval_metric_explains_score():
    case = {"case_id": "partial_retrieval", "name": "partial retrieval"}
    context = {
        "run_id": "run_eval_partial",
        "status": "awaiting_approval",
        "final_output": {
            "retrieved_documents": [{"doc_id": "doc:1"}, {"doc_id": "doc:2"}],
            "retrieval_diagnostics": {
                "vector_search_result_count": 4,
                "post_geo_filter_result_count": 2,
                "indexed_document_count": 2,
            },
        },
        "cost_total_usd": 0,
        "latency_ms": 10,
        "enrichment_tool_calls": [],
    }

    result = evaluate_case(case, context)

    retrieval_metric = next(item for item in result["metrics"] if item["name"] == "retrieval_result_count")
    assert retrieval_metric["score"] == 0.6667
    assert retrieval_metric["value"]["expected_min_count_for_full_score"] == 3
    assert "2개" in retrieval_metric["reason"]
    assert retrieval_metric["expected"]
    assert "2개" in retrieval_metric["actual"]
    assert retrieval_metric["penalty_reason"]
    assert retrieval_metric["next_check"]


def test_metric_explainability_fields_are_added():
    case = {
        "case_id": "source_explainability",
        "name": "source explainability",
        "expected_min_products": 1,
    }
    context = {
        "run_id": "run_eval_source_explainability",
        "status": "awaiting_approval",
        "final_output": {
            "retrieved_documents": [{"doc_id": "doc:1", "title": "근거"}],
            "products": [
                {
                    "id": "product_1",
                    "source_ids": ["doc:1"],
                }
            ],
        },
        "cost_total_usd": 0,
        "latency_ms": 10,
        "enrichment_tool_calls": [],
    }

    result = evaluate_case(case, context)

    metric = next(item for item in result["metrics"] if item["name"] == "product_source_id_validity")
    assert metric["evaluator_type"] == "code"
    assert "source_ids" in metric["principle"]
    assert metric["expected"]
    assert "잘못된 source_id 연결은 0개" in metric["actual"]
    assert metric["next_check"]


def test_regression_dataset_loads():
    cases = load_dataset("regression")

    case_ids = {case["case_id"] for case in cases}
    assert "reg_geo_daecheongdo_not_cheongdo" in case_ids
    assert "reg_geo_busan_pet_not_banryeodong" in case_ids
    assert "reg_geo_multi_region_route_unsupported" in case_ids
    assert all("tags" in case for case in cases)


def test_quality_dataset_loads():
    cases = load_dataset("quality")

    case_ids = {case["case_id"] for case in cases}
    assert {
        "quality_general_tour_product",
        "quality_wellness_claim_risk",
        "quality_pet_claim_risk",
        "quality_visual_license_risk",
        "quality_signal_claim_risk",
    } <= case_ids
    assert all("llm-judge" in case.get("tags", []) for case in cases)


def test_eval_runner_does_not_call_llm_judge_by_default(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "evaluation_report_dir", str(tmp_path / "reports"))
    monkeypatch.setattr(eval_runner, "DATASET_DIR", tmp_path)
    _write_single_case_dataset(tmp_path)
    run_id = _create_reusable_eval_run()

    def fail_if_called(**kwargs):
        raise AssertionError("LLM judge should be disabled by default")

    monkeypatch.setattr(eval_runner, "run_llm_judges", fail_if_called)

    report, _path = run_evaluation(dataset="custom", reuse_run_id=run_id, sleep_between_cases=0)

    metric_names = {metric["name"] for metric in report["cases"][0]["metrics"]}
    assert "product_quality_judge" not in metric_names
    assert report["options"]["enable_llm_judge"] is False


def test_eval_runner_adds_fake_llm_judge_metrics_when_enabled(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "evaluation_report_dir", str(tmp_path / "reports"))
    monkeypatch.setattr(eval_runner, "DATASET_DIR", tmp_path)
    _write_single_case_dataset(tmp_path)
    run_id = _create_reusable_eval_run()

    def fake_judges(**kwargs):
        return [
            {
                "name": "product_quality_judge",
                "passed": True,
                "score": 0.9,
                "value": {"status": "judged"},
                "reason": "상품 품질이 충분합니다.",
                "blocking": False,
                "evaluator_type": "llm",
                "principle": "상품 품질을 LLM으로 보조 평가합니다.",
                "expected": "상품이 구체적이어야 합니다.",
                "actual": "상품이 구체적입니다.",
                "penalty_reason": None,
                "next_check": "Judge 요약을 확인하세요.",
                "not_applicable_reason": None,
                "judge_reasoning_summary": "요청과 상품이 잘 맞습니다.",
                "evidence_quotes_or_refs": ["doc:1"],
            }
        ]

    monkeypatch.setattr(eval_runner, "run_llm_judges", fake_judges)

    report, _path = run_evaluation(
        dataset="custom",
        reuse_run_id=run_id,
        sleep_between_cases=0,
        enable_llm_judge=True,
    )

    metric = next(item for item in report["cases"][0]["metrics"] if item["name"] == "product_quality_judge")
    assert metric["evaluator_type"] == "llm"
    assert metric["judge_reasoning_summary"] == "요청과 상품이 잘 맞습니다."
    assert report["options"]["enable_llm_judge"] is True


def test_eval_runner_llm_judge_failure_is_nonblocking(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "evaluation_report_dir", str(tmp_path / "reports"))
    monkeypatch.setattr(eval_runner, "DATASET_DIR", tmp_path)
    _write_single_case_dataset(tmp_path)
    run_id = _create_reusable_eval_run()

    def fake_judges(**kwargs):
        return [
            {
                "name": "claim_risk_llm_judge",
                "passed": False,
                "score": 0.0,
                "value": {"status": "errored"},
                "reason": "Judge 자체가 실패했습니다.",
                "blocking": False,
                "evaluator_type": "llm",
                "principle": "복합 claim 위험을 LLM으로 보조 평가합니다.",
                "expected": "암시적 claim을 잡아야 합니다.",
                "actual": "Judge 호출 실패",
                "penalty_reason": "Judge 자체가 실패했습니다.",
                "next_check": "Judge log를 확인하세요.",
                "not_applicable_reason": None,
                "judge_reasoning_summary": "LLM judge 호출 실패",
                "evidence_quotes_or_refs": [],
            }
        ]

    monkeypatch.setattr(eval_runner, "run_llm_judges", fake_judges)

    report, _path = run_evaluation(
        dataset="custom",
        reuse_run_id=run_id,
        sleep_between_cases=0,
        enable_llm_judge=True,
    )

    case = report["cases"][0]
    metric = next(item for item in case["metrics"] if item["name"] == "claim_risk_llm_judge")
    assert metric["passed"] is False
    assert metric["blocking"] is False
    assert case["status"] == "passed"


def test_eval_runner_smoke_writes_skipped_report_without_live_api(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "evaluation_report_dir", str(tmp_path))

    report, path = run_evaluation(
        dataset="smoke",
        name="Smoke test custom name",
        limit=1,
        no_live_api=True,
        sleep_between_cases=0,
        stop_on_first_failure=True,
    )

    assert path.exists()
    assert report["summary"]["skipped_count"] == 1
    assert report["cases"][0]["status"] == "skipped"
    assert report["name"] == "Smoke test custom name"
    assert report["options"]["name"] == "Smoke test custom name"
    assert report["options"]["sleep_between_cases"] == 0
    assert report["options"]["stop_on_first_failure"] is True


def test_evaluations_api_reads_file_reports(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "evaluation_report_dir", str(tmp_path))
    report = {
        "eval_id": "test_eval",
        "name": "사용자 지정 평가 이름",
        "dataset": "smoke",
        "started_at": "2026-05-12T00:00:00Z",
        "finished_at": "2026-05-12T00:00:01Z",
        "summary": {
            "case_count": 1,
            "passed_count": 1,
            "failed_count": 0,
            "skipped_count": 0,
            "average_score": 1,
            "llm_cost_usd": 0.01,
            "llm_cost_krw": 14.6,
            "latency_ms": 1000,
        },
        "cases": [{"case_id": "case_1", "status": "passed", "metrics": []}],
        "options": {},
    }
    write_evaluation_report(report, report_dir=tmp_path)
    client = TestClient(app)

    listed = client.get("/api/evaluations")
    assert listed.status_code == 200
    assert listed.json()["data"][0]["eval_id"] == "test_eval"
    assert listed.json()["data"][0]["name"] == "사용자 지정 평가 이름"

    detail = client.get("/api/evaluations/test_eval")
    assert detail.status_code == 200
    assert detail.json()["data"]["name"] == "사용자 지정 평가 이름"
    assert detail.json()["data"]["cases"][0]["case_id"] == "case_1"

    cases = client.get("/api/evaluations/test_eval/cases")
    assert cases.status_code == 200
    assert cases.json()["data"][0]["status"] == "passed"


def test_evaluations_api_deletes_selected_file_reports(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "evaluation_report_dir", str(tmp_path))
    base_report = {
        "dataset": "smoke",
        "started_at": "2026-05-12T00:00:00Z",
        "finished_at": "2026-05-12T00:00:01Z",
        "summary": {
            "case_count": 1,
            "passed_count": 1,
            "failed_count": 0,
            "skipped_count": 0,
            "average_score": 1,
            "llm_cost_usd": 0.01,
            "llm_cost_krw": 14.6,
            "latency_ms": 1000,
        },
        "cases": [{"case_id": "case_1", "status": "passed", "metrics": []}],
        "options": {},
    }
    with SessionLocal() as db:
        eval_run = models.WorkflowRun(
            template_id="default_product_planning",
            status="awaiting_approval",
            input={
                "message": "eval run",
                "_evaluation": {"eval_id": "delete_me", "case_id": "case_1"},
            },
        )
        db.add(eval_run)
        db.commit()
        eval_run_id = eval_run.id

    delete_report = {
        "eval_id": "delete_me",
        **base_report,
        "cases": [{**base_report["cases"][0], "workflow_run_id": eval_run_id}],
    }
    write_evaluation_report(delete_report, report_dir=tmp_path)
    write_evaluation_report({"eval_id": "keep_me", **base_report}, report_dir=tmp_path)
    client = TestClient(app)

    deleted = client.post("/api/evaluations/delete", json={"eval_ids": ["delete_me"]})
    assert deleted.status_code == 200
    assert deleted.json()["data"]["deleted_eval_ids"] == ["delete_me"]
    assert deleted.json()["data"]["deleted_workflow_run_ids"] == [eval_run_id]
    assert not (tmp_path / "eval_delete_me.json").exists()
    with SessionLocal() as db:
        assert db.get(models.WorkflowRun, eval_run_id) is None

    listed = client.get("/api/evaluations")
    assert listed.status_code == 200
    eval_ids = [item["eval_id"] for item in listed.json()["data"]]
    assert eval_ids == ["keep_me"]

    missing = client.get("/api/evaluations/delete_me")
    assert missing.status_code == 404


def test_evaluations_api_deletes_running_report_and_active_workflow_run(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "evaluation_report_dir", str(tmp_path))
    with SessionLocal() as db:
        eval_run = models.WorkflowRun(
            template_id="default_product_planning",
            status="running",
            input={
                "message": "running eval run",
                "_evaluation": {"eval_id": "running_delete_me", "case_id": "case_1"},
            },
        )
        db.add(eval_run)
        db.commit()
        eval_run_id = eval_run.id

    report = {
        "eval_id": "running_delete_me",
        "name": "Running eval",
        "dataset": "smoke",
        "status": "running",
        "started_at": "2026-05-12T00:00:00Z",
        "finished_at": None,
        "process": {"pid": os.getpid(), "started_at": "2026-05-12T00:00:00Z"},
        "active_case": {
            "case_id": "case_1",
            "name": "case 1",
            "index": 1,
            "total": 1,
            "workflow_run_id": eval_run_id,
        },
        "summary": {
            "case_count": 0,
            "passed_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "average_score": None,
            "llm_cost_usd": 0,
            "llm_cost_krw": 0,
            "latency_ms": 0,
        },
        "total_case_count": 1,
        "cases": [],
        "options": {},
    }
    write_evaluation_report(report, report_dir=tmp_path)
    client = TestClient(app)

    deleted = client.post("/api/evaluations/delete", json={"eval_ids": ["running_delete_me"]})

    assert deleted.status_code == 200
    data = deleted.json()["data"]
    assert data["deleted_eval_ids"] == ["running_delete_me"]
    assert data["deleted_workflow_run_ids"] == [eval_run_id]
    assert data["terminated_eval_processes"][0]["status"] == "skipped_current_process"
    assert not (tmp_path / "eval_running_delete_me.json").exists()
    with SessionLocal() as db:
        assert db.get(models.WorkflowRun, eval_run_id) is None


def test_running_report_without_live_process_is_marked_stopped(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "evaluation_report_dir", str(tmp_path))
    report = {
        "eval_id": "stale_running",
        "name": "stale",
        "dataset": "smoke",
        "status": "running",
        "started_at": "2026-05-12T00:00:00Z",
        "finished_at": None,
        "summary": {
            "case_count": 0,
            "passed_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "average_score": None,
            "llm_cost_usd": 0,
            "llm_cost_krw": 0,
            "latency_ms": 0,
        },
        "total_case_count": 1,
        "cases": [],
        "options": {},
    }
    write_evaluation_report(report, report_dir=tmp_path)

    listed = list_evaluation_reports(report_dir=tmp_path)
    detail = read_evaluation_report("stale_running", report_dir=tmp_path)

    assert listed[0]["status"] == "stopped"
    assert detail is not None
    assert detail["status"] == "stopped"
    assert detail["stop_reason"] == "missing_process_metadata"


def _write_single_case_dataset(path):
    case = {
        "case_id": "custom_case",
        "name": "custom case",
        "input": {"message": "테스트 상품 1개", "product_count": 1},
        "expected_min_products": 1,
        "expected_claim_limits": [],
        "expected_source_families": [],
        "requires_live_api": False,
        "requires_llm": False,
        "tags": ["test"],
    }
    (path / "custom.jsonl").write_text(json.dumps(case, ensure_ascii=False) + "\n", encoding="utf-8")


def _create_reusable_eval_run() -> str:
    init_db()
    with SessionLocal() as db:
        run = models.WorkflowRun(
            template_id="default_product_planning",
            status="awaiting_approval",
            input={"message": "eval reusable run", "product_count": 1},
            final_output={
                "retrieved_documents": [{"doc_id": "doc:1", "title": "근거"}],
                "products": [
                    {
                        "id": "product_1",
                        "title": "근거 기반 상품",
                        "one_liner": "근거 기반 상품입니다.",
                        "source_ids": ["doc:1"],
                        "claim_limits": [],
                        "not_to_claim": [],
                    }
                ],
                "marketing_assets": [],
                "qa_report": {"issues": []},
            },
            cost_total_usd=0,
            latency_ms=10,
        )
        db.add(run)
        db.commit()
        return run.id
