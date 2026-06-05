import copy
import json

import pytest

from fastapi.testclient import TestClient

from app.agents.workflow import (
    _marketing_prompt,
    _product_prompt,
    _filter_retrieved_documents_by_geo_scope,
    _merge_retrieved_documents,
    _source_item_documents,
    marketing_agent,
    validate_marketing_assets,
    validate_products,
    validate_qa_report,
)
from app.core.config import get_settings
from app.db import models
from app.db.session import SessionLocal
from app.llm.gemini_gateway import GeminiJsonResult
from app.main import app


DOCS = [
    {
        "doc_id": "doc_1",
        "title": "갑천 야간 산책",
        "snippet": "갑천 주변 야간 산책과 수변 경관을 소개하는 근거입니다.",
        "metadata": {"content_type": "attraction"},
    },
    {
        "doc_id": "doc_2",
        "title": "갈마공원",
        "snippet": "갈마공원 위치와 주변 산책 정보를 제공하는 근거입니다.",
        "metadata": {"content_type": "attraction"},
    },
]

MANY_DOCS = [
    *DOCS,
    *[
        {
            "doc_id": f"doc_{index}",
            "title": f"추가 근거 {index}",
            "snippet": f"추가 관광 근거 {index}입니다.",
            "metadata": {"content_type": "attraction"},
        }
        for index in range(3, 26)
    ],
]


EVIDENCE_CONTEXT = {
    "source_confidence": 0.72,
    "data_coverage": {"detail_coverage": 0.5, "image_coverage": 0.2},
    "productization_advice": {
        "usable_claims": ["장소명, 주소, 개요는 근거와 함께 사용할 수 있습니다."],
        "candidate_evidence_cards": [
            {
                "content_id": "100",
                "source_item_id": "item_1",
                "title": "갑천 야간 산책",
                "address": "대전광역시",
                "evidence_strength": "medium",
                "usable_facts": [{"field": "개요", "value": "수변 산책 근거", "source": "TourAPI"}],
                "experience_hooks": ["수변 산책"],
                "recommended_product_angles": ["야간 산책 코스"],
                "operational_unknowns": ["missing_price_or_fee"],
                "restricted_claims": ["가격 확정"],
                "evidence_document_ids": ["doc_1"],
            }
        ],
    },
    "unresolved_gaps": [
        {
            "gap_type": "missing_price_or_fee",
            "severity": "medium",
            "reason": "요금 정보 근거가 없어 운영자 확인이 필요합니다.",
            "target_item_id": "item_1",
            "target_content_id": "100",
            "source_item_title": "갑천 야간 산책",
        }
    ],
    "ui_highlights": [{"title": "요금 확인 필요", "body": "가격은 아직 확정할 수 없습니다.", "severity": "warning"}],
}


def _product_payload(count: int = 2) -> dict:
    return {
        "products": [
            {
                "id": f"product_{index + 1}",
                "title": f"대전 수변 산책 상품 {index + 1}",
                "one_liner": "근거 문서를 바탕으로 구성한 야간 산책 상품입니다.",
                "target_customer": "외국인",
                "core_value": ["야간 산책", "수변 경관"],
                "itinerary": [{"order": 1, "name": "갑천 산책", "source_id": "doc_1"}],
                "estimated_duration": "2시간",
                "operation_difficulty": "보통",
                "source_ids": ["doc_1"],
                "assumptions": ["세부 운영 조건은 운영자가 확인해야 합니다."],
                "not_to_claim": ["가격 확정"],
                "evidence_summary": "갑천 야간 산책 근거를 사용했습니다.",
                "needs_review": ["요금 정보는 운영자 확인이 필요합니다."],
                "coverage_notes": ["일부 상세 정보가 부족합니다."],
                "claim_limits": ["가격 단정 금지"],
            }
            for index in range(count)
        ]
    }


def _marketing_payload(*, sns_bodies: list[str]) -> dict:
    return {
        "marketing_assets": [
            {
                "product_id": "product_1",
                "sales_copy": {
                    "headline": "대전 수변 산책",
                    "subheadline": "근거 기반 산책 상품입니다.",
                    "sections": [{"title": "핵심", "body": "수변 산책 근거를 중심으로 구성합니다."}],
                    "disclaimer": "세부 요금은 운영자가 최종 확인해야 합니다.",
                },
                "faq": [
                    {
                        "question": "누구에게 추천하나요?",
                        "answer": "대전의 수변 분위기를 가볍게 경험하고 싶은 외국인 관광객에게 추천합니다.",
                    },
                    {"question": "가격이 확정됐나요?", "answer": "가격은 운영자가 확인해야 합니다."},
                ],
                "sns_campaign": {
                    "campaign_angles": [{"angle": "대전 수변 야간 산책", "rationale": "수변 경관과 밤 산책 장면이 SNS hook으로 적합합니다."}],
                    "posts": [
                        {"format": "feed", "hook": body.split()[0] if body.split() else "대전 수변 산책", "body": body, "hashtags": ["#대전여행"]}
                        for body in sns_bodies
                    ],
                    "visual_direction": ["수변 산책로의 저녁 분위기"],
                },
                "search_keywords": ["대전", "수변 산책"],
                "evidence_disclaimer": "요금 정보는 운영자 확인 후 게시하세요.",
                "claim_limits": ["무료 여부 단정 금지"],
            }
        ]
    }


