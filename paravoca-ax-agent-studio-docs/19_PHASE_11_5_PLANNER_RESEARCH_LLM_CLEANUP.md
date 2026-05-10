# Phase 11.5 Gemini Planner/Research and LLM Call Cleanup

작성 기준일: 2026-05-10

## 목적

Phase 11.5는 Phase 11에서 강화한 evidence 기반 Product/Marketing/QA 흐름 앞단을 정리하는 단계입니다.

- `PlannerAgent`를 Gemini prompt + JSON schema 기반 정규화 Agent로 전환합니다.
- `ResearchAgent`를 `ResearchSynthesisAgent`로 전환해 EvidenceFusion 결과를 상품 생성용 research brief로 재구성합니다.
- `data_summary`처럼 실제 LLM 호출이 아닌 deterministic 실행 기록을 LLM Calls에서 분리합니다.
- `ApiCapabilityRouterAgent`와 future `BaselineSearchPlanner`/`TourAPIQueryPlanner` 역할을 명확히 구분합니다.

## PlannerAgent

`PlannerAgent`는 사용자 요청을 workflow가 사용할 실행 의도와 제약으로 정규화합니다.

출력 필드:

- `user_intent`
- `product_count`
- `target_customer`
- `preferred_themes`
- `avoid`
- `period`
- `output_language`
- `request_type`
- `product_generation_constraints`
- `evidence_requirements`

중요한 역할 경계:

- 지역 코드, `lDongRegnCd`, `lDongSignguCd`, `areaCode`는 Planner가 확정하지 않습니다.
- 지역 확정은 `GeoResolverAgent`가 담당합니다.
- 상품 개수는 최대 5개로 제한합니다.
- Baseline TourAPI 검색 query/API 전략은 현재 deterministic 수집 코드가 담당합니다.

Prompt 핵심 구성:

- 입력: 사용자 message, region hint, period, target customer, product count, preferences, avoid, output language
- 역할 경계: 지역 코드 확정 금지, 해외/지원 범위 판단은 preflight/GeoResolver 정책과 분리, API query plan 생성 금지
- 출력 규칙: `product_count` 1~5 제한, 명확한 선호/회피 조건만 추출, 상품 생성 제약과 evidence requirement를 한국어 문장으로 작성

예시 출력:

```json
{
  "user_intent": "대전 유성구에서 외국인 대상 야간 관광 상품을 기획합니다.",
  "product_count": 3,
  "target_customer": "외국인",
  "preferred_themes": ["야간 관광", "대중교통 접근성"],
  "avoid": ["혼잡한 장소"],
  "period": "",
  "output_language": "ko",
  "request_type": "tourism_product_generation",
  "product_generation_constraints": [
    "상품 개수는 최대 5개입니다.",
    "지역 코드는 GeoResolverAgent가 확정합니다.",
    "근거 없는 운영시간, 가격, 예약 가능 여부는 단정하지 않습니다."
  ],
  "evidence_requirements": [
    "각 상품은 최소 1개 이상의 실제 근거 문서와 연결되어야 합니다.",
    "부족한 정보는 needs_review 또는 claim_limits로 분리해야 합니다."
  ]
}
```

## ResearchSynthesisAgent

`ResearchSynthesisAgent`는 EvidenceFusion 직후 실행됩니다.

이 단계는 evidence를 짧게 요약해 버리는 단계가 아닙니다. ProductAgent가 바로 사용할 수 있도록 후보별 근거를 보존하면서 다음 구조로 재배열합니다.

- `research_brief`
- `candidate_evidence_cards`
- `usable_claims`
- `restricted_claims`
- `operational_unknowns`
- `unresolved_gaps`
- `product_generation_guidance`
- `qa_risk_notes`

반드시 보존해야 하는 정보:

- `candidate_evidence_cards[].usable_facts`
- `candidate_evidence_cards[].operational_unknowns`
- `candidate_evidence_cards[].restricted_claims`
- `candidate_evidence_cards[].evidence_document_ids`
- `data_coverage`
- `source_confidence`
- `unresolved_gaps`

서버 validation은 Gemini 응답이 후보별 card를 너무 짧게 반환해도 EvidenceFusion base card의 핵심 facts와 `evidence_document_ids`를 보존합니다.

Prompt 핵심 구성:

- 입력: normalized request, geo scope, retrieved document 요약, EvidenceFusion의 candidate evidence cards, gap summary, enrichment summary
- 보존 필드: `usable_facts`, `operational_unknowns`, `restricted_claims`, `evidence_document_ids`, `unresolved_gaps`, `data_coverage`, `source_confidence`
- 출력 규칙: raw TourAPI/RAG 전체를 그대로 복사하지 않되 상품화에 필요한 세부 facts는 삭제하지 않음, 근거 없는 운영 조건은 restricted/unknown으로 분리

