# Codex 구현 프롬프트

아래 프롬프트는 Codex에게 실제 구현을 맡길 때 그대로 사용할 수 있습니다.

## 구현 요청

TravelOps AX Agent Studio를 구현해줘.

이 프로젝트는 여행 액티비티/관광 상품 운영 자동화를 위한 멀티에이전트 워크플로우 시스템이야. 사용자가 "이번 달 부산에서 외국인 대상 액티비티 상품을 5개 기획해줘"처럼 요청하면, 시스템은 공공 관광 데이터 조회, 지역/계절성 분석, 상품 아이디어 생성, 상세페이지 카피/FAQ/SNS/검색 키워드 생성, QA/Compliance 검수, Human Approval, 저장까지 실행해야 해.

중요한 제약:

- Tailwind CSS 쓰지 마.
- shadcn/ui 쓰지 마.
- 프론트엔드는 Bootstrap 5와 React-Bootstrap을 사용해.
- Workflow Builder는 React Flow를 사용해.
- Backend는 Python FastAPI를 사용해.
- Agent runtime은 LangGraph를 우선 사용해.
- LLM 호출은 LiteLLM gateway를 통해 감싸고 비용을 기록해.
- TourAPI 실제 키가 없어도 mock provider로 전체 demo가 돌아가야 해.
- 사람 승인 전에는 외부 저장/export tool이 실행되면 안 돼.
- 평가 지표를 최소한 deterministic하게라도 구현해.

## 문서 읽기 순서

먼저 이 폴더의 문서를 읽고 구현해.

1. `00_INDEX.md`
2. `01_PRODUCT_BRIEF.md`
3. `02_USER_STORIES_AND_SCOPE.md`
4. `03_SYSTEM_ARCHITECTURE.md`
5. `04_TECH_STACK_BOOTSTRAP.md`
6. `05_DATA_SOURCES_AND_INGESTION.md`
7. `06_AGENT_WORKFLOW_SPEC.md`
8. `07_BACKEND_API_AND_DB_SPEC.md`
9. `08_FRONTEND_UI_SPEC.md`
10. `09_RAG_GUARDRAILS_EVALUATION.md`
11. `10_COST_BILLING_AND_PAYMENT.md`
12. `11_IMPLEMENTATION_ROADMAP.md`
13. `12_DEPLOYMENT_OPERATIONS_SECURITY.md`

## 우선 구현할 MVP

다음을 end-to-end로 먼저 완성해.

```text
Frontend request form
→ POST /api/workflow-runs
→ Backend creates workflow run
→ LangGraph workflow executes with mock tourism provider
→ Planner/Data/Research/Product/Marketing/QA steps are stored
→ Generated products include sources, FAQ, SNS, QA report
→ Run status becomes awaiting_approval
→ Frontend result review displays products/evidence/QA issues
→ User approves
→ Backend marks run approved
→ Markdown/JSON report is saved
→ Eval smoke command runs and outputs metrics
```

## Backend 구현 상세

폴더 구조:

```text
backend/
  app/
    main.py
    core/
    db/
    schemas/
    api/
    agents/
    tools/
    llm/
    rag/
    evals/
    fixtures/
    tests/
```

필수 API:

- `GET /api/health`
- `GET /api/workflows`
- `POST /api/workflow-runs`
- `GET /api/workflow-runs`
- `GET /api/workflow-runs/{run_id}`
- `GET /api/workflow-runs/{run_id}/steps`
- `GET /api/workflow-runs/{run_id}/tool-calls`
- `GET /api/workflow-runs/{run_id}/result`
- `POST /api/workflow-runs/{run_id}/approval`
- `POST /api/rag/search`
- `POST /api/evals/run`
- `GET /api/costs/summary`

필수 DB 테이블:

- workflow_templates
- workflow_runs
- agent_steps
- tool_calls
- llm_calls
- tourism_items
- source_documents
- generated_products
- approvals
- eval_runs
- eval_results
- usage_costs

필수 provider:

- `MockTourismProvider`
- `TourApiProvider` skeleton
- `CachedTourismProvider` optional

## Frontend 구현 상세

폴더 구조:

```text
frontend/src/
  components/
  pages/
  services/
  styles/
  workflows/
```

필수 화면:

- Dashboard
- Workflow Builder
- Run list
- Run detail
- Result Review
- Evaluation Dashboard
- Cost Dashboard
- Settings

Bootstrap 요구:

- `bootstrap/dist/css/bootstrap.min.css` import
- `react-bootstrap` 컴포넌트 사용
- `@xyflow/react` 사용
- Tailwind config 생성 금지
- shadcn component 생성 금지

## Agent 구현 상세

Agent는 최소 다음을 구현해.

- Planner Agent
- Data Agent
- Research Agent
- Product Agent
- Marketing Agent
- QA/Compliance Agent
- Human Approval Node

처음에는 mock LLM으로 시작해도 돼. 단, 구조는 나중에 LiteLLM real call로 교체 가능해야 해.

각 step은 DB에 저장해야 해.

```json
{
  "agent_name": "ProductAgent",
  "status": "succeeded",
  "input": {},
  "output": {},
  "latency_ms": 1234
}
```

## 평가 구현 상세

최소 지표:

- Retrieval Recall
- Tool Call Accuracy
- Task Success Rate
- Cost per Task
- Latency

가능하면 추가:

- Ragas Faithfulness
- DeepEval task completion

Eval dataset은 JSONL로 만들어.

```text
backend/app/evals/datasets/smoke.jsonl
```

명령:

```bash
python -m app.evals.run_eval --dataset app/evals/datasets/smoke.jsonl --sample-size 3
```

## 비용 구현 상세

모든 LLM 호출은 다음을 기록해야 해.

- provider
- model
- purpose
- input_tokens
- output_tokens
- cost_usd
- latency_ms

Mock LLM일 때도 cost를 0 또는 추정치로 기록해.

Budget guard:

- workflow 1회 비용 한도
- daily/monthly budget
- premium model enabled flag

## 완료 기준

다음이 되면 MVP 완료로 봐.

- 로컬에서 backend/frontend 실행 가능
- UI에서 workflow run 생성 가능
- mock data로 상품 5개 생성 가능
- 각 상품에 source evidence 표시
- QA issue 표시
- 승인/반려 가능
- run cost/latency 표시
- eval smoke 실행 가능
- Tailwind/shadcn 파일 없음
- README에 실행 방법 있음

## 개발 중 판단 기준

구현 범위를 줄여야 한다면 다음은 남겨.

- end-to-end workflow
- source-grounded product output
- QA/compliance
- approval gate
- cost tracking
- eval smoke
- Bootstrap UI

다음은 나중으로 미뤄도 돼.

- 실제 결제
- 실제 Google Sheets 저장
- full auth
- advanced charts
- 대규모 데이터 sync
- P1/P2 기능