def _marketing_payload_for_products(product_ids: list[str], *, sns_bodies: list[str]) -> dict:
    template = _marketing_payload(sns_bodies=sns_bodies)["marketing_assets"][0]
    return {"marketing_assets": [dict(copy.deepcopy(template), product_id=product_id) for product_id in product_ids]}


def _marketing_strategy_pack() -> dict:
    return {
        "marketing_strategy": {
            "target_segment": {
                "primary": "대전의 수변 분위기를 부담 없이 경험하고 싶은 외국인 관광객",
                "secondary": ["야간 산책을 선호하는 커플", "가벼운 로컬 경험을 찾는 소규모 여행자"],
                "foreigner_context": "처음 방문한 외국인도 지역 분위기를 이해하기 쉬운 산책형 상품으로 안내합니다.",
            },
            "product_positioning": {
                "summary": "대전 수변의 밤 분위기를 가볍게 경험하는 입문형 산책 상품",
                "differentiation": "실제 수변 산책 근거를 중심으로 무리한 운영 조건을 단정하지 않는 점이 강점입니다.",
            },
            "key_selling_points": [
                {
                    "point": "수변 경관을 중심으로 한 야간 산책 경험",
                    "evidence_basis": "갑천 주변 야간 산책과 수변 경관 근거가 확인됩니다.",
                    "usage_note": "상세페이지 첫 화면과 SNS hook에 활용합니다.",
                }
            ],
            "customer_objections": [
                {
                    "objection": "요금이나 운영시간이 확정됐는지 궁금할 수 있습니다.",
                    "response": "게시 전 운영자가 최종 확인한 뒤 안내한다고 설명합니다.",
                    "requires_confirmation": True,
                }
            ],
            "operation_checklist": [
                {"item": "요금과 운영시간 확인", "reason": "근거에 확정 정보가 부족해 게시 전 확인이 필요합니다."}
            ],
        },
        "landing_page_outline": {
            "hero": {
                "headline": "대전의 밤을 천천히 걷는 수변 산책",
                "subheadline": "외국인 관광객도 부담 없이 지역 분위기를 느낄 수 있는 코스",
                "hook": "처음 방문한 대전이라면 밤의 수변 분위기부터 가볍게 시작해 보세요.",
            },
            "why_this_product": ["수변 경관과 산책 근거를 중심으로 구성한 입문형 상품입니다."],
            "evidence_backed_points": [
                {
                    "point": "갑천 주변 수변 산책 경험",
                    "evidence_basis": "갑천 야간 산책 근거에서 수변 경관 맥락을 확인할 수 있습니다.",
                }
            ],
            "practical_info": ["요금과 운영시간은 게시 전 운영자가 확인해야 합니다."],
        },
        "faq_strategy": {
            "buyer_faq": [
                {
                    "question": "어떤 여행자에게 잘 맞나요?",
                    "answer": "대전의 로컬 분위기를 가볍게 느끼고 싶은 외국인 관광객에게 잘 맞습니다.",
                }
            ],
            "operation_faq": [
                {
                    "question": "요금과 운영시간은 확정됐나요?",
                    "answer": "게시 전 운영자가 요금과 운영시간을 최종 확인해야 합니다.",
                }
            ],
        },
        "sns_campaign": {
            "campaign_angles": [
                {"angle": "대전 수변 야간 산책", "rationale": "수변 경관과 밤 산책 장면이 SNS hook으로 적합합니다."}
            ],
            "posts": [
                {
                    "format": "feed",
                    "hook": "대전의 밤을 천천히 걷고 싶다면",
                    "body": "갑천 주변 수변 분위기를 중심으로 가볍게 즐기는 산책 상품을 검토해 보세요.",
                    "hashtags": ["#대전여행", "#수변산책"],
                }
            ],
            "visual_direction": ["수변 산책로의 저녁 분위기", "걷는 장면과 주변 경관"],
        },
        "claim_strategy": {
            "usable_claims": [
                {
                    "claim": "수변 경관을 중심으로 한 산책 경험을 제안할 수 있습니다.",
                    "evidence_basis": "갑천 주변 산책과 수변 경관 근거가 확인됩니다.",
                }
            ],
            "caution_phrasing": [
                {"phrase": "요금과 운영시간", "reason": "근거에 확정 정보가 부족합니다."},
                {"phrase": "무료로 언제나 이용 가능", "reason": "요금과 운영시간 근거가 부족합니다."}
            ],
        },
    }


def test_product_prompt_includes_evidence_fusion_context_and_avoid_rules():
    prompt = _product_prompt(
        {"product_count": 2, "target_customer": "외국인", "avoid": ["무리한 도보"]},
        {"summary": "근거 기반 상품화를 준비합니다."},
        DOCS,
        evidence_context=EVIDENCE_CONTEXT,
        source_items=[{"id": "item_1", "title": "갑천 야간 산책", "content_id": "100"}],
        qa_settings={"avoid": ["무리한 도보"]},
    )

    assert "evidence_based_generation_context" in prompt
    assert "candidate_evidence_cards" in prompt
    assert "unresolved_gaps" in prompt
    assert "무리한 도보" in prompt
    assert "운영시간, 요금, 예약 가능 여부" in prompt
    assert "상품성_기준" in prompt
    assert "같은 제목 패턴" in prompt


