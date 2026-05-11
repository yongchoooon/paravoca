# Agent와 Workflow 상세 명세

## 설계 원칙

이 프로젝트의 Agent는 전체 업무 경로를 workflow 안에서 수행합니다. 각 단계 내부에서 필요한 도구 선택과 분석은 Agent가 맡고, 실행 순서와 상태 전이는 workflow가 통제합니다.

기본 workflow:

```text
User Input
  → Planner Agent
  → GeoResolver Agent
  → BaselineDataAgent
  → DataGapProfilerAgent
  → ApiCapabilityRouterAgent
  → TourApiDetailPlannerAgent
  → VisualDataPlannerAgent
  → RouteSignalPlannerAgent
  → ThemeDataPlannerAgent
  → EnrichmentExecutor
  → EvidenceFusionAgent
  → Research Agent
  → Product Agent
  → Marketing Agent
  → QA/Compliance Agent
  → Human Approval Node
  → Save/Export Node
```

Run 생성 전에는 `PreflightValidationAgent`가 먼저 실행됩니다. 이 검증은 LangGraph run 내부 step으로 기록하지 않고, run 생성 API에서 동기적으로 처리합니다.

- 자연어 요청이나 입력 필드가 상품 21개 이상 생성을 요구하면 run을 만들지 않고 생성 modal에서 최대 20개 안내를 표시합니다.
- 검증을 통과한 요청도 실제 사용 가능한 근거 데이터가 요청 수보다 적으면, ProductAgent가 가능한 개수까지만 생성하고 부족 사유를 상품별 확인 항목에 남깁니다.
- 관광 상품 기획과 무관한 요청은 run을 만들지 않고 지원 범위 안내를 표시합니다.
- 검증을 통과한 요청만 `workflow_created` 이후 LangGraph workflow로 들어갑니다.

Phase 10 기준으로 GeoResolver 단계에는 두 개의 조기 종료 경로가 있습니다.

- 지역 후보 안내: `중구`처럼 후보가 여러 개인 경우 run status는 `failed`로 저장하고 후보를 UI에 보여주며 Data Agent로 넘어가지 않습니다.
- `unsupported`: 해외 목적지처럼 PARAVOCA의 현재 국내 관광 데이터 지원 범위 밖인 경우 안내 메시지를 반환하고 Data Agent로 넘어가지 않습니다.

후속 Poster Studio workflow:

```text
Approved or Reviewable Run
  → Poster Context Builder
  → Poster Prompt Agent
  → Human Poster Option Review
  → Poster Image Agent
  → Poster QA/Review
  → Poster Asset Save
```

## LangGraph 상태

### GraphState

```python
class GraphState(TypedDict):
    run_id: str
    user_request: dict
    normalized_request: dict
    geo_scope: dict
    plan: list[dict]
    source_items: list[dict]
    retrieved_documents: list[dict]
    data_gap_report: dict
    enrichment_plan: dict
    enrichment_summary: dict
    evidence_profile: dict
    productization_advice: dict
    data_coverage: dict
    unresolved_gaps: list[dict]
    source_confidence: float
    research_summary: dict
    product_ideas: list[dict]
    marketing_assets: list[dict]
    qa_report: dict
    approval: dict | None
    final_report: dict | None
    errors: list[dict]
    cost_summary: dict
```

### 상태 업데이트 규칙

- 각 node는 자신이 담당하는 key만 업데이트합니다.
- 모든 node는 `run_id`를 사용해 DB에 step log를 남깁니다.
- 실패 시 `errors`, `agent_steps.error`, workflow run error에 원인을 남기고 해당 run을 실패 상태로 종료합니다.

## Planner Agent

### 역할

사용자 요청을 정규화하고 실행 계획을 만듭니다.

### 입력

```json
{
  "message": "이번 달 부산에서 외국인 대상 액티비티 상품을 5개 기획해줘",
  "current_date": "2026-05-05",
  "timezone": "Asia/Seoul"
}
```

### 출력

