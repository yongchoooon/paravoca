# 구현 로드맵

## 구현 원칙

Codex는 아래 순서대로 구현합니다. 핵심은 "작동하는 얇은 end-to-end slice"를 먼저 만든 뒤, 데이터/에이전트/평가/UI를 점진적으로 강화하는 것입니다.

첫 번째 목표:

```text
사용자 요청 입력
→ mock 데이터 조회
→ agent workflow 실행
→ 상품 3개 생성
→ QA 검수
→ 승인 대기
→ 승인
→ 결과 report 저장
```

## Phase 0: 프로젝트 scaffold

목표:

- backend/frontend 기본 구조 생성
- Docker Compose 준비
- Bootstrap 기반 UI scaffold

작업:

- `backend/` FastAPI 프로젝트 생성
- `frontend/` React/Next.js 프로젝트 생성
- Tailwind/shadcn 없이 Bootstrap 설치
- `.env.example` 작성
- `docker-compose.yml` 작성
- README 실행 방법 작성

완료 기준:

- Backend `GET /api/health` 동작
- Frontend dashboard 렌더링
- Bootstrap style 적용
- Tailwind 관련 파일 없음

## Phase 1: DB와 API 기본

목표:

- workflow template/run/step/tool call 저장 구조 구현

작업:

- SQLAlchemy 모델 작성
- SQLite 연결
- Alembic optional
- workflow template seed
- workflow run CRUD API
- step/tool call 조회 API

완료 기준:

- `POST /api/workflow-runs`가 run을 생성
- `GET /api/workflow-runs/{id}`가 상태 반환
- DB 파일 생성
- unit test 통과

## Phase 2: 관광 데이터 provider

목표:

- TourAPI interface와 mock provider 구현

작업:

- `TourismDataProvider` protocol 작성
- mock fixture 작성
- TourAPI 실제 client skeleton 작성
- data normalization
- tool logging decorator
- tourism search API

완료 기준:

- mock provider로 부산 관광지/행사/숙박 데이터 반환
- tool call log 저장
- 실제 API 키가 없어도 테스트 통과

## Phase 3: RAG 최소 구현

목표:

- source document 생성과 vector search 구현

작업:

- SourceDocument model
- Chroma client
- embedding wrapper
- fixture ingest command
- vector search API
- keyword fallback

완료 기준:

- 부산 fixture가 vector DB에 색인됨
- `POST /api/rag/search`가 top_k 결과 반환
- metadata filter 적용

## Phase 4: LangGraph workflow

목표:

- Planner/Data/Research/Product/Marketing/QA node가 연결된 workflow 실행

작업:

- GraphState 정의
- Planner Agent 구현
- Data Agent 구현
- Research Agent 구현
- Product Agent 구현
- Marketing Agent 구현
- QA Agent 구현
- Human Approval stop 구현

완료 기준:

- mock input으로 end-to-end workflow 실행
- run status가 `awaiting_approval`로 멈춤
- final draft output 생성
- agent_steps, tool_calls, llm_calls 저장

## Phase 5: LLM gateway와 비용 추적

목표:

- LiteLLM 기반 모델 호출과 비용 기록

작업:

- LLMGateway 구현
- model policy config
- cost tracker
- budget guard
- schema validation retry
- fallback policy

완료 기준:

- 모든 LLM 호출이 `llm_calls`에 저장
- run total cost 계산
- budget 초과 시 차단
- mock LLM mode 지원

## Phase 6: Frontend workflow/run UI

목표:

- 운영자가 workflow를 실행하고 상태를 볼 수 있는 UI 구현

작업:

- AppShell
- Dashboard
- Workflow Builder 기본 canvas
- Run list
- Run detail
- Run timeline
- Tool call table
- Result Review
- Approval modal

완료 기준:

- UI에서 workflow 실행 가능
- 2초 polling으로 상태 갱신
- 상품 결과와 QA 이슈 표시
- 승인/반려 가능

## Phase 7: 평가 파이프라인

목표:

- 프로젝트 차별점인 evaluation 자동화 구현

작업:

- eval dataset JSONL
- eval runner
- retrieval recall
- tool call accuracy
- task success
- cost per task
- latency
- Ragas faithfulness optional
- DeepEval smoke optional
- eval report 생성

완료 기준:

- `python -m app.evals.run_eval --sample-size 3` 실행
- Markdown/JSON report 생성
- Eval dashboard에서 결과 조회

## Phase 8: 배포와 polish

목표:

- 데모 가능 상태

작업:

- Dockerfile 정리
- Docker Compose로 backend/frontend/db/vector 실행
- README 업데이트
- sample video script 작성
- seed data command
- 오류/empty/loading 상태 UI 정리

완료 기준:

- 새 환경에서 README만 보고 실행 가능
- mock mode demo 완주 가능
- 실제 TourAPI 키가 있으면 real mode 전환 가능

## Codex 작업 단위

### Task 1

프로젝트 scaffold와 health check.

산출물:

- backend FastAPI
- frontend Bootstrap dashboard
- docker compose

### Task 2

DB schema와 workflow run API.

산출물:

- SQLAlchemy models
- run create/list/detail
- tests

### Task 3

TourAPI provider와 mock fixtures.

산출물:

- provider interface
- mock provider
- data tools
- tool call logs

### Task 4

LangGraph workflow skeleton.

산출물:

- graph state
- dummy agents
- run execution
- approval stop

### Task 5

LLM gateway와 real prompt outputs.

산출물:

- LiteLLM wrapper
- prompt files
- structured output parsing
- cost tracking

### Task 6

Frontend workflow run UI.

산출물:

- run form
- run timeline
- result review
- approval modal

### Task 7

RAG와 evaluation.

산출물:

- Chroma ingest/search
- eval dataset
- metrics
- report

## 작업 우선순위 판단 기준

무조건 먼저:

- end-to-end run
- result with sources
- approval gate
- cost logs
- eval smoke

나중:

- 예쁜 chart
- 인증
- 실제 결제
- 복잡한 권한
- 대규모 데이터 sync

## 완료 정의

MVP 완료는 다음 demo script가 성공하면 됩니다.

1. 사용자가 dashboard에 접속합니다.
2. "부산 / 2026년 5월 / 외국인 / 상품 5개" 요청을 입력합니다.
3. workflow run이 생성되고 진행 상태가 보입니다.
4. Data Agent tool call 로그에 TourAPI mock/real 호출이 보입니다.
5. 상품 5개가 생성됩니다.
6. 각 상품에 source evidence가 연결됩니다.
7. QA 이슈가 표시됩니다.
8. 사용자가 승인합니다.
9. 결과 report가 저장됩니다.
10. eval smoke를 실행해 metrics report를 봅니다.

## 위험 요소와 대응

### TourAPI 키/트래픽 문제

대응:

- mock provider 기본
- cached mode
- 실제 API는 설정 시만 사용

### LLM 비용 증가

대응:

- model tier
- budget guard
- mock LLM mode
- eval sample size 제한

### 생성 JSON 깨짐

대응:

- Pydantic validation
- structured output
- retry with repair prompt

### UI 범위 과다

대응:

- dashboard/run/result/eval만 먼저
- settings와 billing은 읽기 중심

### 평가 구현 난이도

대응:

- deterministic metrics 먼저
- Ragas/DeepEval은 최소 smoke 연동