def test_marketing_prompt_includes_phase19_quality_rules():
    products = validate_products(
        _product_payload(1),
        {"product_count": 1, "target_customer": "외국인"},
        DOCS,
        evidence_context=EVIDENCE_CONTEXT,
    )

    prompt = _marketing_prompt(
        products,
        DOCS,
        evidence_context=EVIDENCE_CONTEXT,
        qa_settings={"avoid": ["가격 단정 표현"]},
    )

    assert "마케팅_출력_품질_기준" in prompt
    assert "상품별_차별화_지시" in prompt
    assert "근거_안전_마케팅_정책" in prompt
    assert "구매 전 궁금증" in prompt
    assert "첫 문장에 hook" in prompt
    assert "not_to_claim, claim_limits, source_id" in prompt
    assert "Marketing_Strategy_Pack_출력_형식" in prompt
    assert "marketing_strategy" in prompt
    assert "landing_page_outline" in prompt
    assert "faq_strategy" in prompt
    assert "sns_campaign" in prompt
    assert "claim_strategy" in prompt
    assert "관광상품 판매 기획서" in prompt


def test_product_prompt_prioritizes_evidence_card_document_ids():
    docs = [
        {
            "doc_id": f"doc:tourapi:content:{index}",
            "title": f"일반 근거 {index}",
            "snippet": "일반 근거입니다.",
            "metadata": {"content_id": str(index), "source_family": "kto_tourapi_kor"},
        }
        for index in range(20)
    ]
    docs.append(
        {
            "doc_id": "doc:theme:kto_audio:story",
            "title": "1. 국립일제강제동원역사관과 기억의 터널",
            "snippet": "국립일제강제동원역사관 오디오 해설 스토리입니다.",
            "metadata": {"content_id": "2551424", "source_family": "kto_audio"},
        }
    )
    evidence_context = {
        "productization_advice": {
            "candidate_evidence_cards": [
                {
                    "content_id": "2551424",
                    "source_item_id": "tourapi:content:2551424",
                    "title": "국립일제강제동원역사관",
                    "evidence_document_ids": ["doc:theme:kto_audio:story"],
                }
            ]
        }
    }

    prompt = _product_prompt(
        {"product_count": 3, "target_customer": "외국인"},
        {"summary": "근거 기반 상품화를 준비합니다."},
        docs,
        evidence_context=evidence_context,
        source_items=[],
    )

    assert "doc:theme:kto_audio:story" in prompt
    assert "국립일제강제동원역사관과 기억의 터널" in prompt


def test_validate_products_uses_only_real_doc_ids_and_adds_evidence_fields():
    payload = _product_payload(2)
    payload["products"][0]["source_ids"] = ["missing_doc", "doc_1"]

    products = validate_products(
        payload,
        {"product_count": 2, "target_customer": "외국인", "avoid": ["무리한 도보"]},
        DOCS,
        evidence_context=EVIDENCE_CONTEXT,
        qa_settings={"avoid": ["무리한 도보"]},
    )

    assert len(products) == 2
    assert products[0]["source_ids"] == ["doc_1"]
    assert "missing_doc" not in products[0]["source_ids"]
    assert products[0]["evidence_summary"]
    assert not any("source id" in item for item in products[0]["needs_review"])
    assert any(
        item.get("category") == "source_id_guardrail" and item.get("invalid_source_id") == "missing_doc"
        for item in products[0].get("internal_diagnostics", [])
    )
    assert any(
        note.get("audience") == "user" and note.get("category") == "copy_caution"
        for note in products[0].get("review_notes", [])
    )
    assert "가격, 무료 여부, 할인율 단정" in products[0]["claim_limits"]
    assert "요청 avoid 기준: 무리한 도보" in products[0]["claim_limits"]


def test_validate_products_does_not_fallback_to_generic_sources_when_source_ids_are_invalid():
    payload = _product_payload(1)
    payload["products"][0]["title"] = "근거 없는 새 상품"
    payload["products"][0]["one_liner"] = "연결할 수 있는 직접 근거가 없는 상품입니다."
    payload["products"][0]["core_value"] = ["새 경험"]
    payload["products"][0]["evidence_summary"] = ""
    payload["products"][0]["source_ids"] = ["missing_doc"]
    payload["products"][0]["itinerary"] = [{"order": 1, "name": "근거 없는 일정", "source_id": "missing_doc"}]

    products = validate_products(
        payload,
        {"product_count": 1, "target_customer": "외국인"},
        DOCS,
        evidence_context=EVIDENCE_CONTEXT,
    )

    assert products[0]["source_ids"] == []
    assert products[0]["itinerary"][0]["source_id"] == ""
    assert products[0]["evidence_summary"] == "연결된 근거가 부족해 운영자 확인이 필요합니다."
    assert not any("실제 근거 목록에 없는 source id" in item for item in products[0]["needs_review"])
    assert any("근거 문서가 없어" in item for item in products[0]["needs_review"])
    assert any(
        note.get("audience") == "user"
        and note.get("category") == "publish_check"
        and "근거 문서가 없어" in str(note.get("message"))
        for note in products[0].get("review_notes", [])
    )
    assert not any("서버가 사용 가능한 근거를 보정" in item for item in products[0]["needs_review"])
    assert products[0]["internal_diagnostics"][0]["category"] == "source_id_guardrail"
    assert products[0]["internal_diagnostics"][0]["invalid_source_id"] == "missing_doc"
    assert products[0]["internal_diagnostics"][0]["action"] == "excluded"
    assert products[0]["internal_diagnostics"][0]["reason"] == "source_id_not_in_allowed_documents"


