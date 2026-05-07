# Backend API와 DB 명세

## Backend 목표

Backend는 agent workflow 실행과 운영 상태 저장의 중심입니다.

역할:

- workflow template CRUD
- workflow run 생성/실행/조회
- agent step/tool call/LLM call 로그 저장
- 관광 데이터 조회와 cache
- RAG 색인/검색
- 생성 결과 저장
- 사람 승인/반려
- Poster Studio prompt/image asset 저장
- 평가 실행/리포트
- 비용/사용량 집계

## API 기본 규칙

Base URL:

```text
/api
```

응답 envelope:

```json
{
  "data": {},
  "error": null,
  "meta": {
    "request_id": "req_..."
  }
}
```

오류 응답:

```json
{
  "data": null,
  "error": {
    "code": "WORKFLOW_NOT_FOUND",
    "message": "Workflow run not found",
    "details": {}
  },
  "meta": {
    "request_id": "req_..."
  }
}
```

## API 엔드포인트

이 섹션은 전체 제품 목표 API까지 포함합니다. 현재 Phase 9.6 코드에 구현된 API는 아래 범위입니다.

- `GET /api/health`
- `GET /api/workflows`
- `POST /api/workflow-runs`
- `GET /api/workflow-runs`
- `GET /api/workflow-runs/{run_id}`
- `GET /api/workflow-runs/{run_id}/steps`
- `GET /api/workflow-runs/{run_id}/tool-calls`
- `GET /api/workflow-runs/{run_id}/llm-calls`
- `GET /api/workflow-runs/{run_id}/approvals`
- `GET /api/workflow-runs/{run_id}/result`
- `POST /api/workflow-runs/{run_id}/approve`
- `POST /api/workflow-runs/{run_id}/reject`
- `POST /api/workflow-runs/{run_id}/request-changes`
- `POST /api/workflow-runs/{run_id}/revisions`
- `GET /api/data/sources/capabilities`
- `GET /api/data/tourism/search`
- `POST /api/data/tourism/details/enrich`
- `POST /api/rag/ingest/tourism`
- `POST /api/rag/search`
- `POST /api/llm/key-check`

아래에 남아 있는 cancel/retry, report, sync, eval, cost, poster API는 후속 Phase에서 구현할 목표입니다.

### Health

```http
GET /api/health
```

응답:

```json
{
  "status": "ok",
  "version": "0.1.0",
  "db": "ok",
  "vector_db": "ok"
}
```

### Workflow templates

```http
GET /api/workflows
POST /api/workflows
GET /api/workflows/{template_id}
PUT /api/workflows/{template_id}
DELETE /api/workflows/{template_id}
```

Template body:

```json
{
  "name": "Default Product Planning",
  "description": "TourAPI 기반 상품 기획 기본 workflow",
  "nodes": [
    {
      "id": "planner",
      "type": "planner_agent",
      "position": {"x": 100, "y": 100},
      "config": {}
    }
  ],
  "edges": [
    {
      "id": "edge_1",
      "source": "planner",
      "target": "data_agent"
    }
  ]
}
```

### Workflow runs

```http
POST /api/workflow-runs
GET /api/workflow-runs
GET /api/workflow-runs/{run_id}
POST /api/workflow-runs/{run_id}/cancel
POST /api/workflow-runs/{run_id}/retry
```

Run 생성 request:

```json
{
  "template_id": "default_product_planning",
  "input": {
    "message": "이번 달 부산에서 외국인 대상 액티비티 상품을 5개 기획해줘",
    "region": "부산",
    "period": "2026-05",
    "target_customer": "외국인",
    "product_count": 5,
    "preferences": ["야간 관광", "축제"]
  }
}
```

Run response:

```json
{
  "id": "run_01",
  "status": "pending",
  "template_id": "default_product_planning",
  "created_at": "2026-05-05T10:00:00+09:00"
}
```

생성 API는 즉시 `pending` run을 반환하고, workflow는 background task에서 실행됩니다. 실행 중에는 frontend가 polling으로 `pending -> running -> awaiting_approval` 또는 `failed` 변화를 확인합니다.

### Agent steps

```http
GET /api/workflow-runs/{run_id}/steps
GET /api/workflow-runs/{run_id}/steps/{step_id}
```

### Tool calls

```http
GET /api/workflow-runs/{run_id}/tool-calls
```

### Result