```json
{
  "normalized_request": {
    "message": "이번 달 부산에서 외국인 대상 액티비티 상품을 5개 기획해줘",
    "start_date": "2026-05-01",
    "end_date": "2026-05-31",
    "target_customer": "foreign_travelers",
    "product_count": 5,
    "preferred_themes": ["activity", "night_view", "festival"],
    "output_language": "ko"
  },
  "tasks": [
    {
      "id": "task_1",
      "type": "geo_resolution",
      "description": "요청 문장에서 지역 범위 해석",
      "required_agent": "GeoResolverAgent"
    }
  ],
  "risk_notes": [
    "이번 달은 2026-05-01부터 2026-05-31까지로 해석합니다."
  ]
}
```

### 도구

- region code resolver
- date parser
- model policy checker

### 프롬프트 규칙

- 상대 날짜는 반드시 기준일로 절대 날짜 변환합니다.
- 상품 수가 없으면 기본 3개로 설정합니다.
- 지역 해석은 GeoResolverAgent가 담당합니다.
- 지역이 불명확하면 억지로 추정하지 않고 `needs_clarification`으로 멈춥니다.
- 가격, 예약 가능 여부, 실시간 재고는 알 수 없다고 표시합니다.

## GeoResolver Agent

### 역할

자연어 요청에서 지역 의도를 추출하고 TourAPI v4.4 검색에 사용할 `lDongRegnCd`/`lDongSignguCd` 기반 `geo_scope`를 만듭니다.

### 입력

```json
{
  "message": "부산 부산진구 전포동 일대 카페 투어 상품 3개 기획해줘",
  "period": "2026-05",
  "preferences": ["카페 투어"]
}
```

### 처리 규칙

- 기준 catalog는 `ldongCode2?lDongListYn=Y` 전체 paging sync 결과입니다.
- Phase 12.0부터 Gemini GeoResolverAgent는 catalog 후보를 prompt로 받아 `resolved_locations`를 직접 선택합니다.
- Python resolver는 Gemini가 선택한 code가 실제 catalog에 있는지, confidence가 충분한지 검증합니다.
- resolver는 특정 테스트 지명을 코드에 하드코딩해 강제 매핑하지 않습니다.
- Python fallback matcher는 명확한 시도/시군구 exact match, normalized match, fuzzy candidate만 처리합니다.
- 상위 지역이 확정된 상태에서만 `전포동`, `대청도` 같은 더 좁은 지명을 keyword로 유지합니다.
- 좁은 지명 keyword가 있으면 BaselineDataAgent는 상위 시군구 code로 수집한 뒤 item/document text에 keyword가 있는 근거만 남깁니다.
- `중구`처럼 여러 시도에 같은 시군구명이 있으면 `needs_clarification=true`로 처리합니다.
- 해외 목적지는 `unsupported`로 처리하고 PARAVOCA가 현재 국내 관광 데이터만 지원한다는 안내를 반환합니다.
- 사용자가 `전국`, `국내 전체`처럼 명시한 경우에만 전국 검색을 허용합니다.

### 출력

```json
{
  "geo_scope": {
    "mode": "single_area",
    "status": "resolved",
    "locations": [
      {
        "name": "부산광역시 부산진구 전포동 일대",
        "role": "primary",
        "ldong_regn_cd": "26",
        "ldong_signgu_cd": "230",
        "keywords": ["전포동"],
        "confidence": 0.98
      }
    ],
    "needs_clarification": false
  }
}
```

## Data Agent

### 역할

Planner가 만든 plan에 따라 외부/내부 데이터를 조회합니다.

### 입력

```json
{
  "normalized_request": {
    "start_date": "2026-05-01",
    "end_date": "2026-05-31",
    "target_customer": "foreign_travelers",
    "preferred_themes": ["night_view", "festival"]
  },
  "geo_scope": {
    "mode": "single_area",
    "locations": [
      {"ldong_regn_cd": "26", "ldong_signgu_cd": "230", "keywords": ["전포동"]}
    ]
  }
}
```

### 도구

