# Codex 구현 프롬프트

아래 프롬프트는 Codex에게 실제 구현을 맡길 때 그대로 사용할 수 있습니다.

## 구현 요청

TravelOps AX Agent Studio를 구현해줘.

이 프로젝트는 여행 액티비티/관광 상품 운영 자동화를 위한 멀티에이전트 워크플로우 시스템이야. 사용자가 "이번 달 부산에서 외국인 대상 액티비티 상품을 5개 기획해줘"처럼 요청하면, 시스템은 공공 관광 데이터 조회, 지역/계절성 분석, 상품 아이디어 생성, 상세페이지 카피/FAQ/SNS/검색 키워드 생성, QA/Compliance 검수, Human Approval, 저장까지 실행해야 해.

중요한 제약:

- Tailwind CSS 쓰지 마.
- shadcn/ui 쓰지 마.
- Bootstrap 쓰지 마.
- 프론트엔드는 Mantine UI와 CSS Modules 또는 SCSS Modules를 사용해.
- Workflow Builder는 React Flow를 사용해.
- Backend는 Python FastAPI를 사용해.
- Agent runtime은 LangGraph를 우선 사용해.
- LLM 호출은 Gemini gateway를 통해 감싸고 비용을 기록해. OpenAI/GPT는 현재 workflow에서 사용하지 마.
- 후속 Poster Studio에서만 OpenAI Image API를 이미지 생성 provider로 사용할 수 있어.
- TourAPI는 실제 한국관광공사 API만 사용해.
- TourAPI 키가 없거나 API 호출이 실패하면 tool_call과 workflow run을 failed로 기록하고 개발자가 터미널/DB 로그에서 원인을 확인할 수 있게 해.
- TourAPI mock, fixture, fallback은 만들지 마.
- Gemini 호출 실패 시 deterministic fallback 하지 마. 실패 run, `agent_steps.error`, `workflow_errors.log`에 기록해.
- 사람 승인 전에는 외부 저장/export tool이 실행되면 안 돼.
- 평가 지표를 최소한 deterministic하게라도 구현해.

## 문서 읽기 순서

먼저 이 폴더의 문서를 읽고 구현해.

1. `00_INDEX.md`
2. `01_PRODUCT_BRIEF.md`
3. `02_USER_STORIES_AND_SCOPE.md`
4. `03_SYSTEM_ARCHITECTURE.md`
5. `04_TECH_STACK_MANTINE.md`
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
→ LangGraph workflow executes with real TourAPI provider
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
- `GET /api/workflow-runs/{run_id}/llm-calls`
- `GET /api/workflow-runs/{run_id}/approvals`
- `GET /api/workflow-runs/{run_id}/result`
- `POST /api/workflow-runs/{run_id}/approve`
- `POST /api/workflow-runs/{run_id}/reject`
- `POST /api/workflow-runs/{run_id}/request-changes`
- `POST /api/workflow-runs/{run_id}/revisions`
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

- `TourApiProvider`

Revision 정책:

- 기존 run의 `final_output`을 직접 수정하지 마.
- 모든 revision은 새 workflow run으로 생성해.
- revision run은 항상 최상위 원본 run을 `parent_run_id`로 가져야 해.
- revision에서 다시 revision을 만들 때도 중간 revision이 parent가 되면 안 돼. 같은 원본 run 아래에서 `revision_number`만 증가해야 해.
- `manual_save`: 운영자가 수정한 products/marketing_assets를 저장하고 QA는 다시 실행하지 마.
- `manual_edit`: 운영자가 수정한 products/marketing_assets를 저장하고 QA/Compliance만 다시 실행해.
- `qa_only`: 기존 결과를 유지하고 QA/Compliance만 다시 실행해.
- `llm_partial_rewrite`: 선택된 QA issue와 requested changes에 필요한 필드만 AI가 patch해. Product/Marketing 전체를 다시 생성하지 마.
- revision 실행 전 `qa_settings`를 받을 수 있게 해. 기본값은 create run의 region/period/target/preferences/avoid/output_language야.
- QA 메시지에는 `disclaimer`, `not_to_claim`, `sales_copy` 같은 내부 필드명을 그대로 노출하지 말고 사용자 친화적 라벨로 바꿔.
- `확인 필요`, `변동될 수 있음`, `운영자가 최종 확정해야 함` 같은 완화 문구는 단정 표현 위반으로 보지 마.

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

