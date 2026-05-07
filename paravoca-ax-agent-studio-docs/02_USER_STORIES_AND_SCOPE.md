# 사용자 스토리와 개발 범위

## 제품 범위 원칙

이 프로젝트의 목표는 "실제로 운영 가능한 멀티에이전트 여행 상품 운영 자동화 시스템"을 보여주는 것입니다. 따라서 MVP는 기능을 넓게 벌리기보다, 하나의 대표 업무를 끝까지 완성하는 데 집중합니다.

대표 업무:

```text
지역/기간/타깃/상품 수 입력
→ 데이터 조회
→ 지역/계절성/행사 분석
→ 상품 아이디어 생성
→ 마케팅 카피/FAQ/SNS/키워드 생성
→ 리스크 검수
→ 사람 승인
→ 저장
→ 평가/비용 리포트
```

## 사용자 역할

### Admin

시스템 설정, API 키, 모델 라우팅, 평가 데이터셋, 사용자 권한을 관리합니다.

### Operator

상품 기획 요청을 실행하고 결과를 승인/반려합니다.

### Reviewer

QA/Compliance 결과를 검토하고 수정 의견을 남깁니다.

### Viewer

결과 리포트와 실행 로그를 조회합니다.

MVP에서는 인증을 간단히 구현합니다. 실제 계정 시스템은 단일 관리자 계정으로 시작해도 됩니다.

## MVP 사용자 스토리

### US-001: 상품 기획 요청 생성

사용자로서 지역, 기간, 타깃, 상품 수, 선호 조건을 입력해 상품 기획 workflow를 실행하고 싶다.

입력 필드:

- `region`: 예: 부산
- `period`: 예: 이번 달, 2026-05, 2026-05-01~2026-05-31
- `target_customer`: 예: 외국인, 가족, 커플, 혼행, 시니어
- `product_count`: 예: 5
- `preferences`: 예: 야간 관광, 축제 포함, 전통시장 포함
- `avoid`: 예: 과도한 이동, 가격 단정 표현
- `language`: `ko`, `en`, `ja`, `zh` 중 MVP는 `ko`, `en`만 지원

수용 기준:

- 요청 생성 시 `workflow_runs` 레코드가 생성됩니다.
- 상태는 `pending`에서 시작해 `running`, `awaiting_approval`, `approved` 또는 `failed`로 바뀝니다.
- 입력값은 원문과 정규화된 값 모두 저장됩니다.

### US-002: Planner Agent 작업 분해

사용자로서 시스템이 복잡한 요청을 단계별 작업으로 나누는 과정을 보고 싶다.

수용 기준:

- Planner Agent는 최소 다음 작업을 생성합니다.
  - 지역 데이터 조회
  - 관광지 후보 검색
  - 행사/축제 조회
  - 숙박 또는 주변 인프라 조회
  - 수요/계절성 분석
  - 상품 기획
  - 카피/FAQ/SNS 생성
  - 리스크 검수
  - 최종 리포트 생성
- 각 작업은 `agent_steps`에 저장됩니다.
- 각 작업은 `status`, `started_at`, `finished_at`, `input`, `output`을 갖습니다.

### US-003: 관광 데이터 조회

사용자로서 TourAPI 기반 관광지/행사/숙박/이미지 정보를 자동으로 수집하고 싶다.

수용 기준:

- Data Agent는 지역코드 조회, 키워드 검색, 지역 기반 관광정보, 행사정보, 숙박정보, 이미지정보 중 최소 3개 이상을 호출합니다.
- 실제 TourAPI 키가 없으면 관광 데이터 조회와 workflow run은 실패 상태로 기록됩니다.
- tool call 로그에는 tool name, arguments, response summary, latency, success 여부가 저장됩니다.
- API 실패 시 tool call error와 workflow run error가 저장되고 개발자 로그에 출력됩니다.

### US-004: 지역/계절성/타깃 분석

사용자로서 수집된 데이터를 바탕으로 이번 기간에 어떤 상품이 적합한지 분석받고 싶다.

수용 기준:

- Research Agent는 후보 관광지를 유형별로 분류합니다.
- 행사 날짜가 요청 기간과 겹치는지 확인합니다.
- 타깃 고객과 적합한 이유를 설명합니다.
- 출처 없는 주장은 `assumption`으로 표시합니다.

### US-005: 상품 아이디어 생성

사용자로서 실행 결과로 판매 가능한 수준의 상품 아이디어를 받고 싶다.

수용 기준:

- Product Agent는 요청한 개수만큼 상품 아이디어를 생성합니다.
- 각 아이디어에는 제목, 타깃, 핵심 가치, 추천 코스, 포함 관광지/행사, 운영 난이도, 예상 소요 시간, 주의사항이 포함됩니다.
- 각 아이디어는 최소 2개 이상의 source item을 참조합니다.
- 가격은 확정 가격으로 단정하지 않고 "운영자가 협의/확정 필요"로 표시합니다.