- `tourapi_area_code`
- `tourapi_ldong_code`
- `tourapi_lcls_system_code`
- `tourapi_area_based_list`
- `tourapi_search_keyword`
- `tourapi_search_festival`
- `tourapi_search_stay`
- `tourapi_detail_common`
- `tourapi_detail_intro`
- `tourapi_detail_info`
- `tourapi_detail_image`
- `tourapi_category_code`
- `tourapi_location_based_list`
- `tourism_demand_resource`
- `local_product_search`
- `vector_search`

현재 Phase 10 구현:

- `BaselineDataAgent`는 GeoResolver가 만든 `geo_scope`를 기준으로 TourAPI v4.4 `lDongRegnCd`/`lDongSignguCd` 파라미터를 전달하고 기본 후보만 수집합니다.
- `DataGapProfilerAgent`는 기본 후보의 상세정보, 이미지, 운영시간, 요금, 예약정보, 연관 장소, 동선, 테마 특화 데이터 공백을 구조화합니다.
- `ApiCapabilityRouterAgent`는 gap을 `backend/app/tools/kto_capabilities.py` capability catalog 기준의 API family planner lane으로 분배합니다.
- `TourApiDetailPlannerAgent`, `VisualDataPlannerAgent`, `RouteSignalPlannerAgent`, `ThemeDataPlannerAgent`는 각자 배정된 gap과 자기 source family subset만 보고 짧은 call/skip 계획을 만듭니다.
- `EnrichmentExecutor`는 Agent 판단자가 아니라 코드 실행 action입니다. 계획된 KorService2 상세 보강만 실행합니다. `detailCommon2`, `detailIntro2`, `detailInfo2`, `detailImage2`는 구현되어 있고, 아직 provider가 없는 KTO source family는 skipped/future로 기록합니다.
- 보강된 상세/반복/이미지 metadata는 `tourism_entities`, `tourism_visual_assets`, `source_documents`, Chroma index, `enrichment_runs`, `enrichment_tool_calls`에 반영됩니다.
- `EvidenceFusionAgent`는 같은 content_id/source item 기준으로 근거를 묶어 `evidence_profile`, 후보별 `candidate_evidence_cards`가 포함된 `productization_advice`, `data_coverage`, `unresolved_gaps`, `source_confidence`를 생성합니다.
- `source_documents`와 Chroma metadata에는 `ldong_regn_cd`, `ldong_signgu_cd`, `lcls_systm_1/2/3`가 저장됩니다.
- 상세 이미지 후보는 `tourism_visual_assets.usage_status=candidate`로 저장합니다.
- `categoryCode2`, `locationBasedList2`는 provider method와 capability에는 준비되어 있으나, 아직 route/candidate ranking workflow에는 연결하지 않았습니다.

P2 이후 추가 후보:

- `web_search`
- `google_search_grounding`
- `user_detail_request`

웹 검색/검색 grounding은 MVP 필수 경로가 아닙니다. TourAPI와 내부 RAG만으로 상품화/검증 근거가 부족할 때 보강 도구로 사용합니다. 특히 운영 시간, 가격/포함사항, 예약 조건, 집결지, 최신 행사 변경 공지처럼 TourAPI 응답에 없거나 오래될 수 있는 정보가 대상입니다.

### 출력

```json
{
  "source_items": [
    {
      "id": "tourapi:content:12345",
      "title": "광안리해수욕장",
      "content_type": "attraction",
      "source": "tourapi",
      "metadata": {}
    }
  ],
  "retrieved_documents": [
    {
      "doc_id": "doc_123",
      "title": "광안리해수욕장",
      "snippet": "...",
      "score": 0.82,
      "source_id": "tourapi:content:12345"
    }
  ],
  "data_gaps": [
    "일부 행사 종료일이 누락되어 공식 페이지 확인이 필요합니다."
  ],
  "web_evidence_documents": [
    {
      "doc_id": "doc:web:...",
      "title": "공식 공지 또는 상세 안내",
      "url": "https://example.com/notice",
      "snippet": "...",
      "source_type": "official_site",
      "retrieved_at": "2026-05-06T00:00:00+09:00"
    }
  ],
  "user_detail_requests": [
    {
      "field": "meeting_point",
      "reason": "TourAPI와 웹 근거에서 확정 집결지를 찾지 못했습니다.",
      "required_for": ["product_publish", "qa_pass"]
    }
  ]
}
```

