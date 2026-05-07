# 시스템 아키텍처

## 아키텍처 목표

PARAVOCA AX Agent Studio는 운영 업무 자동화 시스템입니다. 따라서 아키텍처는 다음 요구를 만족해야 합니다.

- 에이전트 실행 상태를 저장할 수 있어야 합니다.
- 도구 호출과 LLM 호출을 추적할 수 있어야 합니다.
- 외부 API 실패와 LLM 실패를 복구하거나 부분 결과로 남길 수 있어야 합니다.
- 사람 승인 전에는 외부 저장/전송이 실행되지 않아야 합니다.
- 평가 파이프라인이 운영 workflow와 같은 코드를 호출해야 합니다.
- Mantine UI 기반 프론트엔드가 workflow 상태와 결과를 읽기 쉬운 형태로 보여줘야 합니다.

## 전체 구성

```text
Browser
  └─ React/Next.js + Mantine UI + CSS Modules + React Flow
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
       ├─ GeoResolver Agent
       ├─ Data Agent
       ├─ Research Agent
       ├─ Product Agent
       ├─ Marketing Agent
       ├─ QA/Compliance Agent
       └─ Human Approval Node

Tool Layer
  ├─ TourAPI Client
  ├─ TourAPI Catalog Sync
  ├─ Tourism Demand API Client
  ├─ Local DB Search Tool
  ├─ Vector Search Tool
  ├─ Export Tool
  ├─ Poster Prompt Tool
  ├─ OpenAI Image Generation Tool
  └─ Cost Tracking Tool

Storage
  ├─ SQLite/PostgreSQL
  ├─ Chroma or Qdrant
  ├─ Poster asset storage
  ├─ Local file storage for reports/eval artifacts
  └─ Redis optional for queue/cache

LLM Gateway
  └─ GeminiGateway
       ├─ Gemini 2.5 Flash-Lite generation model
       ├─ JSON schema validation
       ├─ cost/token/latency logging
       └─ local embedding model optional

Image Generation Gateway
  └─ OpenAIImageGateway
       ├─ gpt-image-2 default candidate
       ├─ prompt/options validation
       ├─ image output storage
       └─ cost/latency logging
```

## 주요 설계 결정

### Backend는 FastAPI

Python agent stack과 잘 맞고, Pydantic 스키마를 API와 Agent 입출력에 재사용하기 좋습니다.

### Agent runtime은 LangGraph 우선

상태가 있는 장기 실행 workflow, human approval, step retry, tool call orchestration을 보여주기에 적합합니다. OpenAI Agents SDK는 대체 구현 또는 비교 섹션으로 남깁니다.

### LLM provider 직접 호출 금지

모든 LLM 호출은 `GeminiGateway`를 통해 보냅니다. OpenAI/GPT는 현재 workflow에서 사용하지 않고, 향후 비교 또는 확장 후보로만 남깁니다.

장점:

- 모델별 비용 추적
- JSON schema validation
- timeout/retry/error logging 정책 통일
- Gemini 호출 실패 시 deterministic fallback 없이 failed run으로 기록

### Poster Studio는 별도 Image Gateway로 분리

후속 Poster Studio에서는 텍스트 workflow와 이미지 생성 workflow를 분리합니다. 상품 기획, 마케팅 문구, QA 검수는 기존 workflow run 결과를 사용하고, 포스터 이미지는 `OpenAIImageGateway`를 통해 생성합니다.

기본 후보 모델:

- `gpt-image-2`: OpenAI 공식 Image generation 문서 기준 기본 이미지 생성 후보
- `gpt-image-1.5`, `gpt-image-1`, `gpt-image-1-mini`: 비용/품질/가용성 비교 후보

설계 원칙:

- 최종 이미지 생성 전 poster prompt draft를 사용자가 확인합니다.
- 생성 요청에는 source document 원문 전체를 넣지 않고, 선택된 상품과 사용자가 승인한 문구만 넣습니다.
- `not_to_claim`, QA issue, requested changes는 prompt constraint로 포함합니다.
- 생성 이미지는 `needs_review` 상태로 저장하고, 사람이 확인한 뒤 사용 가능 상태로 바꿉니다.
- 이미지 모델명, 가격, 파라미터는 구현 직전에 공식 문서로 재확인합니다.

### 데이터 provider는 interface로 분리

TourAPI는 실제 한국관광공사 API만 호출합니다. API 키가 없거나 호출이 실패하면 실패한 tool call, workflow run error, FastAPI 로그에 원인을 기록합니다.

```python
class TourismDataProvider(Protocol):
    async def search_by_keyword(
        self,
        query: str,
        ldong_regn_cd: str | None,
        ldong_signgu_cd: str | None,
    ) -> list[TourismItem]: ...
    async def search_events(
        self,
        ldong_regn_cd: str,
        start_date: date,
        end_date: date,
        ldong_signgu_cd: str | None = None,
    ) -> list[TourismEvent]: ...
    async def get_detail(self, content_id: str) -> TourismDetail: ...
```

구현체:

- `TourApiProvider`: 실제 한국관광공사 API 호출

