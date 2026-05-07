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
- Gemini gateway for LLM calls
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
- Mantine UI
- CSS Modules 또는 SCSS Modules
- React Flow (`@xyflow/react`)
- Tabler Icons 또는 lucide-react
- Recharts optional
- TanStack Query optional
- Zustand optional

중요:

- Tailwind CSS 사용 금지
- shadcn/ui 사용 금지
- Bootstrap 사용 금지
- Bootstrap 기반 class, layout, component library 사용 금지

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

## Mantine 프론트엔드 규칙

### 설치 패키지

React 또는 Next.js 기반으로 개발할 경우:

```bash
npm install @mantine/core @mantine/hooks @mantine/form @mantine/notifications @mantine/dates @tabler/icons-react @xyflow/react
```

차트가 필요하면:

```bash
npm install @mantine/charts recharts
```

Mantine 기본 스타일은 앱 루트에서 import합니다.

```tsx
import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "@mantine/dates/styles.css";
import "@xyflow/react/dist/style.css";
import "./styles/app.css";
```

앱 루트는 `MantineProvider`와 `Notifications`로 감쌉니다.

```tsx
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { theme } from "./theme";

export function Root() {
  return (
    <MantineProvider theme={theme} defaultColorScheme="light">
      <Notifications position="top-right" />
      <App />
    </MantineProvider>
  );
}
```

### 핵심 Mantine 컴포넌트

운영툴 UI는 Mantine의 다음 컴포넌트를 중심으로 구성합니다.

- `AppShell`
- `Table`
- `Tabs`
- `Modal`
- `Drawer`
- `Notification` / `Notifications`
- `Badge`
- `Button`
- `ActionIcon`
- `Menu`
- `Group`
- `Stack`
- `Grid`
- `SimpleGrid`
- `Card`
- `Paper`
- `ScrollArea`
- `Divider`
- `Text`
- `Title`
- `Tooltip`
- `Progress`
- `RingProgress`
- `Timeline`
- `Alert`
- `Loader`
- `Skeleton`
- `TextInput`
- `Textarea`
- `NumberInput`
- `Select`
- `MultiSelect`
- `DateInput` 또는 `DatePickerInput`
- `Checkbox`
- `Switch`
- `SegmentedControl`

`Card`와 `Paper`는 반복 item, 결과 패널, inspector, modal 내부 요약에만 제한적으로 사용합니다. 페이지 전체를 카드 묶음처럼 만들지 않습니다.

### 스타일 파일 구조

CSS Modules 또는 SCSS Modules를 사용합니다.

```text
frontend/src/
  theme.ts
  styles/
    app.css
  components/
    AppShellLayout/
      AppShellLayout.tsx
      AppShellLayout.module.css
    WorkflowCanvas/
      WorkflowCanvas.tsx
      WorkflowCanvas.module.css
    ResultReview/
      ResultReview.tsx
      ResultReview.module.css
```

SCSS Modules를 선택하면:

```text
AppShellLayout.module.scss
WorkflowCanvas.module.scss
ResultReview.module.scss
```

### Mantine theme customization

`theme.ts` 예시:

```tsx
import { createTheme, rem } from "@mantine/core";

export const theme = createTheme({
  primaryColor: "indigo",
  fontFamily:
    "Inter, Pretendard, system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
  headings: {
    fontFamily:
      "Inter, Pretendard, system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
    fontWeight: "650",
  },
  radius: {
    xs: rem(3),
    sm: rem(5),
    md: rem(7),
    lg: rem(8),
    xl: rem(10),
  },
  defaultRadius: "md",
  colors: {
    opsBlue: [
      "#edf4ff",
      "#dce9fb",
      "#b8d0f3",
      "#91b5ec",
      "#709fe5",
      "#5b90e2",
      "#4f87e1",
      "#4076c8",
      "#3569b3",
      "#285a9f",
    ],
  },
});
```

주의:

- Mantine 기본 theme를 그대로 쓰지 말고 운영툴에 맞게 spacing, radius, color, font weight를 조정합니다.
- 한 가지 색상 계열만 지배하는 팔레트를 피합니다.
- 보라/남색 gradient 중심 UI를 피합니다.
- SaaS 운영툴답게 밀도 있고 스캔하기 쉬운 UI를 만듭니다.
- hero/landing page를 만들지 않습니다. 첫 화면은 실제 workflow dashboard입니다.

### CSS Modules 사용 원칙

Mantine props만으로 충분한 레이아웃은 Mantine props를 사용합니다.

```tsx
<Group justify="space-between" align="center" gap="sm">
  <Badge color="green" variant="light">approved</Badge>
  <Button size="xs">Run</Button>
</Group>
```

반복되는 화면 구조, React Flow canvas, run console, result review처럼 제품 고유의 레이아웃은 CSS Modules로 작성합니다.

```css
.canvasShell {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr) 340px;
  height: calc(100dvh - var(--app-shell-header-height));
  min-height: 640px;
}

.canvas {
  min-width: 0;
  border-left: 1px solid var(--mantine-color-gray-3);
  border-right: 1px solid var(--mantine-color-gray-3);
}
```

### Tailwind/shadcn/Bootstrap 금지 사항

다음 파일이나 패키지는 만들거나 설치하지 않습니다.

- `tailwind.config.js`
- `tailwind.config.ts`
- Tailwind용 `postcss.config.js`
- `@tailwind base`
- `@tailwind components`
- `@tailwind utilities`
- `tailwindcss`
- `shadcn-ui`
- shadcn용 `components.json`
- shadcn 목적으로 쓰는 `class-variance-authority`
- `bootstrap`
- `react-bootstrap`
- `bootstrap-icons`

다음 스타일 방식도 피합니다.

- Tailwind utility class 기반 layout
- Bootstrap class 기반 layout
- shadcn scaffold component 복붙
- 아무 theme 조정 없이 Mantine default만 쓰는 화면

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
app = FastAPI(title="PARAVOCA AX Agent Studio")
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

- local: `sqlite:///./data/paravoca.db`
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

- Gemini 2.5 Flash-Lite

`standard`: 상품 기획, 카피 생성

- Gemini 2.5 Flash-Lite 우선, 필요 시 Gemini Flash 계열 검토

`premium`: 최종 품질 생성, 복잡한 검수

- GPT 계열

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
- TourAPI provider integration
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
    "@mantine/core": "^7",
    "@mantine/hooks": "^7",
    "@mantine/form": "^7",
    "@mantine/notifications": "^7",
    "@mantine/dates": "^7",
    "@tabler/icons-react": "^3",
    "@xyflow/react": "^12",
    "react": "^19",
    "react-dom": "^19"
  }
}
```

React와 Mantine의 실제 major version은 scaffold 시점의 안정 버전에 맞춥니다.

## 품질 기준

- 모든 API 응답은 Pydantic schema로 정의합니다.
- 모든 LLM 출력은 가능하면 structured output 또는 JSON schema validation을 거칩니다.
- tool call은 DB에 저장합니다.
- workflow run마다 cost와 latency를 집계합니다.
- Mantine component props, theme, CSS Modules를 함께 사용합니다.
- 사용자에게 보이는 상태명은 일관되게 표시합니다.
- Tailwind/shadcn/Bootstrap 의존성이 없어야 합니다.
