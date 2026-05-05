# Agent와 Workflow 상세 명세

## 설계 원칙

이 프로젝트의 Agent는 자유롭게 아무 일이나 하는 챗봇이 아닙니다. 전체 업무 경로는 workflow로 통제하고, 각 단계 내부에서 필요한 도구 선택과 분석은 Agent가 수행합니다.

기본 workflow:

```text
User Input
  → Planner Agent
  → Data Agent
  → Research Agent
  → Product Agent
  → Marketing Agent
  → QA/Compliance Agent
  → Human Approval Node
  → Save/Export Node
```

## LangGraph 상태

### GraphState

```python
class GraphState(TypedDict):
    run_id: str
    user_request: dict
    normalized_request: dict
    plan: list[dict]
    source_items: list[dict]
    retrieved_documents: list[dict]
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
- 실패 시 `errors`에 추가하고, recoverable이면 다음 fallback path를 실행합니다.

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
    "region_name": "부산",
    "region_code": "6",
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
      "type": "data_lookup",
      "description": "부산 지역 관광지 후보 조회",
      "required_tools": ["tourapi_area_based_list", "tourapi_search_keyword"]
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
- 지역이 불명확하면 `needs_clarification`으로 표시하지만, MVP에서는 최대한 합리적 추정으로 진행합니다.
- 가격, 예약 가능 여부, 실시간 재고는 알 수 없다고 표시합니다.

## Data Agent

### 역할

Planner가 만든 plan에 따라 외부/내부 데이터를 조회합니다.

### 입력

```json
{
  "normalized_request": {
    "region_code": "6",
    "start_date": "2026-05-01",
    "end_date": "2026-05-31",
    "target_customer": "foreign_travelers",
    "preferred_themes": ["night_view", "festival"]
  }
}
```

### 도구

- `tourapi_area_code`
- `tourapi_area_based_list`
- `tourapi_search_keyword`
- `tourapi_search_festival`
- `tourapi_search_stay`
- `tourapi_detail_common`
- `tourapi_detail_image`
- `tourism_demand_resource`
- `local_product_search`
- `vector_search`

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
  ]
}
```

### 실패 처리

- TourAPI 실패: mock/cache fallback
- 수요 API 실패: `demand_data_unavailable` flag
- 이미지 조회 실패: 상품 기획은 계속 진행

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

자동 생성 결과를 사람이 승인하기 전 workflow를 멈춥니다.

### 승인 조건

- QA high severity issue가 없거나 사람이 override reason을 입력해야 합니다.
- result preview를 확인해야 합니다.
- 승인 코멘트를 남길 수 있습니다.

### 승인 API

```http
POST /api/workflow-runs/{run_id}/approval
```

```json
{
  "decision": "approved",
  "comment": "행사 날짜는 별도 확인 예정. 나머지 초안 승인.",
  "override_high_risk": false
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
| Eval judge | cheap/standard batch | 비용 통제 필요 |

## 프롬프트 버전 관리

각 prompt는 파일로 분리합니다.

```text
backend/app/agents/prompts/
  planner_v1.md
  research_v1.md
  product_v1.md
  marketing_v1.md
  qa_v1.md
```

prompt metadata:

```yaml
id: product_v1
owner: product_agent
created_at: 2026-05-05
expected_output_schema: ProductIdeas
```

DB에는 workflow run마다 prompt version을 저장합니다.

## 재실행 정책

사용자가 QA 결과를 보고 수정 요청하면 전체 workflow를 다시 돌리지 않습니다.

재실행 단위:

- Marketing only
- Product + Marketing + QA
- QA only
- Data refresh + downstream all

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