Mantine UI 요구:

- `@mantine/core`, `@mantine/hooks`, `@mantine/form`, `@mantine/notifications` 사용
- 앱 루트를 `MantineProvider`와 `Notifications`로 감싸기
- 운영툴 UI는 Mantine `AppShell`, `Table`, `Tabs`, `Modal`, `Drawer`, `Notification`, `Badge`, `Button`, `Form` 계열 컴포넌트 중심으로 구현
- 제품 고유 레이아웃은 CSS Modules 또는 SCSS Modules로 구현
- `@xyflow/react` 사용
- Tailwind config 생성 금지
- shadcn component 생성 금지
- Bootstrap dependency와 class 사용 금지

## Agent 구현 상세

Agent는 최소 다음을 구현해.

- Planner Agent
- Data Agent
- Research Agent
- Product Agent
- Marketing Agent
- QA/Compliance Agent
- Human Approval Node

처음에는 rule-based 생성으로 시작해도 돼. 단, 구조는 Gemini real call로 교체 가능해야 해.

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

Rule-based 생성일 때도 cost를 0 또는 추정치로 기록해.

Budget guard:

- workflow 1회 비용 한도
- daily/monthly budget
- premium model enabled flag

## 완료 기준

다음이 되면 MVP 완료로 봐.

- 로컬에서 backend/frontend 실행 가능
- UI에서 workflow run 생성 가능
- 실제 TourAPI 데이터로 상품 생성 가능
- 각 상품에 source evidence 표시
- QA issue 표시
- 승인/반려 가능
- run cost/latency 표시
- eval smoke 실행 가능
- Tailwind/shadcn/Bootstrap 파일 없음
- README에 실행 방법 있음

## 후속 Poster Studio 구현 기준

MVP가 끝난 뒤 Poster Studio를 구현할 때는 다음 흐름을 따라.

```text
Run Review product 선택
→ Poster Context Builder가 run/product/marketing/QA context 추출
→ Poster Prompt Agent가 문구와 디자인 옵션 후보 생성
→ 사용자가 추천 문구와 옵션을 삭제/수정/추가
→ 최종 prompt preview 확인
→ OpenAI Image API로 poster image 생성
→ Poster QA/Review
→ 승인된 poster만 export
```

필수 컴포넌트:

- Poster Prompt Agent
- Poster Image Agent
- Poster QA/Review
- Poster Studio UI
- poster asset DB table
- poster image call cost log
- OpenAIImageGateway

기본 이미지 모델 후보:

- `gpt-image-2`

주의:

- 모델명, 가격, 파라미터는 구현 직전에 OpenAI 공식 문서로 다시 확인해.
- 이미지 생성은 사용자가 prompt와 옵션을 확인한 뒤에만 실행해.
- 포스터 안 텍스트는 사람이 최종 검수하게 해.
- 가격, 예약 가능 여부, 운영 일정 단정 표현을 prompt에서 제한해.
- TourAPI 이미지를 참고하거나 재사용할 때 license note를 확인해.
- 생성 poster는 기본 `needs_review` 상태로 저장해.
- 외부 게시/export는 승인 뒤에만 허용해.

## 개발 중 판단 기준

구현 범위를 줄여야 한다면 다음은 남겨.

- end-to-end workflow
- source-grounded product output
- QA/compliance
- approval gate
- revision workflow
- selected QA issue 기반 AI patch
- cost tracking
- eval smoke
- Mantine UI

다음은 나중으로 미뤄도 돼.

- 실제 결제
- 실제 Google Sheets 저장
- full auth
- advanced charts
- 대규모 데이터 sync
- Poster Studio
- P1/P2 기능
