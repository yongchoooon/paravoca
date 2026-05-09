# PARAVOCA AX Agent Studio 문서 인덱스

작성 기준일: 2026-05-07

이 폴더는 Codex가 실제 개발을 시작할 수 있도록 만든 프로젝트 상세 명세입니다. 원문 아이디어의 방향은 유지하되, 프론트엔드 스택은 `Tailwind CSS`, `shadcn/ui`, `Bootstrap`을 사용하지 않고 `Mantine UI`, `CSS Modules 또는 SCSS Modules`, `React Flow`를 사용하는 것으로 확정했습니다.

## 프로젝트 요약

`PARAVOCA AX Agent Studio`는 여행 액티비티와 관광 상품 운영자를 위한 멀티에이전트 워크플로우 시스템입니다. 사용자가 "이번 달 부산에서 외국인 대상 액티비티 상품을 5개 기획해줘"처럼 요청하면, 시스템은 공공 관광 데이터 조회, 지역/계절성 분석, 상품 아이디어 생성, 상세페이지 카피/FAQ 생성, 리스크 검수, 사람 승인, 저장까지 이어지는 운영 자동화 플로우를 실행합니다.

제품 방향은 여행 상품화 운영 업무에 맞춥니다. 문서 전반에서 다음을 강제합니다.

- 출처 기반 생성: TourAPI, 관광 수요 데이터, 자체 DB, RAG 결과를 근거로 답변합니다.
- 도구 호출 추적: 어떤 Agent가 어떤 API/tool을 왜 호출했는지 저장합니다.
- Human-in-the-loop: 최종 저장과 외부 전송은 사람 승인 뒤에만 실행합니다.
- 평가 자동화: RAG, agent tool call, workflow success, 비용, latency를 측정합니다.
- 비용 거버넌스: Gemini gateway 사용량 추적, 저가 모델 라우팅, 샘플 기반 eval, batch 실행을 설계합니다.

현재 코드 구현 기준은 Phase 10.2까지입니다. TourAPI 기본 검색, KorService2 상세 보강, source document/Chroma 색인, local semantic embedding provider, Gemini 기반 Product/Marketing/QA, revision workflow, KTO capability catalog, Run Detail Evidence의 상세 정보/이미지 후보 표시까지 구현되어 있습니다. Phase 9.6에서는 `GeoResolverAgent`를 추가해 자연어 요청에서 지역 의도를 해석하고, TourAPI v4.4 `ldongCode2?lDongListYn=Y`/`lclsSystmCode2` catalog를 기준으로 `lDongRegnCd`/`lDongSignguCd` 검색을 수행합니다. 지역이 애매하면 run status는 `failed`로 저장하고 지역 후보 안내를 표시하며, 해외 목적지는 PARAVOCA 국내 지원 범위 안내로 종료합니다. Phase 10에서는 Data 단계를 `BaselineDataAgent`, `DataGapProfilerAgent`, `ApiCapabilityRouterAgent`, 4개 API family planner, `EnrichmentExecutor`, `EvidenceFusionAgent`로 분리해 필요한 데이터 보강만 실행하고, Product/Marketing/QA에 넘길 `evidence_profile`, `productization_advice`, `data_coverage`, `unresolved_gaps`를 생성합니다. Phase 10.2에서는 DataGap/Router/Planner/Fusion 판단을 Gemini prompt + JSON schema 기반으로 전환했고, raw 후보 shortlist, compact capability brief, KorService2 상세 보강 전체 처리, 후보별 EvidenceFusion card, prompt debug log, Dashboard task 삭제, QA Review Avoid 표시를 반영했습니다.

## 문서 목록

1. [01_PRODUCT_BRIEF.md](./01_PRODUCT_BRIEF.md)
   - 제품 목적, 대상 사용자, 비즈니스 임팩트, 포트폴리오 포지셔닝

2. [02_USER_STORIES_AND_SCOPE.md](./02_USER_STORIES_AND_SCOPE.md)
   - 사용자 스토리, MVP/P1/P2 범위, 수용 기준

3. [03_SYSTEM_ARCHITECTURE.md](./03_SYSTEM_ARCHITECTURE.md)
   - 전체 아키텍처, 서비스 구성, 데이터 흐름, 실행 플로우