def test_validate_products_repairs_source_item_id_to_real_doc_id_without_generic_fallback():
    docs = [
        {
            "doc_id": "doc:tourapi:content:2551424",
            "title": "국립일제강제동원역사관",
            "snippet": "일제강제동원 피해 역사를 다루는 역사관입니다.",
            "metadata": {
                "content_id": "2551424",
                "source_item_id": "tourapi:content:2551424",
                "source_family": "kto_tourapi_kor",
            },
        },
        {
            "doc_id": "doc:theme:kto_audio:test",
            "title": "국립일제강제동원역사관과 기억의 터널",
            "snippet": "국립일제강제동원역사관 오디오 해설입니다.",
            "metadata": {
                "content_id": "2551424",
                "source_item_id": "tourapi:content:2551424",
                "source_family": "kto_audio",
            },
        },
    ]
    payload = _product_payload(1)
    payload["products"][0]["title"] = "부산의 아픈 역사, 국립일제강제동원역사관 탐방"
    payload["products"][0]["source_ids"] = ["tourapi:content:2551424"]

    products = validate_products(
        payload,
        {"product_count": 1, "target_customer": "외국인"},
        docs,
        evidence_context={},
    )

    assert products[0]["source_ids"] == ["doc:tourapi:content:2551424", "doc:theme:kto_audio:test"]
    assert products[0]["internal_diagnostics"][0]["action"] == "normalized"
    assert products[0]["internal_diagnostics"][0]["normalized_to"] == "doc:tourapi:content:2551424"
    assert not any("근거 문서가 없어" in item for item in products[0]["needs_review"])


def test_validate_products_adds_directly_linked_supporting_evidence_documents():
    docs = [
        {
            "doc_id": "doc:tourapi:content:2551424",
            "title": "국립일제강제동원역사관",
            "snippet": "일제강제동원 피해 역사를 다루는 역사관입니다.",
            "metadata": {
                "content_id": "2551424",
                "source_item_id": "tourapi:content:2551424",
                "source_family": "kto_tourapi_kor",
            },
        },
        {
            "doc_id": "doc:theme:kto_audio:story",
            "title": "1. 국립일제강제동원역사관과 기억의 터널",
            "snippet": "국립일제강제동원역사관 오디오 해설 스토리입니다.",
            "metadata": {
                "content_id": "2551424",
                "source_item_id": "tourapi:content:2551424",
                "source_family": "kto_audio",
            },
        },
        {
            "doc_id": "doc:theme:kto_audio:other",
            "title": "영도다리 오디오 해설",
            "snippet": "다른 장소의 오디오 해설입니다.",
            "metadata": {
                "content_id": "999999",
                "source_item_id": "tourapi:content:999999",
                "source_family": "kto_audio",
            },
        },
    ]
    payload = _product_payload(1)
    payload["products"][0]["title"] = "부산의 아픈 역사, 국립일제강제동원역사관 탐방"
    payload["products"][0]["source_ids"] = ["doc:tourapi:content:2551424"]
    payload["products"][0]["evidence_summary"] = "국립일제강제동원역사관의 개요를 바탕으로 구성했습니다."

    products = validate_products(
        payload,
        {"product_count": 1, "target_customer": "외국인"},
        docs,
        evidence_context={},
    )

    assert products[0]["source_ids"] == [
        "doc:tourapi:content:2551424",
        "doc:theme:kto_audio:story",
    ]
    assert "국립일제강제동원역사관과 기억의 터널" in products[0]["evidence_summary"]
    assert "doc:theme:kto_audio:other" not in products[0]["source_ids"]


def test_validate_products_strictly_infers_source_id_from_exact_evidence_title():
    docs = [
        {
            "doc_id": "doc:tourapi:content:3303393",
            "title": "부산 밀 페스티벌",
            "snippet": "밀을 주제로 세계 식문화를 탐험하는 축제입니다.",
            "metadata": {"content_id": "3303393", "source_family": "kto_tourapi_kor"},
        },
        {
            "doc_id": "doc:tourapi:content:2818494",
            "title": "부산가족축제",
            "snippet": "가족 체험 축제입니다.",
            "metadata": {"content_id": "2818494", "source_family": "kto_tourapi_kor"},
        },
    ]
    payload = _product_payload(1)
    payload["products"][0]["title"] = "부산의 맛, 밀 페스티벌에서 세계 식문화를 탐험하다"
    payload["products"][0]["source_ids"] = []

    products = validate_products(
        payload,
        {"product_count": 1, "target_customer": "외국인"},
        docs,
        evidence_context={},
    )

    assert products[0]["source_ids"] == ["doc:tourapi:content:3303393"]
    assert not any("근거 문서가 없어" in item for item in products[0]["needs_review"])


def test_validate_products_does_not_infer_unrelated_regional_source():
    docs = [
        {
            "doc_id": "doc:tourapi:content:2818494",
            "title": "부산가족축제",
            "snippet": "가족 체험 축제입니다.",
            "metadata": {"content_id": "2818494", "source_family": "kto_tourapi_kor"},
        }
    ]
    payload = _product_payload(1)
    payload["products"][0]["title"] = "부산 역사 스토리텔링 산책"
    payload["products"][0]["source_ids"] = []

    products = validate_products(
        payload,
        {"product_count": 1, "target_customer": "외국인"},
        docs,
        evidence_context={},
    )

    assert products[0]["source_ids"] == []
    assert any("근거 문서가 없어" in item for item in products[0]["needs_review"])