### US-006: 마케팅 콘텐츠 생성

사용자로서 상품별 상세페이지 카피, FAQ, SNS 문구, 검색 키워드를 받고 싶다.

수용 기준:

- Marketing Agent는 상품별로 다음을 생성합니다.
  - 상세페이지 헤드라인 1개
  - 상세 요약 1개
  - 세부 섹션 3개 이상
  - FAQ 5개
  - SNS 문구 3개
  - 검색 키워드 10개
- 과장 표현은 피하고, 불확실한 정보는 확인 필요로 표시합니다.
- 외국인 대상 요청이면 영어 카피도 선택 생성할 수 있어야 합니다.

### US-007: QA/Compliance 검수

사용자로서 생성 결과가 운영 리스크를 일으키지 않는지 자동 검수하고 싶다.

검수 항목:

- 출처 누락
- 날짜 불일치
- 행사 종료/미확정 정보 단정
- 가격 단정
- 안전/의료/법적 과장 표현
- "무조건", "최고", "100% 만족" 같은 과장 표현
- API 데이터와 생성 결과의 충돌
- 이미지 사용 제한 메모 누락

수용 기준:

- QA Agent는 상품별 risk status를 `pass`, `needs_review`, `fail` 중 하나로 표시합니다.
- 이슈는 severity `low`, `medium`, `high`를 갖습니다.
- high 이슈가 있으면 Human Approval 전에 반드시 수정 또는 확인이 필요합니다.

### US-008: Human Approval

사용자로서 사람이 승인해야만 결과가 저장되게 하고 싶다.

수용 기준:

- workflow 결과는 기본적으로 `draft`입니다.
- 승인 버튼 클릭 시 `approved`가 됩니다.
- 반려 버튼 클릭 시 `rejected`가 됩니다.
- 승인/반려에는 reviewer, timestamp, comment가 저장됩니다.
- 승인 전에는 Google Sheet, 외부 API, 실서비스 DB 저장 tool이 실행되지 않습니다.

### US-009: Workflow Builder

사용자로서 노드 기반 UI에서 워크플로우를 조합하고 실행하고 싶다.

수용 기준:

- React Flow 기반 캔버스가 있습니다.
- 기본 노드:
  - User Input
  - Data Collection
  - RAG Search
  - Research Analysis
  - Product Planning
  - Marketing Copy
  - QA Review
  - Human Approval
  - Save Result
- 노드를 연결하고 저장할 수 있습니다.
- 저장된 workflow template을 실행할 수 있습니다.
- 각 노드 실행 상태가 색상/배지로 표시됩니다.

### US-010: 평가 리포트

사용자로서 시스템 품질을 지표로 확인하고 싶다.

수용 기준:

- 평가 데이터셋 JSONL을 읽어 workflow를 실행합니다.
- 결과로 다음 지표를 계산합니다.
  - Retrieval Recall
  - Faithfulness
  - Tool Call Accuracy
  - Task Success Rate
  - Cost per Task
  - Latency
- Human Revision Rate
- 평가 결과는 JSON과 Markdown 리포트로 저장됩니다.

## 후속 사용자 스토리

### US-011: Poster Studio

사용자로서 승인 또는 검토 중인 상품 초안을 기반으로 홍보 포스터를 만들고 싶다.

사용 흐름:

1. Run Review에서 포스터를 만들 상품을 선택합니다.
2. 시스템은 선택한 상품의 title, one_liner, core_value, itinerary, sales_copy, FAQ, assumptions, not_to_claim, QA issue를 읽습니다.
3. Poster Prompt Agent가 포스터에 넣을 문구와 디자인 방향을 추천합니다.
4. 사용자는 추천 문구를 남기거나 삭제하고 직접 수정합니다.
5. 사용자는 포스터 목적, 비율, 스타일, 문구 밀도, 포함 정보, 이미지 기준을 선택합니다.
6. Poster Prompt Agent가 최종 이미지 생성 프롬프트를 생성합니다.
7. Poster Image Agent가 OpenAI Image API로 포스터 이미지를 생성합니다.
8. 생성 결과는 원본 run과 product에 연결되어 저장됩니다.

입력 옵션:

- `product_id`: 포스터를 만들 상품
- `purpose`: `detail_cover`, `sns_feed`, `sns_story`, `offline_a4`
- `aspect_ratio`: `1:1`, `4:5`, `9:16`, `a4_portrait`
- `style_direction`: 예: 프리미엄 여행, 로컬 감성, 축제 홍보, 가족 친화, 액티비티 중심
- `copy_density`: `minimal`, `balanced`, `detailed`
- `include_fields`: 상품명, 지역, 기간, 타깃, 핵심 코스, CTA, 확인 필요 문구
- `visual_source_mode`: `ai_generated`, `tourapi_reference`, `graphic_only`
- `custom_instruction`: 사용자가 직접 추가하는 디자인/문구 지시

