# Frontend UI 명세

## 프론트엔드 목표

TravelOps AX Agent Studio의 프론트엔드는 마케팅 사이트가 아니라 운영툴입니다. 첫 화면부터 실제 workflow 실행, 결과 검토, 평가 지표 확인이 가능해야 합니다.

핵심 화면:

1. Dashboard
2. Workflow Builder
3. Run Console
4. Result Review
5. Data Sources
6. Evaluation Dashboard
7. Cost/Billing Dashboard
8. Settings

## 기술 제약

반드시 사용:

- React 또는 Next.js
- TypeScript
- Bootstrap 5
- React-Bootstrap
- React Flow

사용 금지:

- Tailwind CSS
- shadcn/ui
- shadcn `components.json`
- Tailwind utility 기반 디자인 시스템

## UI 톤

SaaS 운영 도구처럼 조용하고 밀도 있게 만듭니다.

권장:

- 좌측 sidebar navigation
- 상단 compact toolbar
- 표, 탭, 배지, 상태 컬럼
- 결과 preview와 source evidence를 나란히 배치
- workflow canvas는 넓게
- 버튼은 명확한 command 중심

피해야 할 것:

- landing page hero
- 큰 gradient 배경
- 장식용 카드 남발
- 과도한 둥근 모서리
- 한 가지 색상만 지배하는 UI
- 기능 설명 문구를 화면에 길게 노출

## 라우팅 구조

Next.js 예시:

```text
/                         Dashboard
/workflows                Workflow template list
/workflows/:id            Workflow Builder
/runs                     Workflow run list
/runs/:id                 Run Console + Result Review
/data-sources             Tourism data search/cache
/evals                    Evaluation Dashboard
/evals/:id                Eval Report
/costs                    Cost Dashboard
/settings                 API keys/model policy/settings
```

React Router를 쓰는 경우도 동일 path를 사용합니다.

## 공통 레이아웃

### AppShell

구성:

- Sidebar
- Topbar
- Main content
- Toast container

Bootstrap 구조:

```tsx
<div className="app-shell">
  <Sidebar />
  <main className="app-main">
    <Topbar />
    <Container fluid className="py-3">
      <Outlet />
    </Container>
  </main>
</div>
```

### Sidebar 메뉴

- Dashboard
- Workflows
- Runs
- Data Sources
- Evaluations
- Costs
- Settings

아이콘:

- Bootstrap Icons 또는 lucide-react 사용
- 텍스트만 있는 큰 버튼 형태 지양

### 상태 배지

Workflow status 색상:

| status | Bootstrap variant |
|---|---|
| pending | secondary |
| running | primary |
| awaiting_approval | warning |
| approved | success |
| rejected | danger |
| failed | danger |
| cancelled | secondary |

## Dashboard

목적:

- 최근 workflow run
- 승인 대기
- 실패 run
- 이번 달 비용
- 평균 latency
- 평가 통과율

구성:

- 상단 KPI row
- 승인 대기 table
- 최근 실행 table
- 비용 trend compact chart optional

KPI:

- Runs today
- Awaiting approval
- Avg cost per task
- Avg latency
- Eval pass rate

## Workflow Builder

React Flow 기반 canvas입니다.

### 좌측 팔레트

노드 타입:

- User Input
- Data Collection
- RAG Search
- Research Analysis
- Product Planning
- Marketing Copy
- QA Review
- Human Approval
- Save Result

각 노드는 icon + 짧은 name으로 표시합니다.

### 중앙 canvas

기능:

- drag nodes
- connect edges
- delete node/edge
- zoom/pan
- fit view
- save template
- run template

### 우측 inspector

선택한 node의 config를 편집합니다.

예: Data Collection node

- provider: mock/tourapi/cached
- region source: user_input.region
- include events: checkbox
- include stays: checkbox
- max results: number

예: QA Review node

- block high severity: checkbox
- check prohibited phrases: checkbox
- require sources: checkbox
- judge model tier: select

### Top toolbar

버튼:

- Save
- Run
- Validate
- Fit view
- Export JSON

아이콘 사용:

- save icon
- play icon
- check icon
- maximize icon
- download icon

### Node 상태 표시

실행 중 run을 열면 node별 상태를 표시합니다.

- queued: grey border
- running: blue border + spinner
- succeeded: green check
- failed: red alert
- waiting_for_human: yellow pause

## Run Console

목적:

- workflow 실행 상태를 실시간 또는 polling으로 보여줍니다.

구성:

- run summary header
- step timeline
- tool call table
- LLM call/cost table
- raw event log collapsible

### Run summary

필드:

- Run ID
- status
- created at
- elapsed time
- total cost
- model policy
- provider mode

### Step timeline

각 step row:

- agent name
- status badge
- latency
- model
- prompt version
- output summary

### Tool call table

컬럼:

- time
- tool
- status
- arguments summary
- response count
- latency
- error