def test_retrieved_theme_documents_without_strong_match_signals_are_excluded():
    documents = [
        {
            "doc_id": "doc:theme:kto_audio:bad",
            "title": "7코스 안내자 소개",
            "content": "종로에서 만나는 혁명의 길 이야기",
            "metadata": {
                "source_family": "kto_audio",
                "content_type": "theme",
                "ldong_regn_cd": "26",
                "ldong_signgu_cd": "290",
                "theme_match_signals": "[]",
                "first_seen_run_id": "run_test_theme_integrity",
                "last_seen_run_id": "run_test_theme_integrity",
            },
        },
        {
            "doc_id": "doc:theme:kto_audio:good",
            "title": "국립일제강제동원역사관 오디오 해설",
            "content": "국립일제강제동원역사관 전시 해설",
            "metadata": {
                "source_family": "kto_audio",
                "content_type": "theme",
                "ldong_regn_cd": "26",
                "ldong_signgu_cd": "290",
                "theme_match_signals": '["target_title_text_match"]',
                "first_seen_run_id": "run_test_theme_integrity",
                "last_seen_run_id": "run_test_theme_integrity",
            },
        },
    ]

    filtered = _filter_retrieved_documents_by_geo_scope(
        documents,
        geo_scope={"locations": [{"ldong_regn_cd": "26", "ldong_signgu_cd": "290"}]},
        run_id="run_test_theme_integrity",
    )

    assert [document["doc_id"] for document in filtered] == ["doc:theme:kto_audio:good"]


def test_retrieved_enrichment_documents_from_previous_runs_are_not_used_as_backfill():
    documents = [
        {
            "doc_id": "doc:theme:kto_audio:old",
            "title": "영도다리",
            "content": "영도다리 오디오 해설",
            "metadata": {
                "source_family": "kto_audio",
                "content_type": "theme",
                "ldong_regn_cd": "26",
                "ldong_signgu_cd": "320",
                "theme_match_signals": '["target_title_text_match"]',
                "first_seen_run_id": "run_old",
                "last_seen_run_id": "run_old",
            },
        },
        {
            "doc_id": "doc:theme:kto_audio:current",
            "title": "국립일제강제동원역사관 오디오 해설",
            "content": "국립일제강제동원역사관 전시 해설",
            "metadata": {
                "source_family": "kto_audio",
                "content_type": "theme",
                "ldong_regn_cd": "26",
                "ldong_signgu_cd": "290",
                "theme_match_signals": '["target_title_text_match"]',
                "first_seen_run_id": "run_current",
                "last_seen_run_id": "run_current",
            },
        },
        {
            "doc_id": "doc:tourapi:content:2551424",
            "title": "국립일제강제동원역사관",
            "content": "기본 TourAPI 근거",
            "metadata": {
                "source_family": "kto_tourapi_kor",
                "source": "tourapi",
                "content_type": "attraction",
                "ldong_regn_cd": "26",
                "ldong_signgu_cd": "290",
            },
        },
    ]

    filtered = _filter_retrieved_documents_by_geo_scope(
        documents,
        geo_scope={"locations": [{"ldong_regn_cd": "26", "ldong_signgu_cd": "290"}]},
        run_id="run_current",
    )

    assert [document["doc_id"] for document in filtered] == [
        "doc:theme:kto_audio:current",
        "doc:tourapi:content:2551424",
    ]


def test_source_item_documents_are_merged_with_rag_results_for_evidence_fusion():
    with TestClient(app):
        pass

    item_id = "tourapi:test:phase17:source-item-doc"
    with SessionLocal() as db:
        db.merge(
            models.SourceDocument(
                id=f"doc:{item_id}",
                source="tourapi",
                source_item_id=item_id,
                title="글로벌 영도커피페스티벌",
                content="제목: 글로벌 영도커피페스티벌\n개요: 커피 축제 근거",
                document_metadata={
                    "source": "tourapi",
                    "source_family": "kto_tourapi_kor",
                    "source_item_id": item_id,
                    "content_type": "event",
                    "source_role": "runtime_run_evidence",
                },
                embedding_status="indexed",
            )
        )
        db.commit()

        source_item_docs = _source_item_documents(db, [{"id": item_id}])
        merged = _merge_retrieved_documents(
            [{"doc_id": "doc:existing", "title": "기존 RAG 근거", "content": "기존 근거", "metadata": {}}],
            source_item_docs,
        )

    assert [document["doc_id"] for document in merged] == ["doc:existing", f"doc:{item_id}"]
    assert merged[1]["title"] == "글로벌 영도커피페스티벌"


def test_validate_products_caps_requested_count_at_twenty():
    payload = _product_payload(25)

    products = validate_products(
        payload,
        {"product_count": 25, "target_customer": "외국인"},
        MANY_DOCS,
        evidence_context=EVIDENCE_CONTEXT,
    )

    assert len(products) == 20


def test_validate_products_keeps_requested_count_when_evidence_is_short():
    payload = _product_payload(20)

    products = validate_products(
        payload,
        {"product_count": 20, "target_customer": "외국인"},
        DOCS,
        evidence_context=EVIDENCE_CONTEXT,
    )

    assert len(products) == 20
    assert not any("사용 가능한 근거 데이터가" in note for product in products for note in product["coverage_notes"])


def test_validate_products_rejects_less_than_effective_count():
    with pytest.raises(ValueError, match="products are required"):
        validate_products(
            _product_payload(1),
            {"product_count": 3, "target_customer": "외국인"},
            MANY_DOCS,
            evidence_context=EVIDENCE_CONTEXT,
        )