`web_evidence_documents`와 `user_detail_requests`는 P2 이후 필드입니다. MVP에서는 `data_gaps`에 운영자 확인 필요 사항을 남기고 workflow를 계속 진행합니다.

### 실패 처리

- TourAPI 실패: failed tool call과 failed workflow run으로 기록
- 수요 API 실패: `demand_data_unavailable` flag
- 이미지 조회 실패: 상품 기획은 계속 진행
- 웹 검색 실패: P2 이후에는 `web_search_unavailable` flag를 남기고 TourAPI/RAG 근거만으로 진행합니다.
- 사용자 추가 정보가 필요한 경우: 상품 생성은 draft로 진행하되 QA에서 `needs_review`를 표시합니다.

### 웹 근거 보강 정책

Data Agent는 다음 조건에서 웹 보강 검색 후보를 만듭니다.

- TourAPI overview가 짧거나 운영 정보가 비어 있음
- 행사 날짜, 운영 시간, 휴무, 예약 조건이 상품 구성에 중요함
- source evidence가 하나뿐이거나 공식 출처가 약함
- QA가 가격/예약/안전/운영 시간 단정 표현을 검출함

웹 보강 검색 실행은 비용과 latency가 있으므로 기본 비활성화합니다. `web_search_enabled=true`, 운영자 수동 요청, 또는 향후 budget guard가 허용한 경우에만 실행합니다.

검색 결과 사용 규칙:

- 공식 사이트/행사 주최 측 공지를 우선합니다.
- 검색 snippet만으로 단정하지 않고 URL과 조회 시각을 함께 저장합니다.
- 비공식 블로그, 커뮤니티, 리뷰성 자료는 트렌드 참고로만 쓰고 확정 근거로 쓰지 않습니다.
- Product/Marketing Agent는 웹 근거가 있어도 가격, 예약 가능 여부, 운영 시간은 최종 확인 문구를 유지합니다.

## Research Agent

### 역할

데이터를 해석해 상품 기획에 필요한 근거를 만듭니다.

### 분석 항목

- 지역 특성
- 계절성
- 행사/축제 기간 매칭
- 타깃 고객 적합성
- 관광지 간 조합 가능성
- 이동 동선
- 운영 리스크
- 데이터 부족 사항

### 출력

```json
{
  "region_insights": [
    {
      "claim": "부산은 해변, 야경, 시장 먹거리 조합이 외국인 대상 액티비티로 구성하기 좋습니다.",
      "evidence_source_ids": ["tourapi:content:12345", "tourapi:content:23456"],
      "confidence": 0.78
    }
  ],
  "seasonal_insights": [],
  "event_opportunities": [],
  "recommended_themes": [
    {
      "theme": "night_food_tour",
      "reason": "...",
      "evidence_source_ids": []
    }
  ],
  "constraints": [
    "정확한 행사 운영 시간은 공식 페이지 확인 필요"
  ]
}
```

### 프롬프트 규칙

- 출처가 없는 주장은 `assumption`으로 분리합니다.
- source evidence가 약하면 confidence를 낮춥니다.
- 수요 데이터는 보조 지표로만 해석합니다.

## Product Agent

### 역할

Research summary와 source items를 바탕으로 여행 액티비티 상품 아이디어를 생성합니다.

### 상품 생성 규칙

각 상품은 다음을 포함해야 합니다.

- `title`
- `one_liner`
- `target_customer`
- `core_value`
- `itinerary`
- `included_places`
- `operation_notes`
- `estimated_duration`
- `source_ids`
- `assumptions`
- `not_to_claim`

### 출력 schema