Poster Prompt Agent 추천 항목:

- headline 후보 3개
- subheadline 후보 3개
- CTA 후보 3개
- 포스터에 넣을 핵심 정보
- 제외할 정보
- 이미지 스타일 설명
- 색감/분위기 후보
- 텍스트 배치 가이드
- 운영 리스크가 있는 문구

수용 기준:

- 포스터 생성은 기존 workflow run을 덮어쓰지 않고 별도 poster asset으로 저장됩니다.
- 최종 이미지 생성 전 사용자가 문구와 옵션을 확인하고 수정할 수 있습니다.
- 최종 prompt에는 가격, 예약 가능 여부, 운영 시간 단정 표현이 들어가지 않아야 합니다.
- `not_to_claim`, QA issue, requested changes는 포스터 문구 추천에서 제한 조건으로 반영됩니다.
- 생성된 이미지, prompt, 선택 옵션, provider, model, latency, 예상 비용이 저장됩니다.
- 기본 이미지 모델 후보는 구현 시점 공식 문서 기준으로 재확인하며, 현재 문서 기준 후보는 `gpt-image-2`입니다.
- 생성 이미지는 `needs_review` 상태로 시작하고 사람이 승인해야 사용 가능 상태가 됩니다.

## MVP 범위

### 반드시 포함

- FastAPI backend
- SQLite 기본 DB, PostgreSQL 전환 가능 구조
- SQLAlchemy 모델
- LangGraph 기반 workflow 실행
- Gemini gateway 기반 모델 호출 wrapper
- TourAPI provider
- Chroma 또는 Qdrant 중 하나
- React 또는 Next.js frontend
- React Flow workflow builder
- Mantine UI + CSS Modules 또는 SCSS Modules UI
- pytest 평가/단위 테스트
- Ragas 또는 DeepEval 최소 1개 연동
- Docker Compose

### 선택 포함

- Redis 기반 background queue
- Google Sheets export placeholder
- 로그인/권한
- 다국어 출력
- Qdrant payload index
- OpenAI/GPT 비교 implementation branch

## P1 범위

MVP 이후 추가할 기능입니다.

- 실제 Google Sheets 저장
- 팀/프로젝트 단위 멀티테넌트
- 워크플로우 템플릿 버전 관리
- 프롬프트 버전 관리
- 관광 데이터 정기 동기화 스케줄러
- 평가 결과 대시보드
- Human Revision diff tracking
- CSV 업로드 기반 자체 상품 데이터 RAG
- OpenTelemetry/Prometheus metrics
- Poster Studio prompt draft UI

## P2 범위

고도화 기능입니다.

- Toss Payments 또는 Stripe 기반 유료 플랜
- 사용량 기반 과금
- 예약/재고/가격 관리 시스템 연동
- Slack/Notion/Jira 알림
- 자동 A/B copy variation 생성
- Poster Studio 이미지 생성
- OpenAI Image API 기반 포스터 asset 저장
- 포스터 재생성/variant 관리
- 외부 파트너 승인 워크플로우
- 다국어 TourAPI 서비스 확장

## 명시적 제외 범위

- Tailwind CSS 사용
- shadcn/ui 사용
- Bootstrap 사용
- 실제 고객 결제 처리 MVP 포함
- 예약 확정/취소/환불 처리
- 공공데이터 라이선스 범위를 벗어난 이미지 재사용
- 사람이 검수하지 않은 생성 포스터의 외부 게시
- 웹 크롤링 중심 데이터 수집
- 사람이 승인하지 않은 외부 저장/전송

## 비기능 요구사항

### 성능

- MVP 기준 단일 workflow는 90초 이내 완료를 목표로 합니다.
- 실제 TourAPI 호출 기준 30초 이내 완료를 목표로 합니다.
- API 응답은 일반 조회 1초 이내, workflow 실행 시작 요청 2초 이내를 목표로 합니다.

### 안정성

- 외부 API 실패 시 workflow 전체가 즉시 죽지 않고 partial result와 error를 남깁니다.
- LLM 호출 실패 시 실패 원인을 로그에 남기고 retry 가능 상태로 기록합니다.
- 비용 상한 초과 시 expensive model 호출을 차단합니다.

### 관측성

- workflow run id 기준으로 모든 agent step, tool call, LLM call, cost, latency를 추적합니다.
- 평가 실행은 별도 eval run id를 가집니다.

### 보안

- API keys는 `.env`에만 저장합니다.
- 프론트엔드 번들에 secret key가 들어가면 안 됩니다.
- TourAPI service key, LLM provider key, 결제 provider secret은 서버에서만 사용합니다.