```http
GET /api/workflow-runs/{run_id}/result
GET /api/workflow-runs/{run_id}/report.md
```

### Approval

```http
POST /api/workflow-runs/{run_id}/approve
POST /api/workflow-runs/{run_id}/reject
POST /api/workflow-runs/{run_id}/request-changes
GET /api/workflow-runs/{run_id}/approvals
```

Request:

```json
{
  "reviewer": "operator",
  "comment": "초안 승인. 가격은 추후 운영자가 확정.",
  "high_risk_override": false,
  "requested_changes": []
}
```

Decision:

- `approved`
- `rejected`
- `request_changes`

### Revision

```http
POST /api/workflow-runs/{run_id}/revisions
```

Request:

```json
{
  "revision_mode": "llm_partial_rewrite",
  "comment": "선택한 QA 이슈 반영",
  "requested_changes": ["과장 표현 완화", "집결지 안내 보강"],
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

지원 모드:

- `manual_save`: 수정한 결과를 새 revision run으로 저장하고 QA는 재실행하지 않습니다.
- `manual_edit`: 수정한 결과를 새 revision run으로 저장하고 QA만 재실행합니다.
- `llm_partial_rewrite`: 선택된 QA issue와 requested changes에 필요한 필드만 AI가 patch하고 QA를 재실행합니다.
- `qa_only`: 결과는 유지하고 QA만 재실행합니다.

모든 revision run은 최상위 원본 run을 `parent_run_id`로 가지며 `revision_number`가 증가합니다. 기존 run의 `final_output`은 직접 수정하지 않습니다.

### Poster Studio

```http
POST /api/workflow-runs/{run_id}/posters/draft
GET /api/workflow-runs/{run_id}/posters
GET /api/posters/{poster_id}
PATCH /api/posters/{poster_id}
POST /api/posters/{poster_id}/generate
POST /api/posters/{poster_id}/approve
POST /api/posters/{poster_id}/reject
```

Poster draft request:

```json
{
  "product_id": "product_1",
  "purpose": "sns_feed",
  "aspect_ratio": "4:5",
  "style_direction": "프리미엄 야간 관광",
  "copy_density": "balanced",
  "include_fields": ["상품명", "지역", "핵심 코스", "CTA", "확인 필요 문구"],
  "visual_source_mode": "ai_generated",
  "custom_instruction": "밤 분위기는 세련되게, 텍스트는 적게"
}
```

Poster draft response:

```json
{
  "poster_id": "poster_001",
  "run_id": "run_001",
  "product_id": "product_1",
  "status": "draft",
  "copy_candidates": {
    "headlines": ["부산의 밤을 걷는 야경 푸드투어"],
    "subheadlines": ["외국인 자유여행객을 위한 로컬 야간 코스"],
    "ctas": ["운영 조건 확인 후 예약 오픈"]
  },
  "selected_content": [
    {"key": "headline", "value": "부산의 밤을 걷는 야경 푸드투어", "selected": true},
    {"key": "region", "value": "부산", "selected": true}
  ],
  "prompt_draft": "...",
  "constraints": [
    "가격을 확정하지 말 것",
    "예약 가능 여부를 단정하지 말 것"
  ]
}
```

Patch request:

```json
{
  "selected_content": [],
  "final_prompt": "...",
  "manual_prompt_override": true,
  "options": {
    "purpose": "sns_feed",
    "aspect_ratio": "4:5",
    "quality": "medium",
    "format": "png"
  }
}
```

Generate request:

```json
{
  "model": "gpt-image-2",
  "quality": "medium",
  "size": "auto",
  "format": "png"
}
```

Generate response:

```json
{
  "poster_id": "poster_001",
  "status": "needs_review",
  "asset_url": "/api/posters/poster_001/image",
  "provider": "openai",
  "model": "gpt-image-2",
  "latency_ms": 45000,
  "estimated_cost_usd": 0.0
}
```

정책:

- poster draft는 workflow run의 `final_output`을 변경하지 않습니다.
- poster generation은 사용자가 prompt와 옵션을 확인한 뒤 실행합니다.
- 생성 결과는 기본 `needs_review` 상태입니다.
- approve 전에는 외부 게시/export 기본 액션을 막습니다.
- `gpt-image-2` 모델명과 가격은 구현 직전에 OpenAI 공식 문서로 재확인합니다.

### Data source

```http
GET /api/data/tourism/search
GET /api/data/tourism/items/{item_id}
POST /api/data/tourism/sync
GET /api/data/sources/capabilities
POST /api/data/tourism/details/enrich
```

현재 Phase 9.6 구현 API는 `GET /api/data/tourism/search`, `GET /api/data/sources/capabilities`, `POST /api/data/tourism/details/enrich`입니다. TourAPI catalog sync는 API가 아니라 `python -m app.tools.sync_tourapi_catalogs` CLI로 제공합니다. 개별 item 조회와 API 기반 sync endpoint는 후속 Phase 목표입니다.

Search query:

```text
/api/data/tourism/search?region=부산&keyword=야경&type=attraction
```

상세 보강 query:

```text
/api/data/tourism/search?region_code=6&content_type=event&enrich_details=true&detail_limit=1
```

상세 보강 request:

```json
{
  "item_ids": ["tourapi:content:2786391"],
  "content_ids": [],
  "run_id": "run_...",
  "limit": 1
}
```

상세 보강 response에는 보강된 `items`, canonical `entities`, `visual_assets`, source document/index count, summary가 포함됩니다. `visual_assets.usage_status`는 기본 `candidate`입니다.

### RAG search

```http
POST /api/rag/search
```

Request:

```json
{
  "query": "부산 외국인 야간 관광 전통시장",
  "filters": {
    "region_code": "6",
    "content_type": ["attraction", "event"]
  },
  "top_k": 10
}
```

### Evaluation

```http
POST /api/evals/run
GET /api/evals
GET /api/evals/{eval_run_id}
GET /api/evals/{eval_run_id}/report.md
```

Eval run request:

```json
{
  "dataset_path": "backend/app/evals/datasets/mvp_busan.jsonl",
  "sample_size": 20,
  "model_policy": "cheap_eval"
}
```

### Cost

```http
GET /api/costs/summary
GET /api/costs/runs/{run_id}
GET /api/costs/models
```

## DB 모델

아래는 SQLAlchemy 기준 주요 테이블입니다.

현재 Phase 9.6 코드에 실제 구현된 core table은 workflow, approval, tourism item, source document, TourAPI `ldong/lcls` catalog, geo resolution, KTO data foundation, usage log 중심입니다. Poster, evaluation, cost dashboard 전용 table은 후속 Phase 목표입니다.

### users

```text
id UUID PK
email string unique
name string
role string
created_at datetime
```

MVP는 seed user 1명으로 시작 가능합니다.

### workflow_templates

```text
id string PK
name string
description text
version int
nodes json
edges json
is_default bool
created_by UUID nullable
created_at datetime
updated_at datetime
```

### workflow_runs

```text
id string PK
template_id string FK
status string
input json
normalized_input json nullable
final_output json nullable
error json nullable
cost_total_usd numeric
latency_ms int
parent_run_id string nullable
revision_number int default 0
revision_mode string nullable
created_by UUID nullable
created_at datetime
started_at datetime nullable
finished_at datetime nullable
```

### agent_steps

```text
id string PK
run_id string FK
agent_name string
step_type string
status string
input json
output json nullable
error json nullable
prompt_version string nullable
model string nullable
started_at datetime nullable
finished_at datetime nullable
latency_ms int nullable
```

### tool_calls

```text
id string PK
run_id string FK
step_id string FK nullable
tool_name string
status string
arguments json
response_summary json nullable
error json nullable
source string nullable
latency_ms int nullable
created_at datetime
```

### llm_calls

```text
id string PK
run_id string FK
step_id string FK nullable
provider string
model string
purpose string
prompt_tokens int
completion_tokens int
total_tokens int
cost_usd numeric
latency_ms int
cache_hit bool
request_hash string nullable
created_at datetime
```

### poster_assets

후속 Poster Studio Phase에서 구현할 목표 테이블입니다. 현재 Phase 9.6 코드에는 아직 없습니다.

```text
id string PK
run_id string FK
product_id string
source_revision_run_id string nullable
status string
purpose string
aspect_ratio string
style_direction string nullable
copy_density string
include_fields json
visual_source_mode string
selected_content json
prompt_draft text
final_prompt text nullable
manual_prompt_override bool default false
constraints json
image_path text nullable
asset_metadata json nullable
review_comment text nullable
approved_by string nullable
approved_at datetime nullable
created_at datetime
updated_at datetime
```

Status:

- `draft`
- `generating`
- `needs_review`
- `approved`
- `rejected`
- `failed`

### poster_image_calls

후속 Poster Studio Phase에서 구현할 목표 테이블입니다. 현재 Phase 9.6 코드에는 아직 없습니다.

```text
id string PK
poster_id string FK
run_id string FK
provider string
model string
purpose string
request_options json
response_summary json nullable
cost_usd numeric nullable
latency_ms int nullable
error json nullable
created_at datetime
```

### tourism_items

```text
id string PK
source string
content_id string
content_type string
title string
region_code string
sigungu_code string nullable
address text nullable
map_x float nullable
map_y float nullable
tel string nullable
homepage text nullable
overview text nullable
image_url text nullable
license_type string nullable
raw json
last_synced_at datetime
created_at datetime
updated_at datetime
```

Unique:

- `(source, content_id)`

### tourism_events

초기 설계의 분리 테이블 후보입니다. 현재 Phase 9.6 코드에서는 행사도 `tourism_items`에 저장하고 `content_type=event`, `event_start_date`, `event_end_date`, `raw`로 관리합니다.

```text
id string PK
tourism_item_id string FK nullable
source string
content_id string
title string
region_code string
event_start_date date nullable
event_end_date date nullable
place text nullable
raw json
last_synced_at datetime
```

### source_documents

```text
id string PK
source string
source_item_id string
title string
content text
metadata json
embedding_status string
created_at datetime
updated_at datetime
```

Phase 9 metadata에는 `source_family`, `trust_level`, `license_note`, `detail_common_available`, `detail_intro_available`, `detail_info_count`, `detail_image_count`, `visual_asset_count`, `image_candidates` 같은 상세 보강 정보가 포함될 수 있습니다.

### tourism_entities

```text
id string PK
canonical_name string
entity_type string
region_code string nullable
sigungu_code string nullable
address text nullable
map_x numeric nullable
map_y numeric nullable
primary_source_item_id string nullable
match_confidence numeric nullable
metadata json
created_at datetime
updated_at datetime
```

Phase 9에서는 TourAPI content_id 기준 canonical entity를 저장합니다. 예: `entity:tourapi:content:2786391`.

### tourism_visual_assets

```text
id string PK
entity_id string FK nullable
source_family string
source_item_id string nullable
title string nullable
image_url text
thumbnail_url text nullable
shooting_place string nullable
shooting_date string nullable
photographer string nullable
keywords json
license_type string nullable
license_note text nullable
usage_status string
raw json
retrieved_at datetime nullable
created_at datetime
```

Phase 9에서는 `detailImage2` 결과를 `usage_status=candidate`로 저장합니다. 게시 가능 여부는 별도 검토 또는 Poster Studio 단계에서 판단합니다.

### tourism_route_assets

```text
id string PK
entity_id string FK nullable
source_family string
course_name string nullable
path_name string nullable
gpx_url text nullable
distance_km numeric nullable
estimated_duration string nullable
start_point string nullable
end_point string nullable
nearby_places json
safety_notes json
raw json
retrieved_at datetime nullable
created_at datetime
```

Phase 8 foundation으로 테이블만 준비되어 있으며, 두루누비/route API 연결은 후속 Phase입니다.

### tourism_signal_records

```text
id string PK
entity_id string FK nullable
region_code string nullable
sigungu_code string nullable
source_family string
signal_type string
period_start string nullable
period_end string nullable
value_json json
interpretation_note text nullable
raw json
retrieved_at datetime nullable
created_at datetime
```

Phase 8 foundation으로 테이블만 준비되어 있으며, 수요/혼잡/연관 관광지 데이터 연결은 후속 Phase입니다.

### enrichment_runs

```text
id string PK
workflow_run_id string nullable
trigger_type string
status string
gap_report_json json
plan_json json
result_summary_json json
created_at datetime
started_at datetime nullable
finished_at datetime nullable
```

### enrichment_tool_calls

```text
id string PK
enrichment_run_id string FK nullable
workflow_run_id string nullable
plan_id string nullable
tool_name string
source_family string
status string
arguments_json json
response_summary_json nullable
error_json nullable
cache_hit bool
latency_ms int nullable
created_at datetime
```

### web_evidence_documents

```text
id string PK
workflow_run_id string FK nullable
entity_id string FK nullable
field_name string
status string
source_type string
title string nullable
url text
summary text nullable
retrieved_at datetime nullable
published_at datetime nullable
confidence numeric nullable
needs_human_review bool
raw_json json
created_at datetime
```

공식 웹 근거 수집은 Phase 12 이후 목표이며, 현재는 저장 기반만 준비되어 있습니다.

### generated_products

```text
id string PK
run_id string FK
status string
title string
target_customer string
payload json
source_ids json
qa_status string
created_at datetime
updated_at datetime
```

### approvals

```text
id string PK
run_id string FK
decision string
comment text nullable
metadata json
reviewer string
created_at datetime
```

### eval_runs

```text
id string PK
dataset_path string
sample_size int
model_policy string
status string
metrics_summary json
report_path string nullable
created_at datetime
finished_at datetime nullable
```

### eval_results

```text
id string PK
eval_run_id string FK
case_id string
workflow_run_id string nullable
input json
output json
metrics json
passed bool
created_at datetime
```

### usage_costs

```text
id string PK
run_id string FK nullable
eval_run_id string FK nullable
provider string
model string
purpose string
input_tokens int
output_tokens int
cost_usd numeric
created_at datetime
```

## Pydantic 스키마

### WorkflowRunInput

```python
class WorkflowRunInput(BaseModel):
    message: str
    region: str | None = None
    period: str | None = None
    target_customer: str | None = None
    product_count: int = Field(default=3, ge=1, le=10)
    preferences: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    output_language: Literal["ko", "en"] = "ko"