def test_validate_marketing_assets_preserves_evidence_disclaimer_and_claim_limits():
    products = validate_products(
        _product_payload(1),
        {"product_count": 1, "target_customer": "외국인"},
        DOCS,
        evidence_context=EVIDENCE_CONTEXT,
    )
    payload = {
        "marketing_assets": [
            {
                "product_id": "product_1",
                "sales_copy": {
                    "headline": "대전 수변 산책",
                    "subheadline": "근거 기반 산책 상품입니다.",
                    "sections": [{"title": "핵심", "body": "수변 산책 근거를 중심으로 구성합니다."}],
                    "disclaimer": "세부 요금은 운영자가 최종 확인해야 합니다.",
                },
                "faq": [
                    {
                        "question": "누구에게 추천하나요?",
                        "answer": "대전의 수변 분위기를 가볍게 경험하고 싶은 외국인 관광객에게 추천합니다.",
                    },
                    {"question": "가격이 확정됐나요?", "answer": "가격은 운영자가 확인해야 합니다."},
                ],
                "sns_campaign": {
                    "campaign_angles": [{"angle": "대전 수변 산책", "rationale": "수변 산책 장면이 SNS hook으로 적합합니다."}],
                    "posts": [{"format": "feed", "hook": "대전 수변 산책", "body": "대전 수변 산책 상품 초안", "hashtags": ["#대전여행"]}],
                    "visual_direction": ["수변 산책 장면"],
                },
                "search_keywords": ["대전", "수변 산책"],
                "evidence_disclaimer": "요금 정보는 운영자 확인 후 게시하세요.",
                "claim_limits": ["무료 여부 단정 금지"],
            }
        ]
    }

    assets = validate_marketing_assets(payload, products, evidence_context=EVIDENCE_CONTEXT)

    assert assets[0]["evidence_disclaimer"] == "요금 정보는 운영자 확인 후 게시하세요."
    assert "무료 여부 단정 금지" in assets[0]["claim_limits"]
    assert "가격 단정 금지" in assets[0]["claim_limits"]


def test_validate_marketing_assets_accepts_strategy_pack():
    products = validate_products(
        _product_payload(1),
        {"product_count": 1, "target_customer": "외국인"},
        DOCS,
        evidence_context=EVIDENCE_CONTEXT,
    )
    payload = _marketing_payload(sns_bodies=["대전 수변의 밤을 가볍게 걸어보는 외국인 여행 코스입니다. #대전여행"])
    payload["marketing_assets"][0].update(_marketing_strategy_pack())

    assets = validate_marketing_assets(payload, products, evidence_context=EVIDENCE_CONTEXT)
    asset = assets[0]

    assert asset["sales_copy"]["headline"] == "대전 수변 산책"
    assert asset["faq"][0]["question"] == "누구에게 추천하나요?"
    assert asset["sns_campaign"]["posts"]
    assert "무료 여부 단정 금지" in asset["claim_limits"]
    assert asset["marketing_strategy"]["target_segment"]["primary"].startswith("대전의 수변")
    assert asset["marketing_strategy"]["key_selling_points"][0]["evidence_basis"]
    assert asset["landing_page_outline"]["hero"]["headline"].startswith("대전의 밤")
    assert asset["faq_strategy"]["buyer_faq"][0]["question"] == "어떤 여행자에게 잘 맞나요?"
    assert asset["faq_strategy"]["operation_faq"][0]["question"] == "요금과 운영시간은 확정됐나요?"
    assert asset["sns_campaign"]["posts"][0]["hashtags"] == ["#대전여행", "#수변산책"]
    assert asset["claim_strategy"]["usable_claims"][0]["claim"].startswith("수변 경관")
    assert "reasons_to_believe" not in asset["marketing_strategy"]
    assert "recommended_sales_angle" not in asset["marketing_strategy"]
    assert "experience_story" not in asset["landing_page_outline"]
    assert "conversion_cta" not in asset["landing_page_outline"]
    assert asset["claim_strategy"]["caution_phrasing"][0]["phrase"] == "요금과 운영시간"
    assert "safe_alternatives" not in asset["claim_strategy"]
    assert "needs_confirmation" not in asset["claim_strategy"]
    assert "avoid_phrasing" not in asset["claim_strategy"]


def test_validate_marketing_assets_requires_sns_campaign():
    products = validate_products(
        _product_payload(1),
        {"product_count": 1, "target_customer": "외국인"},
        DOCS,
        evidence_context=EVIDENCE_CONTEXT,
    )
    payload = _marketing_payload(sns_bodies=[])
    payload["marketing_assets"][0].pop("sns_campaign")

    with pytest.raises(ValueError, match="sns_campaign must be present"):
        validate_marketing_assets(payload, products, evidence_context=EVIDENCE_CONTEXT)


def test_validate_marketing_assets_normalizes_string_usable_claims():
    products = validate_products(
        _product_payload(1),
        {"product_count": 1, "target_customer": "외국인"},
        DOCS,
        evidence_context=EVIDENCE_CONTEXT,
    )
    payload = _marketing_payload(sns_bodies=["대전 수변의 밤을 가볍게 걸어보는 외국인 여행 코스입니다. #대전여행"])
    strategy_pack = _marketing_strategy_pack()
    strategy_pack["claim_strategy"]["usable_claims"] = ["수변 경관을 중심으로 한 산책 경험을 제안할 수 있습니다."]
    payload["marketing_assets"][0].update(strategy_pack)

    assets = validate_marketing_assets(payload, products, evidence_context=EVIDENCE_CONTEXT)

    assert assets[0]["claim_strategy"]["usable_claims"] == [
        {
            "claim": "수변 경관을 중심으로 한 산책 경험을 제안할 수 있습니다.",
            "evidence_basis": "수변 경관을 중심으로 한 산책 경험을 제안할 수 있습니다.",
        }
    ]


