# 시스템 아키텍처

## 아키텍처 목표

TravelOps AX Agent Studio는 에이전트 데모가 아니라 운영 업무 자동화 시스템입니다. 따라서 아키텍처는 다음 요구를 만족해야 합니다.

- 에이전트 실행 상태를 저장할 수 있어야 합니다.
- 도구 호출과 LLM 호출을 추적할 수 있어야 합니다.
- 외부 API 실패와 LLM 실패를 복구하거나 부분 결과로 남길 수 있어야 합니다.
- 사람 승인 전에는 외부 저장/전송이 실행되지 않아야 합니다.
- 평가 파이프라인이 운영 workflow와 같은 코드를 호출해야 합니다.
- Bootstrap 기반 프론트엔드가 workflow 상태와 결과를 읽기 쉬운 형태로 보여줘야 합니다.

## 전체 구성

```text
Browser
  └─ React/Next.js + Bootstrap + React Flow
       ├─ Workflow Builder
       ├─ Run Console
       ├─ Result Review
       └─ Evaluation Dashboard

Backend API
  └─ FastAPI
       ├─ Auth/User Context
       ├─ Workflow API
       ├─ Agent Run API
       ├─ Data Source API
       ├─ Approval API
       ├─ Evaluation API
       └─ Billing/Cost API

Agent Runtime
  └─ LangGraph
       ├─ Planner Agent
       ├─ Data Agent
       ├─ Research Agent
       ├─ Product Agent
       ├─ Marketing Agent
       ├─ QA/Compliance Agent
       └─ Human Approval Node

Tool Layer
  ├─ TourAPI Client
  ├─ Tourism Demand API Client
  ├─ Local DB Search Tool
  ├─ Vector Search Tool
  ├─ Export Tool
  └─ Cost Tracking Tool

Storage
  ├─ SQLite/PostgreSQL
  ├─ Chroma or Qdrant
  ├─ Local file storage for reports/eval artifacts
  └─ Redis optional for queue/cache

LLM Gateway
  └─ LiteLLM
       ├─ Gemini low-cost model
       ├─ OpenAI model
       ├─ Claude model
       └─ local embedding model optional
```

## 주요 설계 결정

### Backend는 FastAPI

Python agent stack과 잘 맞고, Pydantic 스키마를 API와 Agent 입출력에 재사용하기 좋습니다.

### Agent runtime은 LangGraph 우선

상태가 있는 장기 실행 workflow, human approval, step retry, tool call orchestration을 보여주기에 적합합니다. OpenAI Agents SDK는 대체 구현 또는 비교 섹션으로 남깁니다.

### LLM provider 직접 호출 금지

모든 LLM 호출은 `LLMGateway`를 통해 LiteLLM으로 보냅니다.

장점:

- provider 교체 가능
- 모델별 비용 추적
- fallback/timeout/retry 정책 통일
- eval과 운영에서 같은 호출 인터페이스 사용

### 데이터 provider는 interface로 분리

TourAPI 키가 없어도 개발과 테스트가 가능해야 합니다.

```python
class TourismDataProvider(Protocol):
    async def search_by_keyword(self, query: str, region_code: str | None) -> list[TourismItem]: ...
    async def search_events(self, region_code: str, start_date: date, end_date: date) -> list[TourismEvent]: ...
    async def get_detail(self, content_id: str) -> TourismDetail: ...
```

구현체:

- `TourApiProvider`: 실제 한국관광공사 API 호출
- `MockTourismProvider`: fixture JSON 기반
- `CachedTourismProvider`: DB/cache 우선 조회, miss일 때 실제 API 호출

## 요청 실행 흐름

### 1. Workflow Run 생성

프론트엔드가 `POST /api/workflow-runs`를 호출합니다.

```json
{
  "template_id": "default_product_planning",
  "input": {
    "region": "부산",
    "period": "2026-05",
    "target_customer": "외국인",
    "product_count": 5,
    "preferences": ["야간 관광", "축제", "전통시장"]
  }
}
```

Backend는 다음을 저장합니다.

- `workflow_runs`
- `workflow_run_events`
- initial `agent_steps`

### 2. Planner Agent 실행

Planner는 사용자 요청을 구조화합니다.

출력 예:

```json
{
  "normalized_request": {
    "region": "부산",
    "region_code": "6",
    "start_date": "2026-05-01",
    "end_date": "2026-05-31",
    "target_customer": "foreign_travelers",
    "product_count": 5
  },
  "plan": [
    {"step": "resolve_region_code", "tool": "tourapi.area_code"},
    {"step": "search_attractions", "tool": "tourapi.area_based_list"},
    {"step": "search_events", "tool": "tourapi.search_festival"},
    {"step": "search_accommodations", "tool": "tourapi.search_stay"},
    {"step": "analyze_demand", "tool": "tourism_demand_api"},
    {"step": "generate_products", "agent": "ProductAgent"},
    {"step": "generate_marketing_assets", "agent": "MarketingAgent"},
    {"step": "qa_review", "agent": "QAComplianceAgent"},
    {"step": "human_approval", "node": "HumanApprovalNode"}
  ]
}
```

### 3. Data Agent 실행

Data Agent는 필요한 도구를 호출하고 source item을 저장합니다.

저장 대상:

- `source_documents`
- `tourism_items`
- `tool_calls`
- `vector_documents`

### 4. Research Agent 실행

Research Agent는 수집 데이터를 분석합니다.

분석 항목:

- 관광지 유형
- 행사 기간 매칭
- 타깃 고객 적합도
- 계절성
- 이동 동선 가능성
- 주변 숙박/인프라
- 데이터 부족 영역

### 5. Product Agent 실행

Product Agent는 상품 아이디어를 생성합니다.

출력은 구조화된 JSON이어야 합니다. JSON schema validation에 실패하면 retry합니다.

### 6. Marketing Agent 실행

Marketing Agent는 상품 아이디어별 카피를 생성합니다.

출력:

- 상세페이지 headline/summary/sections
- FAQ
- SNS copy
- search keywords
- SEO title/meta description

### 7. QA/Compliance Agent 실행

QA Agent는 생성 결과와 source evidence를 비교합니다.

검수 출력:

```json
{
  "overall_status": "needs_review",
  "issues": [
    {
      "severity": "high",
      "type": "date_uncertainty",
      "message": "축제 종료일이 출처에서 확인되지 않았는데 확정 일정처럼 표현했습니다.",
      "field_path": "products[2].sales_copy.sections[1]",
      "suggested_fix": "일정은 공식 페이지 확인 필요로 수정하세요."
    }
  ]
}
```

### 8. Human Approval Node

workflow는 `awaiting_approval`에서 멈춥니다.

사용자가 승인하면:

- `approval_status = approved`
- 결과가 `approved_outputs`에 저장됩니다.
- 선택된 export tool이 실행됩니다.

사용자가 반려하면:

- `approval_status = rejected`
- 수정 의견이 저장됩니다.
- 선택적으로 Product/Marketing/QA 단계만 재실행합니다.

## 상태 모델

### WorkflowRun status

- `pending`: 생성됨
- `running`: 실행 중
- `awaiting_approval`: 사람 승인 대기
- `approved`: 승인됨
- `rejected`: 반려됨
- `failed`: 실패
- `cancelled`: 취소

### AgentStep status

- `queued`
- `running`
- `succeeded`
- `failed`
- `skipped`
- `waiting_for_human`

### ToolCall status

- `started`
- `succeeded`
- `failed`
- `retried`
- `blocked_by_budget`
- `blocked_by_approval`

## 데이터 흐름

```text
User Input
  → Request Normalization
  → Planner Plan
  → Tool Calls
  → Raw Source Data
  → Normalized Source Documents
  → Embeddings / Vector Index
  → Research Summary
  → Product Ideas
  → Marketing Assets
  → QA Review
  → Human Approval
  → Approved Output
  → Evaluation/Cost Report
```

## 폴더 구조 제안

```text
travelops/
  backend/
    app/
      main.py
      core/
        config.py
        logging.py
        security.py
      db/
        base.py
        session.py
        models.py
        migrations/
      schemas/
        workflow.py
        agents.py
        tourism.py
        evaluation.py
        billing.py
      api/
        routes_workflows.py
        routes_runs.py
        routes_data.py
        routes_approvals.py
        routes_evals.py
        routes_costs.py
      agents/
        graph.py
        state.py
        planner.py
        data_agent.py
        research_agent.py
        product_agent.py
        marketing_agent.py
        qa_agent.py
        prompts/
      tools/
        tourapi.py
        tourism_demand.py
        vector_search.py
        exports.py
      llm/
        gateway.py
        cost_tracker.py
        model_policy.py
      rag/
        chunking.py
        embeddings.py
        retriever.py
      evals/
        datasets/
        metrics.py
        run_eval.py
      tests/
    pyproject.toml
    Dockerfile
  frontend/
    src/
      app/
      components/
      pages/
      services/
      styles/
      workflows/
    package.json
    Dockerfile
  docker-compose.yml
  docs/
```

## 오류 처리 정책

### 외부 API 오류

- 429: exponential backoff, 최대 3회
- 5xx: retry 후 실패 기록
- 4xx: 사용자/API 설정 오류로 기록
- timeout: partial result 유지

### LLM 오류

- schema validation 실패: 같은 모델로 1회 retry
- provider timeout: fallback model로 1회 retry
- budget exceeded: 비싼 모델 호출 차단, 저가 모델 또는 실패로 전환

### Vector DB 오류

- RAG 검색 실패 시 DB keyword search fallback
- embedding 실패 시 source-only generation으로 전환하되 confidence 낮춤

## 평가 실행 흐름

```text
eval dataset JSONL
  → run workflow with fixed seed/model policy
  → collect outputs/tool calls/retrieved docs/cost/latency
  → calculate metrics
  → save eval_runs
  → write reports/eval_YYYYMMDD.md
```

## 운영에서 중요한 제약

- 모든 생성 결과는 `source_ids`를 들고 있어야 합니다.
- 상품 저장은 approval 뒤에만 실행합니다.
- 외부 저장 tool은 `requires_approval=True` metadata가 있어야 합니다.
- 비용 추적 없는 LLM 호출은 금지합니다.
- 프론트엔드에서 API secret을 직접 사용하면 안 됩니다.
- Tailwind CSS 관련 설정 파일을 만들지 않습니다.