## Result Review

목적:

- 생성된 상품 기획 결과를 사람이 검토하고 승인/반려합니다.

구성:

- 좌측 product list
- 중앙 product detail
- 우측 evidence/QA panel
- 하단 approval actions

### Product list

각 item:

- title
- target
- QA status badge
- source count
- revision status

### Product detail tabs

Tabs:

- Overview
- Itinerary
- Sales Copy
- FAQ
- SNS
- Keywords
- JSON

### Evidence panel

선택 상품의 source_ids를 보여줍니다.

필드:

- source title
- source type
- content_id
- snippet
- API/source link
- license note

### QA panel

이슈 목록:

- severity badge
- type
- message
- field path
- suggested fix

High severity가 있으면 approval button 옆에 warning을 표시합니다.

### Approval actions

버튼:

- Approve
- Request changes
- Reject
- Export draft

승인 modal:

- comment textarea
- high risk override checkbox
- final confirm

## Data Sources 화면

목적:

- 수집된 관광 데이터를 검색하고 RAG 색인 상태를 확인합니다.

구성:

- 검색 필터
- 관광 item table
- detail drawer
- sync button
- embedding status

필터:

- region
- content type
- source
- has image
- event date range
- embedding status

## Evaluation Dashboard

목적:

- 평가 실행과 결과 확인

구성:

- Run eval button
- dataset selector
- model policy selector
- metrics summary
- case result table
- failures panel

Metrics:

- Retrieval Recall
- Faithfulness
- Tool Call Accuracy
- Task Success Rate
- Cost per Task
- Latency
- Human Revision Rate

Case table columns:

- case id
- input summary
- passed
- retrieval recall
- faithfulness
- tool accuracy
- cost
- latency
- failure reason

## Cost Dashboard

목적:

- 월 3만 원 내외 운영 가능성을 보여줍니다.

구성:

- monthly total
- cost by provider
- cost by model
- cost by workflow step
- cost per task distribution
- budget alerts

Budget alert examples:

- daily budget 80% reached
- premium model calls exceeded threshold
- eval batch cost higher than expected

## Settings

섹션:

- API Keys status
- Tourism provider mode
- Model policy
- Budget limits
- Evaluation settings
- Export integrations

API key는 값을 보여주지 않습니다. 존재 여부만 표시합니다.

```text
OPENAI_API_KEY: configured
ANTHROPIC_API_KEY: missing
GEMINI_API_KEY: configured
TOURAPI_SERVICE_KEY: configured
```

## API client

Frontend service 구조:

```text
frontend/src/services/
  apiClient.ts
  workflowsApi.ts
  runsApi.ts
  approvalsApi.ts
  evalsApi.ts
  costsApi.ts
```

`apiClient.ts`:

```ts
export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${import.meta.env.VITE_API_BASE_URL}${path}`);
  if (!res.ok) throw new Error(`API error ${res.status}`);
  const body = await res.json();
  return body.data as T;
}
```

## 상태 관리

MVP:

- TanStack Query 또는 단순 hooks
- Workflow Builder canvas state는 component state 또는 Zustand

권장:

- server state: TanStack Query
- canvas state: Zustand

## 반응형 기준

Desktop 우선 운영툴입니다.

- 1280px 이상: sidebar + main + inspector 3컬럼
- 768~1279px: inspector는 Offcanvas
- 767px 이하: workflow builder는 read/edit 제한, list/review 중심

텍스트가 버튼/배지 내부에서 잘리지 않게 합니다. 긴 run id는 truncate + tooltip 처리합니다.

## 접근성

- 버튼에는 accessible label
- icon-only button에는 tooltip과 `aria-label`
- 상태 색상만으로 의미 전달 금지, badge text 포함
- modal focus trap은 React-Bootstrap 기본 기능 사용

## 주요 컴포넌트 목록

```text
components/
  AppShell.tsx
  Sidebar.tsx
  Topbar.tsx
  StatusBadge.tsx
  CostBadge.tsx
  WorkflowCanvas.tsx
  NodePalette.tsx
  NodeInspector.tsx
  RunTimeline.tsx
  ToolCallTable.tsx
  ProductReviewPanel.tsx
  EvidencePanel.tsx
  QAReportPanel.tsx
  ApprovalModal.tsx
  EvalMetricsGrid.tsx
  CostSummaryChart.tsx
```

## 디자인 acceptance 기준

- 첫 화면이 실제 dashboard여야 합니다.
- Tailwind/shadcn 관련 파일이 없어야 합니다.
- Workflow Builder에서 최소 8개 노드를 배치할 수 있어야 합니다.
- Result Review에서 source evidence와 QA issue가 한 화면에서 확인 가능해야 합니다.
- 승인/반려 액션이 명확해야 합니다.
- 실행 중 상태가 polling으로 갱신되어야 합니다.