def test_validate_marketing_assets_rejects_unsupported_string_usable_claim():
    products = validate_products(
        _product_payload(1),
        {"product_count": 1, "target_customer": "외국인"},
        DOCS,
        evidence_context=EVIDENCE_CONTEXT,
    )
    payload = _marketing_payload(sns_bodies=["대전 수변의 밤을 가볍게 걸어보는 외국인 여행 코스입니다. #대전여행"])
    strategy_pack = _marketing_strategy_pack()
    strategy_pack["claim_strategy"]["usable_claims"] = ["무료로 예약 즉시 확정되는 안전한 산책 상품입니다."]
    payload["marketing_assets"][0].update(strategy_pack)

    with pytest.raises(ValueError, match="unsupported operational claim"):
        validate_marketing_assets(payload, products, evidence_context=EVIDENCE_CONTEXT)


def test_validate_marketing_assets_rejects_internal_terms_in_strategy_pack():
    products = validate_products(
        _product_payload(1),
        {"product_count": 1, "target_customer": "외국인"},
        DOCS,
        evidence_context=EVIDENCE_CONTEXT,
    )
    payload = _marketing_payload(sns_bodies=["대전 수변의 밤을 가볍게 걸어보는 외국인 여행 코스입니다. #대전여행"])
    strategy_pack = _marketing_strategy_pack()
    strategy_pack["marketing_strategy"]["key_selling_points"][0]["point"] = "source_id 기준으로 선택한 수변 산책"
    payload["marketing_assets"][0].update(strategy_pack)

    with pytest.raises(ValueError, match="internal diagnostic terminology"):
        validate_marketing_assets(payload, products, evidence_context=EVIDENCE_CONTEXT)


def test_validate_marketing_assets_rejects_unsupported_usable_claim():
    products = validate_products(
        _product_payload(1),
        {"product_count": 1, "target_customer": "외국인"},
        DOCS,
        evidence_context=EVIDENCE_CONTEXT,
    )
    payload = _marketing_payload(sns_bodies=["대전 수변의 밤을 가볍게 걸어보는 외국인 여행 코스입니다. #대전여행"])
    strategy_pack = _marketing_strategy_pack()
    strategy_pack["claim_strategy"]["usable_claims"][0]["claim"] = "무료로 예약 즉시 확정되는 안전한 산책 상품입니다."
    payload["marketing_assets"][0].update(strategy_pack)

    with pytest.raises(ValueError, match="unsupported operational claim"):
        validate_marketing_assets(payload, products, evidence_context=EVIDENCE_CONTEXT)


def test_validate_marketing_assets_rejects_operational_only_faq():
    products = validate_products(
        _product_payload(1),
        {"product_count": 1, "target_customer": "외국인"},
        DOCS,
        evidence_context=EVIDENCE_CONTEXT,
    )
    payload = _marketing_payload(sns_bodies=["대전 수변의 밤을 가볍게 걸어보는 외국인 여행 코스입니다. #대전여행"])
    payload["marketing_assets"][0]["faq"] = [
        {"question": "가격이 확정됐나요?", "answer": "가격은 운영자가 확인해야 합니다."},
        {"question": "운영시간은 확정인가요?", "answer": "운영시간은 게시 전 확인이 필요합니다."},
    ]

    with pytest.raises(ValueError, match="buyer-facing value question"):
        validate_marketing_assets(payload, products, evidence_context=EVIDENCE_CONTEXT)


def test_validate_marketing_assets_rejects_internal_terms_in_user_copy():
    products = validate_products(
        _product_payload(1),
        {"product_count": 1, "target_customer": "외국인"},
        DOCS,
        evidence_context=EVIDENCE_CONTEXT,
    )
    payload = _marketing_payload(sns_bodies=["대전 수변 산책에서 밤의 분위기를 느껴보세요. #대전여행"])
    payload["marketing_assets"][0]["sales_copy"]["headline"] = "source_id 기준 대전 수변 산책"

    with pytest.raises(ValueError, match="internal diagnostic terminology"):
        validate_marketing_assets(payload, products, evidence_context=EVIDENCE_CONTEXT)