4. [04_TECH_STACK_MANTINE.md](./04_TECH_STACK_MANTINE.md)
   - 기술스택 확정안, Mantine UI 적용 방식, Tailwind/shadcn/Bootstrap 금지 사항

5. [05_DATA_SOURCES_AND_INGESTION.md](./05_DATA_SOURCES_AND_INGESTION.md)
   - TourAPI, 관광 수요 데이터, 수집/정제/저장/색인 전략

5-1. [05_01_KTO_OPENAPI_DATA_ENRICHMENT_PLAN.md](./05_01_KTO_OPENAPI_DATA_ENRICHMENT_PLAN.md)
   - 한국관광공사 OpenAPI 묶음별 데이터 보강 계획, 상품화 활용 방식, 우선 구현 순서

5-2. [05_02_DATA_ENRICHMENT_AGENT_WORKFLOW.md](./05_02_DATA_ENRICHMENT_AGENT_WORKFLOW.md)
   - 데이터 공백 분석, API 라우팅, 보강 실행, 근거 병합 Agent 구현 계획

5-3. [05_03_TOURAPI_KORSERVICE2_V44_SPEC.md](./05_03_TOURAPI_KORSERVICE2_V44_SPEC.md)
   - TourAPI KorService2 v4.4 단일 명세. API 명세 canonical 문서는 99번 체계를 우선

6. [06_AGENT_WORKFLOW_SPEC.md](./06_AGENT_WORKFLOW_SPEC.md)
   - Planner, Data, Research, Product, Marketing, QA/Compliance Agent 상세 명세

7. [07_BACKEND_API_AND_DB_SPEC.md](./07_BACKEND_API_AND_DB_SPEC.md)
   - FastAPI 엔드포인트, DB 테이블, Pydantic 스키마, 작업 큐

8. [08_FRONTEND_UI_SPEC.md](./08_FRONTEND_UI_SPEC.md)
   - React/Next.js UI, React Flow 워크플로우 빌더, Mantine UI 컴포넌트 규칙

9. [09_RAG_GUARDRAILS_EVALUATION.md](./09_RAG_GUARDRAILS_EVALUATION.md)
   - RAG 설계, Guardrails, Ragas/DeepEval/pytest 평가 지표

10. [10_COST_BILLING_AND_PAYMENT.md](./10_COST_BILLING_AND_PAYMENT.md)
    - LLM 비용 설계, 월 3만 원 내외 운영 전략, SaaS 결제 설계, Toss/Stripe 옵션

11. [11_IMPLEMENTATION_ROADMAP.md](./11_IMPLEMENTATION_ROADMAP.md)
    - 개발 순서, 마일스톤, Codex 작업 단위, 완료 기준

12. [12_DEPLOYMENT_OPERATIONS_SECURITY.md](./12_DEPLOYMENT_OPERATIONS_SECURITY.md)
    - Docker, 배포, 환경변수, 보안, 로그, 운영 점검

13. [13_CODEX_IMPLEMENTATION_PROMPT.md](./13_CODEX_IMPLEMENTATION_PROMPT.md)
    - Codex에게 그대로 전달할 구현 프롬프트와 작업 규칙

14. [14_POST_PHASE7_IMPLEMENTATION_PLAN.md](./14_POST_PHASE7_IMPLEMENTATION_PLAN.md)
    - Phase 7 이후 KTO 데이터 보강, AppShell 전역 navigation, 공식 웹 근거, Agent 실제화, 평가, 배포, Poster Studio 구현 순서

15. [15_PHASE_9_6_GEO_RESOLVER_PLAN.md](./15_PHASE_9_6_GEO_RESOLVER_PLAN.md)
    - 자연어 지역 의도 추출, GeoResolverAgent, TourAPI 법정동/신분류체계 전환 구현 계획

16. [16_PHASE_10_2_GEMINI_DATA_ENRICHMENT.md](./16_PHASE_10_2_GEMINI_DATA_ENRICHMENT.md)
   - Gemini 기반 DataGapProfiler/ApiCapabilityRouter/Planner/EvidenceFusion 전환, shortlist와 prompt 축소, KorService2 상세 보강 정책, 후보별 evidence card, Phase 11/12 연결 계획