```

### ProductIdea

```python
class ProductIdea(BaseModel):
    title: str
    one_liner: str
    target_customer: str
    core_value: list[str]
    itinerary: list[ItineraryItem]
    estimated_duration: str | None
    operation_difficulty: Literal["low", "medium", "high"]
    source_ids: list[str]
    assumptions: list[str]
    not_to_claim: list[str]
```

### QAIssue

```python
class QAIssue(BaseModel):
    product_id: str | None = None
    severity: Literal["low", "medium", "high"]
    type: str
    message: str
    field_path: str | None = None
    suggested_fix: str | None = None
```

### WorkflowRevisionCreate

```python
class WorkflowRevisionCreate(BaseModel):
    revision_mode: Literal[
        "manual_save",
        "manual_edit",
        "llm_partial_rewrite",
        "qa_only",
    ]
    comment: str | None = None
    requested_changes: list[str] = []
    qa_issues: list[dict] = []
    qa_settings: dict = {}
    products: list[dict] | None = None
    marketing_assets: list[dict] | None = None
```

## Background execution

MVP 단순 구현:

- `BackgroundTasks`로 workflow 실행
- 상태는 DB polling

P1 개선:

- Redis + Celery/RQ/Arq
- WebSocket/SSE로 실시간 로그 stream

MVP polling:

```text
Frontend calls GET /api/workflow-runs/{run_id} every 2 seconds while running.
```

## LLM gateway interface

```python
class LLMGateway:
    async def complete_json(
        self,
        *,
        run_id: str,
        step_id: str | None,
        purpose: str,
        messages: list[dict],
        response_model: type[BaseModel],
        model_tier: ModelTier,
    ) -> BaseModel:
        ...
```

필수 기능:

- Gemini API 호출
- token usage 파싱
- cost 계산
- `llm_calls` 저장
- schema validation
- retry/error logging
- 실패 시 deterministic fallback 없이 workflow run을 `failed`로 기록

## Tool logging decorator

모든 tool은 공통 decorator를 통과합니다.

```python
@log_tool_call("tourapi_search_keyword")
async def search_keyword(args: SearchKeywordArgs) -> list[TourismItem]:
    ...
```

저장 항목:

- tool name
- arguments
- status
- latency
- response summary
- error

## Approval gate helper

```python
def require_approval(run: WorkflowRun, tool_name: str) -> None:
    if tool_name in APPROVAL_REQUIRED_TOOLS and run.status != "approved":
        raise ApprovalRequiredError(tool_name)
```

## Testing strategy

### Unit tests

- date parser
- region resolver
- TourAPI response parser
- product schema validation
- QA rule checks
- cost calculation
- approval gate

### Integration tests

- create workflow run with real TourAPI provider
- run full workflow
- approve result
- export JSON report
- eval run with 2 sample cases

### Test data

```text
backend/app/tests/data/
  expected_product_schema.json
```
