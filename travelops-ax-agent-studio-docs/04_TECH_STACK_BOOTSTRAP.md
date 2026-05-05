# 기술스택 명세

## 최종 확정 스택

### Backend

- Python 3.11 이상
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- Alembic
- SQLite for MVP
- PostgreSQL for production-ready mode
- Redis optional
- httpx for external API calls
- pytest
- ruff/black/mypy optional

### Agent / Workflow

- LangGraph 우선 사용
- OpenAI Agents SDK는 대체 구현 또는 비교 구현으로 문서화
- LiteLLM for LLM gateway
- Guardrails는 다음 방식으로 구현
  - Pydantic schema validation
  - deterministic rule checks
  - LLM judge checks
  - pre-call budget guard
  - post-call compliance guard

### RAG / Vector DB

MVP 권장:

- Chroma

이유:

- 로컬 시작이 쉽습니다.
- 개인 프로젝트에서 Docker 없이도 빠르게 붙일 수 있습니다.
- 문서, metadata, embedding 저장과 검색을 간단히 구현할 수 있습니다.

P1 또는 production-like 옵션:

- Qdrant

이유:

- Docker 기반 로컬 실행이 쉽습니다.
- payload filter와 payload index를 사용해 지역, content type, 날짜, source 같은 필터 검색을 최적화할 수 있습니다.

### Frontend

- React 또는 Next.js
- TypeScript
- React Flow (`@xyflow/react`)
- Bootstrap 5
- React-Bootstrap
- Bootstrap Icons 또는 lucide-react
- TanStack Query optional
- Zustand optional

중요:

- Tailwind CSS 사용 금지
- shadcn/ui 사용 금지
- Radix 기반 shadcn 컴포넌트 scaffold 금지

### Evaluation

- pytest
- Ragas
- DeepEval
- 자체 평가 스크립트
- JSONL evaluation dataset
- Markdown/JSON/CSV report output

### Deployment

- Docker
- Docker Compose
- Backend: Render/Railway/Fly.io 중 하나
- Frontend: Vercel 또는 same container
- DB: SQLite MVP, PostgreSQL managed DB optional
- Vector DB: Chroma local/persistent, Qdrant container optional

## Bootstrap 프론트엔드 규칙

### 설치 패키지

React 기반으로 개발할 경우:

```bash
npm install bootstrap react-bootstrap @xyflow/react bootstrap-icons
```

Next.js 기반으로 개발할 경우도 동일합니다.

`src/main.tsx` 또는 Next.js root layout에서 Bootstrap CSS를 import합니다.

```tsx
import "bootstrap/dist/css/bootstrap.min.css";
import "bootstrap-icons/font/bootstrap-icons.css";
import "./styles/app.scss";
```

Bootstrap JS가 필요한 dropdown/modal/toast를 React-Bootstrap으로 구현하면 별도 Bootstrap JS import를 최소화할 수 있습니다.

### 사용 컴포넌트

React-Bootstrap 권장 컴포넌트:

- `Container`
- `Row`
- `Col`
- `Navbar`
- `Nav`
- `Button`
- `ButtonGroup`
- `Card`
- `Badge`
- `Alert`
- `Tabs`
- `Tab`
- `Table`
- `Form`
- `InputGroup`
- `Modal`
- `Offcanvas`
- `Toast`
- `Dropdown`
- `ProgressBar`
- `Spinner`

단, 운영툴 UI에서는 장식적인 Card 남용을 피합니다. Card는 반복 아이템, 결과 패널, modal 내부 요약 정도에 제한합니다.

### 스타일 파일 구조

```text
frontend/src/styles/
  app.scss
  _variables.scss
  _layout.scss
  _workflow-builder.scss
  _run-console.scss
  _result-review.scss
  _evaluation.scss
```

### Bootstrap theme customization

`_variables.scss` 예시:

```scss
$primary: #1f6feb;
$success: #2da44e;
$warning: #bf8700;
$danger: #cf222e;
$body-bg: #f6f8fa;
$body-color: #24292f;
$border-radius: 0.375rem;
$border-radius-lg: 0.5rem;
```

주의:

- 한 가지 색상 계열만 지배하는 팔레트를 피합니다.
- 보라/남색 gradient 중심 UI를 피합니다.
- 운영툴답게 밀도 있고 스캔하기 쉬운 UI를 만듭니다.
- hero/landing page를 만들지 않습니다. 첫 화면은 실제 workflow dashboard입니다.

### Tailwind/shadcn 금지 사항

다음 파일이나 패키지는 만들거나 설치하지 않습니다.

- `tailwind.config.js`
- `tailwind.config.ts`
- `postcss.config.js`에 tailwind plugin
- `@tailwind base`
- `@tailwind components`
- `@tailwind utilities`
- `tailwindcss`
- `shadcn-ui`
- `components.json` for shadcn
- `class-variance-authority`를 shadcn 목적으로 추가

Bootstrap utility class는 사용 가능합니다.

예:

```tsx
<div className="d-flex align-items-center gap-2">
  <Badge bg="success">approved</Badge>
  <Button variant="primary" size="sm">Run</Button>
</div>
```

## Backend 상세 스택

### FastAPI

역할:

- workflow 실행 요청
- agent run 상태 조회
- data source 조회
- approval 처리
- eval 실행
- 비용/사용량 리포트 제공

권장 구조:

```python
app = FastAPI(title="TravelOps AX Agent Studio")
app.include_router(workflows.router, prefix="/api/workflows", tags=["workflows"])
app.include_router(runs.router, prefix="/api/workflow-runs", tags=["workflow-runs"])
app.include_router(approvals.router, prefix="/api/approvals", tags=["approvals"])
app.include_router(evals.router, prefix="/api/evals", tags=["evals"])
```

### SQLAlchemy

핵심 테이블:

- users
- workflow_templates
- workflow_runs
- agent_steps
- tool_calls
- llm_calls
- source_documents
- tourism_items
- generated_products
- approvals
- eval_runs
- eval_results
- usage_costs

### SQLite/PostgreSQL

MVP는 SQLite로 충분합니다.

권장:

- local: `sqlite:///./data/travelops.db`
- production-like: PostgreSQL

SQLAlchemy URL만 바꾸면 동작하도록 구현합니다.

### Redis optional

MVP에서는 FastAPI background task로 시작해도 됩니다.

P1에서 Redis를 추가하는 경우:

- workflow 실행 queue
- API response cache
- rate limit counter
- websocket pub/sub

## Agent 스택 상세

### LangGraph

LangGraph는 workflow와 agent의 차이를 보여주기 좋습니다.

- workflow: 정해진 코드 경로를 따르는 구조
- agent: 도구 사용과 다음 행동을 동적으로 결정하는 구조

이 프로젝트에서는 두 방식을 결합합니다.

정해진 workflow path:

```text
Planner → Data → Research → Product → Marketing → QA → Human Approval → Save
```

동적 agent behavior:

- Planner가 필요한 tool call을 선택합니다.
- Data Agent가 지역/키워드/행사/숙박 도구 중 필요한 것을 고릅니다.
- QA Agent가 검수 이슈에 따라 재작성 요청 여부를 결정합니다.

### OpenAI Agents SDK 대체 옵션

OpenAI Agents SDK는 다음 primitive를 제공합니다.

- Agent
- tools
- handoffs
- guardrails
- tracing
- sessions

대체 구현을 만들 경우:

- Planner Agent가 Data/Product/QA Agent로 handoff
- tool call은 function tool로 구현
- tracing을 통해 agent run을 관찰
- SQLite/Redis session으로 대화 상태 유지

하지만 MVP 기본 구현은 LangGraph로 고정합니다.

## LLM 모델 정책

### 모델 계층

`cheap`: 분류, 정규화, 간단 요약

- Gemini Flash-Lite 또는 저가 OpenAI mini/nano 계열

`standard`: 상품 기획, 카피 생성

- Gemini Flash, GPT mini급, Claude Haiku/Sonnet 소량

`premium`: 최종 품질 생성, 복잡한 검수

- Claude Sonnet 또는 GPT 계열

### 호출 정책

- Planner: cheap 또는 standard
- Data normalization: cheap
- Research synthesis: standard
- Product generation: standard
- Marketing copy: standard
- QA compliance: cheap deterministic + standard LLM judge
- Eval judge: cheap/standard, batch 가능하면 batch

## Embedding 정책

MVP 우선순위:

1. 로컬 sentence-transformers CPU embedding
2. 저가 embedding API
3. provider별 embedding 모델

저장 metadata:

- `source`
- `content_id`
- `content_type`
- `region_code`
- `sigungu_code`
- `event_start_date`
- `event_end_date`
- `language`
- `license_type`
- `created_at`

## 평가 스택 상세

### pytest

일반 deterministic test:

- API schema
- DB model
- tool provider mock
- prompt output parser
- cost calculation
- approval gate

### Ragas

RAG/agent metric:

- context recall
- faithfulness
- response relevancy
- tool call accuracy
- agent goal accuracy

### DeepEval

end-to-end/component eval:

- workflow task completion
- answer relevancy
- hallucination/custom GEval
- component tracing

### 자체 평가

반드시 직접 계산할 지표:

- cost per task
- latency
- tool call success rate
- human revision rate
- approval pass rate

## 패키지 예시

### backend/pyproject.toml 핵심 dependencies

```toml
[project]
dependencies = [
  "fastapi",
  "uvicorn[standard]",
  "pydantic",
  "pydantic-settings",
  "sqlalchemy",
  "alembic",
  "httpx",
  "langgraph",
  "langchain-core",
  "litellm",
  "chromadb",
  "pytest",
  "pytest-asyncio",
  "ragas",
  "deepeval"
]
```

Qdrant를 선택하면:

```toml
"qdrant-client"
```

### frontend/package.json 핵심 dependencies

```json
{
  "dependencies": {
    "@xyflow/react": "^12",
    "bootstrap": "^5",
    "bootstrap-icons": "^1",
    "react-bootstrap": "^2",
    "react": "^19",
    "react-dom": "^19"
  }
}
```

React 버전은 실제 scaffold 시점의 안정 버전에 맞춥니다.

## 품질 기준

- 모든 API 응답은 Pydantic schema로 정의합니다.
- 모든 LLM 출력은 가능하면 structured output 또는 JSON schema validation을 거칩니다.
- tool call은 DB에 저장합니다.
- workflow run마다 cost와 latency를 집계합니다.
- Bootstrap class와 SCSS를 사용하되, 인라인 style 남용을 피합니다.
- 사용자에게 보이는 상태명은 일관되게 표시합니다.

