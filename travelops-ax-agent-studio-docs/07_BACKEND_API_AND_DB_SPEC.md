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
  "status": "running",
  "template_id": "default_product_planning",
  "created_at": "2026-05-05T10:00:00+09:00"
}
```

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
POST /api/workflow-runs/{run_id}/approval
```

Request:

```json
{
  "decision": "approved",
  "comment": "초안 승인. 가격은 추후 운영자가 확정.",
  "override_high_risk": false
}
```

Decision:

- `approved`
- `rejected`
- `request_changes`

### Data source

```http
GET /api/data/tourism/search
GET /api/data/tourism/items/{item_id}
POST /api/data/tourism/sync
```

Search query:

```text
/api/data/tourism/search?region=부산&keyword=야경&type=attraction
```

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
  "model_policy": "cheap_eval",
  "use_mock_provider": true
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
override_high_risk bool
reviewer_id UUID nullable
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
    severity: Literal["low", "medium", "high"]
    type: str
    message: str
    field_path: str | None = None
    suggested_fix: str | None = None
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

- LiteLLM 호출
- token usage 파싱
- cost 계산
- `llm_calls` 저장
- schema validation
- retry/fallback

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

- create workflow run with mock provider
- run full workflow
- approve result
- export JSON report
- eval run with 2 sample cases

### Test fixtures

```text
backend/app/tests/fixtures/
  mock_tourapi_busan.json
  mock_workflow_input.json
  expected_product_schema.json
```