## 요청 실행 흐름

### 1. Workflow Run 생성

프론트엔드가 `POST /api/workflow-runs`를 호출합니다.

```json
{
  "template_id": "default_product_planning",
  "input": {
    "message": "이번 달 부산에서 외국인 대상 야간 관광 상품을 5개 기획해줘",
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
    "message": "이번 달 부산에서 외국인 대상 야간 관광 상품을 5개 기획해줘",
    "start_date": "2026-05-01",
    "end_date": "2026-05-31",
    "target_customer": "foreign_travelers",
    "product_count": 5
  },
  "plan": [
    {"step": "resolve_geo_scope", "agent": "GeoResolverAgent"},
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

### 3. GeoResolver Agent 실행

GeoResolver는 사용자의 자연어 요청에서 지역 범위를 해석합니다. 기준 데이터는 `python -m app.tools.sync_tourapi_catalogs`로 동기화한 TourAPI v4.4 `ldongCode2?lDongListYn=Y` catalog입니다. 특정 예시 지명을 코드에 강제 매핑하지 않고, catalog exact/normalized/fuzzy 후보를 점수화합니다.

출력 예:

```json
{
  "geo_scope": {
    "mode": "single_area",
    "status": "resolved",
    "locations": [
      {
        "name": "부산광역시 부산진구 전포동 일대",
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

`중구`처럼 후보가 여러 개인 요청은 Data Agent로 넘어가지 않고 run status를 `failed`로 저장하되, UI에는 지역 후보 안내를 표시합니다. 해외 목적지는 `unsupported`로 종료하며 PARAVOCA가 현재 국내 관광 데이터만 지원한다는 안내를 반환합니다. 두 경우 모두 Data Agent와 TourAPI 검색으로 넘어가지 않습니다.

### 4. Data Agent 실행

Data Agent는 `geo_scope` 기준으로 필요한 도구를 호출하고 source item을 저장합니다. 새 workflow의 primary 지역 필터는 legacy `areaCode`가 아니라 `lDongRegnCd`/`lDongSignguCd`입니다.

저장 대상:

- `source_documents`
- `tourism_items`
- `tool_calls`
- `vector_documents`

### 5. Research Agent 실행

Research Agent는 수집 데이터를 분석합니다.

분석 항목:

- 관광지 유형
- 행사 기간 매칭
- 타깃 고객 적합도
- 계절성
- 이동 동선 가능성
- 주변 숙박/인프라
- 데이터 부족 영역

### 6. Product Agent 실행

Product Agent는 상품 아이디어를 생성합니다.

출력은 구조화된 JSON이어야 합니다. JSON schema validation에 실패하면 retry합니다.

### 7. Marketing Agent 실행

Marketing Agent는 상품 아이디어별 카피를 생성합니다.

출력:

- 상세페이지 headline/summary/sections
- FAQ
- SNS copy
- search keywords
- SEO title/meta description

### 8. QA/Compliance Agent 실행

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

### 9. Human Approval Node

workflow는 `awaiting_approval`에서 멈춥니다.

사용자가 승인하면:

- `approval_status = approved`
- 결과가 `approved_outputs`에 저장됩니다.
- 선택된 export tool이 실행됩니다.

사용자가 반려하면:

- `approval_status = rejected`
- 수정 의견이 저장됩니다.
- 기존 run을 덮어쓰지 않고 revision run을 새로 생성합니다.
- revision run은 최상위 원본 run 아래에 연결되고 `revision_number`가 증가합니다.
- AI 수정은 Product/Marketing 전체 재생성 없이 선택된 QA issue와 requested changes에 필요한 필드만 patch합니다.
- 직접 수정 또는 QA 재검수는 Product/Marketing 재생성 없이 QA/Compliance만 실행할 수 있습니다.

## 상태 모델

### WorkflowRun status

- `pending`: 생성됨
- `running`: 실행 중
- `awaiting_approval`: 사람 승인 대기
- `approved`: 승인됨
- `rejected`: 반려됨
- `changes_requested`: 수정 요청됨
- `failed`: 실패
- `cancelled`: 취소
- `unsupported`: PARAVOCA 현재 지원 범위 밖

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
  → Geo Scope Resolution
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
paravoca/
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
        geo_resolver.py
        data_agent.py
        research_agent.py
        product_agent.py
        marketing_agent.py
        qa_agent.py
        prompts/
      tools/
        tourapi.py
        tourism_demand.py
        sync_tourapi_catalogs.py
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
- timeout: 실패 기록 후 run 실패 처리

### LLM 오류

- schema validation 실패: 같은 모델로 1회 retry
- provider timeout: 실패 기록 후 개발자 로그 출력
- budget exceeded: 비싼 모델 호출 차단, 저가 모델 또는 실패로 전환

### Vector DB 오류

- RAG 검색 실패 시 실패 기록 후 run 실패 처리
- embedding 실패 시 실패 기록 후 run 실패 처리

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
- Tailwind CSS, shadcn/ui, Bootstrap 관련 설정 파일과 의존성을 만들지 않습니다.