99. [99_00_KTO_API_SPEC_INDEX.md](./99_00_KTO_API_SPEC_INDEX.md)
    - KTO/TourAPI API 명세 canonical 인덱스, 99-01부터 99-13까지 서비스별 endpoint/response schema 정규화 문서

## 최종 개발 방향

### MVP에서 반드시 구현할 것

- 자연어 요청/기간/타깃/상품 수 입력 기반 상품 기획 실행
- TourAPI v4.4 법정동 catalog 기반 지역 해석과 지역 후보 확인
- TourAPI 기반 관광지/행사/숙박/이미지 데이터 조회
- RAG 검색 결과와 출처를 포함한 상품 아이디어 생성
- 상세페이지 카피, FAQ, SNS 문구, 검색 키워드 생성
- QA/Compliance Agent의 리스크 검수
- Human Approval 상태 전환
- Workflow Builder UI에서 노드 기반 플로우 생성/실행
- 실행 로그, tool call 로그, 비용/latency 기록
- 최소 평가 스크립트: retrieval recall, faithfulness, tool call accuracy, task success, cost per task

### MVP에서 하지 않을 것

- 실제 여행 상품 판매/예약/재고 연동
- 실결제 승인
- 대규모 크롤링
- 자체 LLM 학습
- 완전한 멀티테넌트 권한/정산 시스템
- Poster Studio 이미지 생성
- Tailwind CSS, shadcn/ui, Bootstrap 설치 또는 사용

## 공식 출처 확인 메모

아래 링크는 문서 작성 시 참고한 공식/주요 출처입니다. 가격과 API 정책은 변동 가능성이 있으므로 실제 구현 직전 재확인이 필요합니다.

- 한국관광공사 국문 관광정보 서비스: https://www.data.go.kr/data/15101578/openapi.do
- 한국관광공사 지역별 관광 자원 수요 API: https://www.data.go.kr/data/15152138/openapi.do
- 한국관광공사 관광공모전 사진 수상작 정보: https://www.data.go.kr/data/15145706/openapi.do
- 한국관광공사 웰니스관광정보: https://www.data.go.kr/data/15144030/openapi.do
- 한국관광공사 의료관광정보: https://www.data.go.kr/data/15143913/openapi.do
- 한국관광공사 반려동물 동반여행 서비스: https://www.data.go.kr/data/15135102/openapi.do
- 한국관광공사 두루누비 정보 서비스_GW: https://www.data.go.kr/data/15101974/openapi.do
- 한국관광공사 관광지 오디오 가이드정보_GW: https://www.data.go.kr/data/15101971/openapi.do
- 한국관광공사 생태 관광 정보_GW: https://www.data.go.kr/data/15101908/openapi.do
- 한국관광공사 관광사진 정보_GW: https://www.data.go.kr/data/15101914/openapi.do
- 한국관광공사 관광빅데이터 정보서비스_GW: https://www.data.go.kr/data/15101972/openapi.do
- 한국관광공사 관광지 집중률 방문자 추이 예측 정보: https://www.data.go.kr/data/15128555/openapi.do
- 한국관광공사 관광지별 연관 관광지 정보: https://www.data.go.kr/data/15128560/openapi.do
- LangGraph workflows/agents: https://docs.langchain.com/oss/python/langgraph/workflows-agents
- Gemini Developer API pricing: https://ai.google.dev/pricing
- OpenAI Image generation: https://developers.openai.com/api/docs/guides/image-generation
- Chroma docs: https://docs.trychroma.com/docs/overview/getting-started
- Qdrant quickstart/indexing: https://qdrant.tech/documentation/quick-start/
- Ragas metrics: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/
- DeepEval docs: https://deepeval.com/docs/introduction
- React Flow: https://reactflow.dev/
- Mantine getting started: https://mantine.dev/getting-started/
- Mantine AppShell: https://mantine.dev/core/app-shell/
- Toss Payments billing: https://docs.tosspayments.com/guides/v2/billing
- Stripe subscriptions: https://docs.stripe.com/billing/subscriptions/set-up-subscription