```json
{
  "products": [
    {
      "title": "부산 야경 + 전통시장 푸드투어",
      "one_liner": "부산의 밤 풍경과 로컬 먹거리를 함께 경험하는 외국인 대상 도보형 액티비티",
      "target_customer": "foreign_travelers",
      "core_value": [
        "야경",
        "로컬 음식",
        "짧은 동선"
      ],
      "itinerary": [
        {
          "order": 1,
          "name": "광안리 야경 감상",
          "source_id": "tourapi:content:12345",
          "notes": "운영 시간과 집결지는 운영자가 확정"
        }
      ],
      "estimated_duration": "3~4 hours",
      "operation_difficulty": "medium",
      "source_ids": ["tourapi:content:12345"],
      "assumptions": [
        "시장 운영 시간은 계절과 요일에 따라 달라질 수 있음"
      ],
      "not_to_claim": [
        "가격 확정",
        "모든 점포 운영 보장"
      ]
    }
  ]
}
```

### 금지 표현

- "100% 만족"
- "무조건"
- "최저가 보장"
- "항상 운영"
- "예약 즉시 확정" unless source confirms
- "안전 완전 보장"

## Marketing Agent

### 역할

상품 아이디어를 실제 상세페이지 초안으로 확장합니다.

### 출력 항목

상품별:

- 상세페이지 headline
- subheadline
- overview
- section copy 3~5개
- included/not included
- meeting point note
- FAQ 5개
- SNS post 3개
- search keywords 10개
- SEO title/meta description

### FAQ 규칙

FAQ는 운영자가 실제로 확인해야 할 질문을 포함합니다.

예:

- 우천 시 진행하나요?
- 집결지는 어디인가요?
- 외국어 가이드가 포함되나요?
- 식사 비용이 포함되나요?
- 행사 일정이 바뀌면 어떻게 되나요?

답변은 확정 정보와 확인 필요 정보를 구분합니다.

### 출력 예

```json
{
  "product_id": "product_1",
  "sales_copy": {
    "headline": "부산의 밤을 로컬처럼 걷고 맛보는 야경 푸드투어",
    "subheadline": "광안리 야경과 시장 먹거리를 한 번에 경험하는 외국인 대상 액티비티",
    "sections": [
      {
        "title": "왜 이 코스인가요",
        "body": "..."
      }
    ],
    "disclaimer": "세부 일정, 포함사항, 가격은 운영자가 최종 확정해야 합니다."
  },
  "faq": [
    {
      "question": "우천 시에도 진행하나요?",
      "answer": "기상 상황과 현장 안전 기준에 따라 변경될 수 있어 운영자 확인이 필요합니다."
    }
  ],
  "sns_posts": [],
  "search_keywords": []
}
```

## QA/Compliance Agent

### 역할

생성물이 출처에 근거하는지, 운영 리스크가 있는지 검수합니다.

### 검수 방식

1. Rule-based check
2. Source consistency check
3. LLM judge check
4. JSON schema check
5. Approval gate check

QA Agent는 create run 또는 revision modal에서 전달된 `qa_settings`를 함께 사용합니다. 기본값은 최초 run 생성 시 입력한 `region`, `period`, `target_customer`, `product_count`, `preferences`, `avoid`, `output_language`입니다. 사용자는 AI 수정이나 QA 재검수 실행 전에 이 설정을 확인하고 수정할 수 있어야 합니다.

### Rule-based checks

```python
PROHIBITED_PATTERNS = [
    "100% 만족",
    "무조건",
    "항상 운영",
    "최저가",
    "완전 보장",
    "예약 즉시 확정",
]
```

### Source consistency checks

- 행사 날짜가 source event 기간과 일치하는지 확인
- source_ids가 존재하는지 확인
- source가 없는 관광지명이 생성됐는지 확인
- 이미지 사용 주의 문구가 필요한지 확인

### QA false positive 방지

아래 문구는 안전한 완화 문구로 봅니다.

- `확인 필요`
- `사전에 확인`
- `현장 상황에 따라`
- `변동될 수 있습니다`
- `운영자가 최종 확정해야 합니다`
- `문의 필요`

가격/일정/예약/안전 위반은 다음처럼 확정 또는 보장으로 읽히는 경우에만 지적합니다.

- `항상 운영`
- `예약 즉시 확정`
- `반드시 이용 가능`
- `가격은 N원입니다`
- `100% 안전`
- `최저가 보장`

