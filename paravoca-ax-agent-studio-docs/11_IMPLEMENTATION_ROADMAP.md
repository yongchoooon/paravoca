# 구현 로드맵

이 문서는 초기 end-to-end 구현 로드맵입니다. Phase 7 이후 실제 구현 순서는 KTO 데이터 보강 계획이 추가되면서 `14_POST_PHASE7_IMPLEMENTATION_PLAN.md`를 우선합니다. 현재 코드 기준으로는 Phase 10.1/10.2까지 구현되어 있고, 다음 단계는 Phase 10.5 UI/운영 화면 정리입니다.

## 구현 원칙

Codex는 아래 순서대로 구현합니다. 핵심은 "작동하는 얇은 end-to-end slice"를 먼저 만든 뒤, 데이터/에이전트/평가/UI를 점진적으로 강화하는 것입니다.

첫 번째 목표:

```text
사용자 요청 입력
→ 실제 TourAPI 데이터 조회
→ agent workflow 실행
→ 상품 3개 생성
→ QA 검수
→ 승인 대기
→ 승인
→ 결과 DB 저장과 JSON export
```

## Phase 0: 프로젝트 scaffold

목표:

- backend/frontend 기본 구조 생성
- Docker Compose 준비
- Mantine UI 기반 UI scaffold

작업:

- `backend/` FastAPI 프로젝트 생성
- `frontend/` React/Next.js 프로젝트 생성
- Tailwind/shadcn/Bootstrap 없이 Mantine UI 설치
- `.env.example` 작성
- `docker-compose.yml` 작성
- README 실행 방법 작성

완료 기준:

- Backend `GET /api/health` 동작
- Frontend dashboard 렌더링
- MantineProvider와 기본 theme 적용
- Tailwind/shadcn/Bootstrap 관련 파일 없음

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

- TourAPI interface와 실제 provider 구현

작업:

- `TourismDataProvider` protocol 작성
- TourAPI 실제 client 작성
- data normalization
- tool logging decorator
- tourism search API

완료 기준:

- 실제 TourAPI로 부산 관광지/행사/숙박 데이터 반환
- tool call log 저장
- API 키가 없거나 호출 실패 시 run과 tool call에 실패 로그 저장

## Phase 3: RAG 최소 구현

목표:

- source document 생성과 vector search 구현

작업:

- SourceDocument model
- Chroma client
- embedding wrapper
- vector search API

완료 기준:

- TourAPI로 수집한 부산 데이터가 vector DB에 색인됨
- `POST /api/rag/search`가 top_k 결과 반환
- metadata filter 적용

## Phase 4: LangGraph workflow

목표:

- Planner/GeoResolver/Data/Research/Product/Marketing/QA node가 연결된 workflow 실행

작업:

- GraphState 정의
- Planner Agent 구현
- GeoResolver Agent 구현
- Data Agent 구현
- Research Agent 구현
- Product Agent 구현
- Marketing Agent 구현
- QA Agent 구현
- Human Approval stop 구현

완료 기준:

- 실제 TourAPI 입력으로 end-to-end workflow 실행
- 자연어 요청의 지역이 TourAPI `ldong` catalog 기준으로 해석됨
- run status가 `awaiting_approval`로 멈춤
- final draft output 생성
- agent_steps, tool_calls, llm_calls 저장

## Phase 5: LLM gateway와 비용 추적

목표:

- Gemini gateway 기반 모델 호출과 비용 기록

작업:

- GeminiGateway 구현
- model policy config
- cost tracker
- budget guard
- JSON schema validation
- error logging policy

완료 기준:

- 모든 LLM 호출이 `llm_calls`에 저장
- run total cost 계산
- budget 초과 시 차단
- rule-based LLM-off mode 지원

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

## Phase 7: Revision Workflow

목표:

- 승인/반려 전 수정 요청을 실제 재생성 또는 사람 편집 흐름으로 연결
- 기존 run을 덮어쓰지 않고 revision run을 새로 만들어 audit trail 유지

작업:

- `parent_run_id`, `revision_number`, `revision_mode` 필드 추가
- `POST /api/workflow-runs/{run_id}/revisions` API 추가
- 수정 방식 선택:
  - `manual_save`: 운영자가 수정한 결과를 저장하고 QA는 재실행하지 않음
  - `manual_edit`: 운영자가 products/marketing_assets 일부를 직접 수정하고 QA만 재실행
  - `llm_partial_rewrite`: 선택한 QA issue와 requested changes를 바탕으로 필요한 필드만 AI patch
  - `qa_only`: 기존 또는 수정된 결과로 QA/Compliance Agent만 다시 실행
- 기존 source evidence, QA report, approval history를 revision context로 전달
- revision 실행 전 create run 설정과 QA settings 확인/수정 UI 제공
- revision run은 `pending -> running -> awaiting_approval`로 별도 실행
- revision run은 항상 최상위 원본 run을 parent로 연결하고 `revision_number`만 증가
- 대시보드에서는 최상위 원본 run 중심으로 표시하고 revision은 펼쳐서 확인
- 원본 run과 revision run을 UI에서 이동 가능하게 표시

완료 기준:

- Request changes 이후 revision run 생성 가능
- 직접 수정한 결과를 저장하거나 QA 재검수 가능
- AI 수정이 전체 재생성 없이 선택된 QA issue 관련 필드만 변경
- Approval History에서 v1 요청, v2 재검수, 최종 승인 흐름 확인 가능
- QA 메시지에서 내부 필드명 노출을 막고 안전한 완화 문구를 단정 표현으로 오판하지 않음

## Phase 8: 평가 파이프라인

현재 Phase 7 이후 실제 구현 순서는 데이터 보강 범위가 확장되면서 재정렬되었습니다. Phase 8 이후의 최신 계획은 `14_POST_PHASE7_IMPLEMENTATION_PLAN.md`를 우선합니다. 이 섹션의 평가 파이프라인은 KTO 상세/이미지/수요/공식 웹 근거 보강과 Planner/Data/Research Agent 실제화 이후 진행합니다.

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

## Phase 9: 배포와 polish

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
- 실제 TourAPI 키가 있으면 demo 완주 가능
- TourAPI 호출 실패 시 FastAPI 로그, tool call, workflow error log에서 원인 확인 가능

## Phase 10: Poster Studio

목표:

- 상품 기획 결과를 포스터 제작 workflow로 확장
- 사용자가 포스터 문구와 옵션을 검토한 뒤 이미지 생성 실행

작업:

- Poster Context Builder 구현
- Poster Prompt Agent 구현
- poster prompt draft schema 작성
- poster option review UI 작성
- `poster_assets`, `poster_prompt_drafts`, `poster_image_calls` 저장 구조 추가
- OpenAIImageGateway 구현
- `gpt-image-2` 기본 후보 설정
- poster generation cost/latency logging
- Poster QA/Review UI 작성
- approved poster export flow 작성

완료 기준:

- Run Review에서 product를 선택하고 Poster Studio를 열 수 있음
- Poster Prompt Agent가 headline/subheadline/CTA/style 후보를 생성
- 사용자가 후보 문구와 옵션을 삭제/수정/추가 가능
- 최종 prompt preview를 확인한 뒤 image generation 실행 가능
- 생성 이미지가 원본 run/product와 연결되어 저장
- 이미지 생성 provider/model/latency/cost가 기록
- generated poster는 `needs_review` 상태로 시작
- 승인된 poster만 export 가능
- OpenAI Image API 모델명과 가격은 구현 직전에 공식 문서로 재확인

## Phase 11: 웹 근거 보강과 사용자 추가 정보 수집

목표:

- TourAPI만으로 부족한 상품화/검증 정보를 웹 근거와 사용자 제공 정보로 보강
- 최신 운영 정보, 예약 조건, 공식 공지, 집결지, 가격/포함사항 등 구체 정보의 출처를 보존
- 비용과 latency가 늘지 않도록 기본 비활성화된 선택 기능으로 구현

배경:

- TourAPI는 관광지/행사/숙박의 공식 기본 데이터에는 강하지만, 실제 판매 가능한 상품으로 다듬는 데 필요한 세부 운영 정보가 부족할 수 있습니다.
- 상품 상세페이지나 QA 검증에는 "왜 이 정보를 썼는지"를 보여줄 수 있는 근거 링크와 조회 시각이 필요합니다.
- 일부 정보는 웹에서도 확정하기 어렵기 때문에 사용자가 직접 공급사 메모, 가격 조건, 집결지, 포함/불포함 항목을 입력하는 흐름이 필요합니다.