def test_marketing_agent_retries_when_sns_campaign_is_not_korean(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    get_settings.cache_clear()

    calls: list[dict] = []

    def fake_call_gemini_json(**kwargs):
        calls.append(kwargs)
        is_repair = kwargs["purpose"] == "marketing_generation_repair"
        return GeminiJsonResult(
            data=_marketing_payload(
                sns_bodies=[
                    "대전 수변 산책 상품을 근거 기반으로 검토해 보세요. #대전여행 #수변산책"
                ]
                if is_repair
                else ["体验大田夜间散步商品 #大田旅行"],
            ),
            model="gemini-test",
            prompt_tokens=100,
            completion_tokens=40,
            total_tokens=140,
            cost_usd=0.0,
            paid_tier_equivalent_cost_usd=0.0,
            latency_ms=1,
            raw_text="{}",
        )

    monkeypatch.setattr("app.agents.workflow.call_gemini_json", fake_call_gemini_json)

    with TestClient(app):
        pass

    products = validate_products(
        _product_payload(1),
        {"product_count": 1, "target_customer": "외국인"},
        DOCS,
        evidence_context=EVIDENCE_CONTEXT,
    )
    with SessionLocal() as db:
        run = models.WorkflowRun(
            template_id="default_product_planning",
            input={"message": "대전 외국인 관광 상품", "product_count": 1},
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        state = {
            "run_id": run.id,
            "product_ideas": products,
            "retrieved_documents": DOCS,
            "evidence_profile": EVIDENCE_CONTEXT.get("evidence_profile", {}),
            "productization_advice": EVIDENCE_CONTEXT.get("productization_advice", {}),
            "data_coverage": EVIDENCE_CONTEXT.get("data_coverage", {}),
            "unresolved_gaps": EVIDENCE_CONTEXT.get("unresolved_gaps", []),
            "source_confidence": EVIDENCE_CONTEXT.get("source_confidence", 0.7),
            "ui_highlights": EVIDENCE_CONTEXT.get("ui_highlights", []),
            "agent_execution": [],
        }
        next_state = marketing_agent(db, state)

    get_settings.cache_clear()

    assert [call["purpose"] for call in calls] == ["marketing_generation", "marketing_generation_repair"]
    assert "검증_실패_수정" in calls[1]["prompt"]
    assert next_state["marketing_assets"][0]["sns_campaign"]["posts"][0]["body"] == "대전 수변 산책 상품을 근거 기반으로 검토해 보세요. #대전여행 #수변산책"


def test_marketing_agent_retries_when_product_asset_is_missing(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    get_settings.cache_clear()

    calls: list[dict] = []

    def fake_call_gemini_json(**kwargs):
        calls.append(kwargs)
        product_ids = ["product_1", "product_2"] if kwargs["purpose"] == "marketing_generation_repair" else ["product_1"]
        return GeminiJsonResult(
            data=_marketing_payload_for_products(
                product_ids,
                sns_bodies=["대전 수변 산책 상품을 근거 기반으로 검토해 보세요. #대전여행 #수변산책"],
            ),
            model="gemini-test",
            prompt_tokens=100,
            completion_tokens=40,
            total_tokens=140,
            cost_usd=0.0,
            paid_tier_equivalent_cost_usd=0.0,
            latency_ms=1,
            raw_text="{}",
        )

    monkeypatch.setattr("app.agents.workflow.call_gemini_json", fake_call_gemini_json)

    with TestClient(app):
        pass

    products = validate_products(
        _product_payload(2),
        {"product_count": 2, "target_customer": "외국인"},
        DOCS,
        evidence_context=EVIDENCE_CONTEXT,
    )
    with SessionLocal() as db:
        run = models.WorkflowRun(
            template_id="default_product_planning",
            input={"message": "대전 외국인 관광 상품", "product_count": 2},
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        state = {
            "run_id": run.id,
            "product_ideas": products,
            "retrieved_documents": DOCS,
            "evidence_profile": EVIDENCE_CONTEXT.get("evidence_profile", {}),
            "productization_advice": EVIDENCE_CONTEXT.get("productization_advice", {}),
            "data_coverage": EVIDENCE_CONTEXT.get("data_coverage", {}),
            "unresolved_gaps": EVIDENCE_CONTEXT.get("unresolved_gaps", []),
            "source_confidence": EVIDENCE_CONTEXT.get("source_confidence", 0.7),
            "ui_highlights": EVIDENCE_CONTEXT.get("ui_highlights", []),
            "agent_execution": [],
        }
        next_state = marketing_agent(db, state)

    get_settings.cache_clear()

    assert [call["purpose"] for call in calls] == ["marketing_generation", "marketing_generation_repair"]
    generation_prompt = json.loads(calls[0]["prompt"])
    assert [product["id"] for product in generation_prompt["상품_목록"]] == ["product_1", "product_2"]
    assert "Missing marketing asset for product_2" in calls[1]["prompt"]
    assert "모든 product_id" in calls[1]["prompt"]
    assert [asset["product_id"] for asset in next_state["marketing_assets"]] == ["product_1", "product_2"]


def test_validate_qa_report_flags_invalid_source_id():
    products = [{"id": "product_1", "title": "대전 산책", "source_ids": ["missing_doc"]}]

    report = validate_qa_report(
        {"overall_status": "pass", "summary": "QA 검수 완료. 차단 수준의 이슈가 없습니다.", "issues": []},
        products,
        docs=DOCS,
        evidence_context=EVIDENCE_CONTEXT,
    )

    assert report["overall_status"] == "pass"
    assert report["issues"] == []
    assert report["internal_diagnostics"][0]["type"] == "internal_diagnostic"


def test_validate_qa_report_flags_unresolved_gap_claim_as_issue():
    products = [
        {
            "id": "product_1",
            "title": "대전 산책",
            "one_liner": "가격은 10,000원입니다.",
            "source_ids": ["doc_1"],
        }
    ]

    report = validate_qa_report(
        {"overall_status": "pass", "summary": "", "issues": []},
        products,
        docs=DOCS,
        evidence_context=EVIDENCE_CONTEXT,
    )

    assert report["overall_status"] == "needs_review"
    assert any(issue["type"] == "price_claim" for issue in report["issues"])