QA 메시지와 suggested fix에는 `disclaimer`, `not_to_claim`, `sales_copy` 같은 내부 필드명을 그대로 노출하지 않습니다. 사용자에게는 `유의 문구`, `운영 주의사항`, `상세 설명`, `FAQ 답변`처럼 이해 가능한 이름으로 표시합니다.

### 출력

```json
{
  "overall_status": "needs_review",
  "summary": "5개 상품 중 2개는 날짜 확인 필요, 1개는 가격 단정 표현 수정 필요",
  "issues": [
    {
      "product_index": 1,
      "severity": "high",
      "type": "unsupported_claim",
      "message": "출처에 없는 '매일 운영' 표현이 포함되어 있습니다.",
      "field_path": "sales_copy.sections[2].body",
      "suggested_fix": "운영 일정은 운영자가 최종 확인해야 한다고 수정"
    }
  ],
  "pass_count": 3,
  "needs_review_count": 2,
  "fail_count": 0
}
```

## Human Approval Node

### 역할

자동 생성 결과를 검토 담당자가 승인하기 전 workflow를 멈춥니다.

### 승인 조건

- QA high severity issue가 없거나 검토 담당자가 override reason을 입력해야 합니다.
- result preview를 확인해야 합니다.
- 승인 코멘트를 남길 수 있습니다.

### 승인 API

```http
POST /api/workflow-runs/{run_id}/approve
POST /api/workflow-runs/{run_id}/reject
POST /api/workflow-runs/{run_id}/request-changes
```

```json
{
  "reviewer": "operator",
  "comment": "행사 날짜는 별도 확인 예정. 나머지 초안 승인.",
  "high_risk_override": false,
  "requested_changes": []
}
```

## Save/Export Node

### 역할

승인된 결과만 저장 또는 외부 전송합니다.

MVP:

- DB 저장
- Markdown report 파일 생성
- JSON export

P1:

- Google Sheets 저장
- Notion page 생성
- Slack message draft

### 승인 gate

외부 전송 tool metadata:

```json
{
  "tool_name": "google_sheet_save",
  "requires_approval": true
}
```

`approval.status != approved`이면 실행하지 않습니다.

## Agent별 모델 추천

| Agent | 기본 모델 계층 | 이유 |
|---|---|---|
| Planner | cheap/standard | 구조화와 날짜 정규화 중심 |
| Data | cheap | 도구 호출/정규화 중심 |
| Research | standard | 근거 종합 필요 |
| Product | standard | 기획 품질 중요 |
| Marketing | standard | 카피 품질 중요 |
| QA | cheap + standard | rule 먼저, 의심 케이스만 judge |
| Poster Prompt | standard | 상품 정보와 디자인 지시를 구조화 |
| Poster Image | OpenAI Image | 포스터 이미지 생성 |
| Poster QA | cheap/standard | 이미지 문구와 운영 리스크 검수 |
| Eval judge | cheap/standard batch | 비용 통제 필요 |

## 후속 Poster Studio Agent

Poster Studio는 workflow run 결과를 홍보 이미지 제작으로 확장하는 후속 기능입니다. 기존 Product/Marketing/QA 결과를 기반으로 포스터 문구와 이미지 생성 프롬프트를 만들고, 사용자가 최종 옵션을 확인한 뒤 이미지를 생성합니다.

### Poster Context Builder

역할:

- 선택된 `run_id`, `product_id`, revision 결과를 읽습니다.
- `products`, `marketing_assets`, `qa_report`, `retrieved_documents`, `approval_history`에서 포스터에 필요한 값만 추립니다.
- 운영 리스크가 있는 값은 prompt constraint로 분리합니다.

출력:

```json
{
  "poster_context": {
    "product_title": "부산 야경 + 전통시장 푸드투어",
    "one_liner": "외국인 자유여행객을 위한 야간 로컬 코스",
    "target_customer": "외국인",
    "region": "부산",
    "core_values": ["야경", "로컬 음식", "짧은 동선"],
    "itinerary_highlights": ["광안리 야경", "전통시장 먹거리", "야간 사진 포인트"],
    "safe_claims": ["운영 조건 확인 후 예약 오픈"],
    "prompt_constraints": [
      "가격을 확정하지 말 것",
      "운영 시간과 예약 가능 여부를 단정하지 말 것",
      "과장 표현을 쓰지 말 것"
    ]
  }
}
```