작업:

- `web_search_enabled`, `max_web_queries_per_run`, `max_grounded_prompts_per_run` 설정 추가
- Data Agent에 `data_gaps` 기반 웹 보강 후보 생성 로직 추가
- `web_search` 또는 `google_search_grounding` tool provider interface 작성
- 웹 검색 결과를 `source=web` SourceDocument로 정규화하고 Chroma에 색인
- 공식 사이트/공지, 비공식 문서, 사용자 입력의 trust level 분리
- 검색 결과 URL, query, retrieved_at, source_type, provider metadata 저장
- 사용자 추가 정보 요청 필드 설계: 집결지, 가격, 포함사항, 운영 시간, 예약 정책, 공급사 메모
- Run Detail UI에서 "추가 정보 필요" 항목과 근거 링크 표시
- Product/Marketing/QA Agent가 TourAPI 근거와 웹 근거를 분리해 표시하도록 prompt/context 확장
- 비용 추적에 grounded prompt/search query count 추가
- budget guard가 검색 grounding을 차단하거나 query 수를 줄일 수 있게 구현

완료 기준:

- TourAPI 근거만 부족한 run에서 `data_gaps`가 생성됨
- 운영자가 웹 보강 검색을 켜면 `tool_calls`에 `web_search` 또는 `google_search_grounding`이 기록됨
- 웹 검색 결과가 `source_documents`와 `retrieved_documents`에 출처 URL과 조회 시각을 포함해 저장됨
- 상품/QA 결과에서 웹 근거가 있는 주장과 운영자 확인이 필요한 주장이 구분됨
- 검색 비용/grounded prompt 수가 run 단위로 집계됨
- 웹 검색 실패 시 workflow 전체를 실패시키지 않고 `web_search_unavailable`로 남긴 뒤 draft 생성은 계속됨

## Codex 작업 단위

### Task 1

프로젝트 scaffold와 health check.

산출물:

- backend FastAPI
- frontend Mantine dashboard
- docker compose

### Task 2

DB schema와 workflow run API.

산출물:

- SQLAlchemy models
- run create/list/detail
- tests

### Task 3

TourAPI provider.

산출물:

- provider interface
- data tools
- tool call logs

### Task 4

LangGraph workflow skeleton.

산출물:

- graph state
- workflow agents
- run execution
- approval stop

### Task 5

LLM gateway와 real prompt outputs.

산출물:

- Gemini gateway
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

### Task 8

Poster Studio 후속 확장.

산출물:

- Poster Prompt Agent
- poster option review UI
- OpenAIImageGateway
- poster asset storage
- poster cost logs
- poster QA/review flow

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
- Poster Studio 이미지 생성
- 복잡한 권한
- 대규모 데이터 sync
- 웹 근거 보강/검색 grounding
- 사용자 추가 정보 수집 UI

## 완료 정의

MVP 완료는 다음 demo script가 성공하면 됩니다.

1. 사용자가 dashboard에 접속합니다.
2. "부산 / 2026년 5월 / 외국인 / 상품 5개" 요청을 입력합니다.
3. workflow run이 생성되고 진행 상태가 보입니다.
4. Data Agent tool call 로그에 실제 TourAPI 호출이 보입니다.
5. 상품 5개가 생성됩니다.
6. 각 상품에 source evidence가 연결됩니다.
7. QA 이슈가 표시됩니다.
8. 사용자가 승인합니다.
9. 결과 report가 저장됩니다.
10. eval smoke를 실행해 metrics report를 봅니다.

## 위험 요소와 대응

### TourAPI 키/트래픽 문제

대응:

- TourAPI key 필수
- API 실패 시 tool call/run 실패 로그 저장
- 개발 중에도 실제 TourAPI 호출을 사용함

### LLM 비용 증가

대응:

- model tier
- budget guard
- rule-based LLM-off mode
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

### 웹 검색 비용과 근거 품질

대응:

- 기본 비활성화
- workflow run당 query/grounded prompt 제한
- 공식 출처 우선
- 비공식 출처는 `needs_review`로 분리
- 검색 실패는 data gap으로 처리하고 workflow error log에 남김