예시 출력:

```json
{
  "research_brief": "대전 유성구의 야간 관광 상품은 산책, 경관, 접근성 중심으로 구성할 수 있습니다. 운영시간과 예약 가능 여부는 근거가 부족하므로 운영자 확인 항목으로 분리합니다.",
  "candidate_evidence_cards": [
    {
      "title": "갑천 산책로",
      "usable_facts": [
        "대전 유성구에 위치한 수변 산책 후보입니다.",
        "야간 경관형 코스의 일부로 활용할 수 있습니다."
      ],
      "experience_hooks": ["가벼운 야간 산책", "도심 수변 경관"],
      "recommended_product_angles": ["외국인 대상 저강도 야간 산책 코스"],
      "operational_unknowns": ["야간 이용 가능 시간 확인 필요", "안전 안내 인력 필요 여부 확인 필요"],
      "restricted_claims": ["정확한 운영시간 단정 금지", "예약 가능 여부 단정 금지"],
      "evidence_document_ids": ["doc_123"]
    }
  ],
  "usable_claims": ["근거 문서에 있는 장소명, 주소, 개요는 사용할 수 있습니다."],
  "restricted_claims": ["가격, 운영시간, 예약 가능 여부는 단정하지 않습니다."],
  "operational_unknowns": ["야간 운영 가능 여부", "외국어 안내 가능 여부"],
  "unresolved_gaps": [
    {
      "gap_type": "missing_operating_hours",
      "label": "운영시간 부족",
      "severity": "medium",
      "reason": "수집된 근거에서 야간 운영 가능 시간이 확인되지 않았습니다."
    }
  ],
  "product_generation_guidance": ["각 상품은 candidate evidence card의 evidence_document_ids와 연결하세요."],
  "qa_risk_notes": ["근거 없는 가격, 예약, 운영시간, 안전, 외국어 지원 claim을 만들지 마세요."]
}
```

## LLM Calls 정리

`data_summary`는 LLM 호출이 아니라 `BaselineDataAgent`의 deterministic 수집/색인/검색 결과 기록이었습니다.

Phase 11.5부터 새 run에서는 `data_summary`를 `llm_calls`에 저장하지 않습니다.

- TourAPI 수집, Chroma 색인, vector search: `agent_steps`와 `tool_calls`에서 확인
- 실제 Gemini 호출: `llm_calls`에서 확인
- 과거 run의 legacy/offline Planner/Research agent call: LLM Calls tab에서 계속 표시
- Developer UI의 LLM Calls tab: `data_summary` deterministic row만 숨기고, Gemini 호출과 agent call 기록은 표시

과거 run에 남아 있는 legacy `rule_based/data_summary` row는 migration하지 않고 UI에서만 숨깁니다. 과거 run의 `planner`, `research` agent call은 계속 표시합니다.

## ApiCapabilityRouterAgent와 DataQueryPlanner 구분

현재 `ApiCapabilityRouterAgent`의 역할은 baseline 데이터 수집 이후에 생성된 gap report를 보고 어떤 API family/planner lane으로 보낼지 결정하는 것입니다.

즉, 다음 질문을 다룹니다.

- “이미 수집한 후보에서 부족한 정보가 무엇인가?”
- “그 gap은 TourAPI detail, visual, route/signal, theme 중 어느 planner lane으로 가야 하는가?”

반면 future `BaselineSearchPlanner` 또는 `TourAPIQueryPlanner`가 생긴다면 baseline 수집 전에 다음 질문을 다룹니다.

- “처음 TourAPI 검색을 keyword 중심으로 할 것인가?”
- “행사, 관광지, 숙박, 음식점, 레포츠 중 어떤 content type을 우선 볼 것인가?”
- “지역/테마/기간에 맞춰 어떤 query 조합을 만들 것인가?”

Phase 11.5에서는 새 DataQueryPlanner를 만들지 않았습니다. 이 역할은 Phase 12 이후 실제 추가 API 연결이 늘어난 뒤 별도 phase로 분리하는 것이 맞습니다.

## 구현 검증 기준

- PlannerAgent는 `LLM_ENABLED=true`에서 Gemini `purpose=planner`로 호출됩니다.
- ResearchSynthesisAgent는 `LLM_ENABLED=true`에서 Gemini `purpose=research_synthesis`로 호출됩니다.
- `data_summary`는 새 workflow run의 `llm_calls`에 저장되지 않습니다.
- ProductAgent는 Phase 11에서 추가한 evidence 기반 입력 구조를 유지합니다.
- 추가 KTO API 실제 연결은 Phase 12.1/12.2/12.3 범위로 남깁니다.