### Poster Prompt Agent

역할:

- 포스터 목적, 비율, 스타일, 문구 밀도에 맞는 prompt draft를 만듭니다.
- 상품 정보에서 포스터에 넣을 문구 후보를 추천합니다.
- 사용자가 삭제/수정할 수 있도록 모든 문구를 구조화해서 반환합니다.

입력:

```json
{
  "poster_context": {},
  "options": {
    "purpose": "sns_feed",
    "aspect_ratio": "4:5",
    "style_direction": "프리미엄 야간 관광",
    "copy_density": "balanced",
    "include_fields": ["상품명", "지역", "핵심 코스", "CTA"],
    "visual_source_mode": "ai_generated",
    "custom_instruction": "밤 분위기는 세련되게, 텍스트는 적게"
  }
}
```

출력:

```json
{
  "copy_candidates": {
    "headlines": ["부산의 밤을 걷는 야경 푸드투어"],
    "subheadlines": ["외국인 자유여행객을 위한 로컬 야간 코스"],
    "ctas": ["운영 조건 확인 후 예약 오픈"]
  },
  "recommended_content": [
    {"key": "headline", "value": "부산의 밤을 걷는 야경 푸드투어", "selected": true},
    {"key": "region", "value": "부산", "selected": true},
    {"key": "price", "value": "", "selected": false}
  ],
  "visual_direction": {
    "style": "프리미엄 여행 포스터",
    "palette": ["navy", "warm white", "neon accent"],
    "composition": "상단 큰 헤드라인, 중앙 야경 이미지, 하단 CTA"
  },
  "prompt_constraints": [
    "포스터 안 텍스트는 사용자가 선택한 문구만 사용",
    "가격과 예약 가능 여부를 쓰지 않음",
    "날짜는 확인된 값만 사용"
  ],
  "prompt_draft": "..."
}
```

### Human Poster Option Review

사용자가 확인하고 수정하는 항목:

- headline/subheadline/CTA 후보
- 포함할 상품 정보
- 삭제할 정보
- 포스터 목적
- aspect ratio
- style direction
- copy density
- custom instruction

완료 조건:

- 사용자가 최종 문구와 옵션을 확인해야 Poster Image Agent를 실행할 수 있습니다.
- 선택되지 않은 정보는 최종 prompt에 포함하지 않습니다.
- QA issue나 `not_to_claim`에 걸린 표현은 기본 선택에서 제외합니다.

### Poster Image Agent

역할:

- 확정된 prompt와 옵션으로 OpenAI Image API를 호출합니다.
- 기본 후보 모델은 `gpt-image-2`입니다.
- 생성 이미지, revised/final prompt, latency, 예상 비용, provider response summary를 저장합니다.

저장 필드:

```json
{
  "poster_id": "poster_001",
  "run_id": "run_001",
  "product_id": "product_1",
  "provider": "openai",
  "model": "gpt-image-2",
  "prompt": "...",
  "options": {
    "size": "auto",
    "quality": "medium",
    "format": "png"
  },
  "image_path": "poster_assets/run_001/product_1/poster_001.png",
  "latency_ms": 45000,
  "estimated_cost_usd": 0.0,
  "status": "needs_review"
}
```

### Poster QA/Review

검수 항목:

- 이미지 안 텍스트가 사용자가 선택한 문구와 일치하는지
- 날짜, 가격, 예약 가능 여부 단정 표현이 들어갔는지
- 과장 표현이나 안전 보장 표현이 들어갔는지
- TourAPI 이미지 참고/재사용 시 라이선스 확인 메모가 있는지
- 브랜드명, 상표, 인물 이미지 리스크가 있는지

주의:

- 이미지 모델은 텍스트 배치와 정확도에 한계가 있으므로 포스터 안 문구는 사람이 최종 확인합니다.
- 생성 이미지는 기본 `needs_review` 상태로 저장합니다.
- 외부 게시나 다운로드 가능한 최종 asset 전환은 사람 승인 뒤에 허용합니다.

