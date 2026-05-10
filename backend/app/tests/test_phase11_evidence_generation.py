from app.agents.workflow import (
    _product_prompt,
    validate_marketing_assets,
    validate_products,
    validate_qa_report,
)


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
    assert any("source id" in item for item in products[0]["needs_review"])
    assert "가격, 무료 여부, 할인율 단정" in products[0]["claim_limits"]
    assert "요청 avoid 기준: 무리한 도보" in products[0]["claim_limits"]


def test_validate_products_caps_requested_count_at_five():
    payload = _product_payload(6)

    products = validate_products(
        payload,
        {"product_count": 10, "target_customer": "외국인"},
        DOCS,
        evidence_context=EVIDENCE_CONTEXT,
    )

    assert len(products) == 5


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
                "faq": [{"question": "가격이 확정됐나요?", "answer": "가격은 운영자가 확인해야 합니다."}],
                "sns_posts": ["대전 수변 산책 상품 초안"],
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


def test_validate_qa_report_flags_invalid_source_id():
    products = [{"id": "product_1", "title": "대전 산책", "source_ids": ["missing_doc"]}]

    report = validate_qa_report(
        {"overall_status": "pass", "summary": "QA 검수 완료. 차단 수준의 이슈가 없습니다.", "issues": []},
        products,
        docs=DOCS,
        evidence_context=EVIDENCE_CONTEXT,
    )

    assert report["overall_status"] == "needs_review"
    assert any(issue["type"] == "source_missing" for issue in report["issues"])
    assert "이슈" in report["summary"]


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