## 프롬프트 버전 관리

각 prompt는 파일로 분리합니다.

```text
backend/app/agents/prompts/
  planner_v1.md
  research_v1.md
  product_v1.md
  marketing_v1.md
  qa_v1.md
  poster_prompt_v1.md
  poster_qa_v1.md
```

prompt metadata:

```yaml
id: product_v1
owner: product_agent
created_at: 2026-05-05
expected_output_schema: ProductIdeas
```

DB에는 workflow run마다 prompt version을 저장합니다.

## Revision Workflow 정책

사용자가 QA 결과를 보고 수정 요청하면 기존 run을 덮어쓰지 않고 revision run을 새로 만듭니다. 원본 run은 감사 추적용으로 유지하고, 모든 revision run은 최상위 원본 run의 `parent_run_id` 아래에 연결합니다. revision에서 다시 revision을 만들어도 새 run은 중간 revision 대신 최상위 원본 run을 parent로 가지며 `revision_number`만 증가합니다.

수정 방식:

- `manual_save`: 운영자가 수정한 products/marketing_assets를 새 revision run에 저장하고 QA는 다시 실행하지 않습니다.
- `manual_edit`: 운영자가 products, marketing_assets, FAQ, SNS 문구를 직접 수정하고 QA/Compliance Agent만 다시 실행합니다.
- `llm_partial_rewrite`: 선택한 QA issue와 requested changes를 바탕으로 필요한 필드만 AI가 patch합니다. Product/Marketing 전체 재생성은 하지 않습니다.
- `qa_only`: 기존 결과 또는 직접 수정한 결과를 유지하고 QA/Compliance Agent만 다시 실행합니다.
- `data_refresh_downstream`: 데이터가 오래되었거나 source evidence가 부족할 때 Data/RAG부터 downstream을 다시 실행합니다. 현재 MVP에서는 제외합니다.

Revision run 입력:

```json
{
  "revision_mode": "llm_partial_rewrite",
  "requested_changes": ["가격 단정 표현 제거", "집결지 안내 보강"],
  "qa_issues": [
    {
      "product_id": "product_1",
      "severity": "medium",
      "type": "general",
      "message": "상세 설명에 과장 표현이 있습니다.",
      "suggested_fix": "완화된 표현으로 수정하세요."
    }
  ],
  "qa_settings": {
    "region": "부산",
    "period": "2026-05",
    "target_customer": "외국인",
    "product_count": 3,
    "preferences": ["야간 관광", "축제"],
    "avoid": ["가격 단정 표현", "과장 표현"],
    "output_language": "ko"
  },
  "products": null,
  "marketing_assets": null
}
```

Revision run 완료 조건:

- 새 run은 `pending -> running -> awaiting_approval` 흐름을 따릅니다.
- 최상위 원본 run, source run, source evidence, retrieved_documents, approval history를 revision context로 사용합니다.
- revision run의 `parent_run_id`는 항상 최상위 원본 run id입니다.
- revision run의 `revision_number`는 같은 최상위 원본 run 아래에서 증가합니다.
- `qa_only`는 Product/Marketing 재생성 없이 QA/Compliance Agent만 다시 실행합니다.
- `llm_partial_rewrite`는 RevisionPatchAgent가 선택한 QA issue와 requested changes에 필요한 필드만 patch하고, 나머지 값은 그대로 유지합니다.
- 사용자는 원본 run과 revision history를 이동하면서 결과와 QA report를 확인할 수 있어야 합니다.

## Agent 평가 포인트

Planner:

- 날짜 정규화 정확도
- 필요한 tool plan 포함 여부

Data:

- tool call accuracy
- API 실패 복구율

Research:

- source evidence coverage
- unsupported assumption rate
- TourAPI 근거와 웹 근거의 충돌/보강 관계 분리

Product:

- 상품 수 충족
- source groundedness
- target fit

Marketing:

- FAQ completeness
- prohibited phrase absence

QA:

- issue detection precision/recall
- high risk miss rate
