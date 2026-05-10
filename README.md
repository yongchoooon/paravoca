# PARAVOCA AX Agent Studio

PARAVOCA AX Agent Studio는 공공 관광 데이터를 여행 상품 운영자의 업무 결과물로 바꾸는 AI 워크플로우 시스템입니다. 자연어 요청에서 지역과 의도를 해석하고, 기간과 타깃 고객을 함께 받아 상품 후보 발굴, 상품 콘셉트 작성, 상세페이지 카피와 FAQ 생성, 운영 리스크 검수, 사람 승인까지 하나의 흐름으로 이어집니다.

## 핵심 메시지

PARAVOCA AX는 여행 상품 운영자에게 "무엇을 팔 수 있을지"를 제안합니다.

관광지, 축제, 숙박, 지역 정보처럼 흩어져 있는 데이터를 운영자가 검토할 수 있는 출시 준비 초안으로 정리하고, 근거 문서와 확인이 필요한 정보를 함께 보여줍니다. 여행 플랫폼 운영자, 상품 MD, 콘텐츠 매니저, 지자체 관광 담당자가 반복적으로 수행하는 리서치와 문서 작성 시간을 줄이는 데 초점을 둡니다.

## 프로젝트 강점

- 공공 관광 데이터를 상품 후보, 코스, 상세페이지 카피, FAQ, 검색 키워드로 연결합니다.
- TourAPI와 RAG 검색 결과를 근거로 사용하고, 출처가 약한 정보는 운영자 확인 대상으로 분리합니다.
- QA/Compliance 단계에서 날짜 오류, 가격 단정, 과장 표현, 출처 누락 같은 운영 리스크를 점검합니다.
- Human Approval과 Revision Workflow로 AI 초안을 사람이 검토, 수정, 승인하는 흐름을 제공합니다.
- Gemini API와 rule-based mode를 함께 지원해 비싼 GPU 없이도 실무형 AI 자동화 흐름을 구성할 수 있습니다.
- 후속 단계에서 웹 검색/검색 grounding과 사용자 추가 입력을 붙여 TourAPI만으로 부족한 운영 시간, 예약 조건, 집결지, 가격/포함사항, 최신 공지 근거를 보강할 계획입니다.
- 후속 기능으로 Run Review 결과를 활용한 포스터 생성 workflow를 확장할 수 있습니다.

## 후속 기능: Poster Studio

Poster Studio는 승인 또는 검토 중인 workflow run 결과를 바탕으로 여행 상품 홍보 포스터를 만드는 기능입니다. 상품 초안, 마케팅 카피, FAQ, 운영 주의사항, 근거 문서를 활용해 포스터에 들어갈 내용을 추천하고, 사용자가 옵션과 문구를 직접 고른 뒤 이미지 생성용 프롬프트를 확정합니다.

예상 workflow:

1. 사용자가 Run Review에서 포스터를 만들 상품을 선택합니다.
2. Poster Prompt Agent가 상품명, 타깃 고객, 핵심 가치, 지역/기간, 주요 코스, CTA, 운영 주의사항 후보를 추천합니다.
3. UI는 포스터 목적과 스타일 옵션을 제공합니다.
4. 사용자는 추천된 문구와 옵션을 남기거나 삭제하고, 직접 수정합니다.
5. Poster Prompt Agent가 최종 이미지 생성 프롬프트를 구조화합니다.
6. Poster Image Agent가 OpenAI Image API로 포스터 이미지를 생성합니다.
7. 생성된 포스터는 원본 run, 선택한 상품, 프롬프트, 옵션, 비용 로그와 함께 저장됩니다.

사용자 선택 옵션 후보:

- 목적: 상품 상세페이지 대표 이미지, SNS 피드, 스토리/릴스 커버, 오프라인 홍보 포스터
- 비율: 1:1, 4:5, 9:16, A4 세로
- 분위기: 프리미엄, 로컬 감성, 가족 친화, 액티비티 중심, 축제/시즌 강조
- 텍스트 밀도: 최소 문구, 핵심 문구 중심, 상세 정보 포함
- 포함 문구: 상품명, 한 줄 소개, 지역/기간, 핵심 코스, 타깃, CTA, 확인 필요 안내
- 이미지 기준: AI 생성 배경, TourAPI 이미지 참고, 이미지 없이 그래픽 중심

구현 시점의 기본 이미지 모델 후보는 OpenAI 공식 Image generation 문서 기준 `gpt-image-2`입니다. 모델명, 가격, 지원 파라미터는 변동될 수 있어 실제 구현 직전에 공식 문서를 다시 확인합니다.

## 공모전/포트폴리오 관점

이 프로젝트의 중심은 여행 상품화입니다. 공공 관광 데이터를 운영자가 바로 검토할 수 있는 상품 초안, 마케팅 문구, FAQ, 리스크 체크리스트, 승인 이력으로 연결합니다.

심사위원이나 채용 평가자가 확인할 수 있는 지점은 명확합니다.

- 여행 플랫폼 운영 업무의 실제 반복 작업을 모델링했습니다.
- 공공데이터를 비즈니스 업무 결과물로 변환합니다.
- LLM 생성 결과에 근거 문서, QA 검수, 사람 승인 절차를 붙였습니다.
- API 사용량, latency, 예상 비용을 기록해 운영 비용 감각을 보여줍니다.
- 작은 여행사와 지역 관광사업자도 접근 가능한 API 기반 구조를 지향합니다.

현재 구현 범위는 Phase 0부터 Phase 10.2까지입니다.

## 현재 구현 범위

- FastAPI backend scaffold
- SQLite + SQLAlchemy 연결
- 기본 workflow template seed
- `GET /api/health`
- `GET /api/workflows`
- `POST /api/workflow-runs`
- `GET /api/workflow-runs`
- `GET /api/workflow-runs/{run_id}`
- `GET /api/workflow-runs/{run_id}/steps`
- `GET /api/workflow-runs/{run_id}/tool-calls`
- `GET /api/workflow-runs/{run_id}/enrichment`
- `GET /api/workflow-runs/{run_id}/llm-calls`
- `GET /api/workflow-runs/{run_id}/approvals`
- `GET /api/workflow-runs/{run_id}/result`
- `POST /api/workflow-runs/{run_id}/approve`
- `POST /api/workflow-runs/{run_id}/reject`
- `POST /api/workflow-runs/{run_id}/request-changes`
- `POST /api/workflow-runs/{run_id}/revisions`
- `POST /api/rag/ingest/tourism`
- `POST /api/rag/search`
- `POST /api/llm/key-check`
- `GET /api/data/sources/capabilities`
- `GET /api/data/tourism/search`
- `POST /api/data/tourism/details/enrich`
- React + Mantine UI frontend scaffold
- MantineProvider, Notifications, project theme
- React Flow preview
- workflow run 생성 dashboard
- TourAPI provider interface
- TourApiProvider
- 관광 데이터 검색 API
- tool call logging
- 관광 검색 결과 `tourism_items` upsert
- `source_documents` 생성
- Chroma 기반 vector index/search
- 설정 기반 embedding provider
- 개발/테스트용 `legacy_hash` embedding provider
- 로컬 `sentence-transformers` semantic embedding provider
- source document 재색인 command
- KTO API capability catalog
- source family, trust level, license note, data quality metadata 저장 구조
- KTO 데이터 보강용 DB 모델 기본 구조
- `tourism_entities`, `tourism_visual_assets`, `tourism_route_assets`, `tourism_signal_records`
- `enrichment_runs`, `enrichment_tool_calls`, `web_evidence_documents`
- KorService2 상세 보강 provider method
- `detailCommon2`, `detailIntro2`, `detailInfo2`, `detailImage2`
- `categoryCode2`, `locationBasedList2`
- TourAPI v4.4 `ldongCode2`, `lclsSystmCode2` catalog sync
- `PreflightValidationAgent` 기반 run 생성 전 지원 범위 검증
- 한 번의 workflow run에서 생성 가능한 상품 수는 최대 5개
- Dashboard run table task 선택/전체 선택/선택 삭제
- parent task 선택 시 연결된 revision task 자동 선택, 실행 중 task 삭제 차단
- `GeoResolverAgent` 기반 자연어 지역 해석
- `lDongRegnCd`, `lDongSignguCd`, `lclsSystm1/2/3` metadata 저장
- Gemini 기반 `PlannerAgent`, `DataGapProfilerAgent`, `ApiCapabilityRouterAgent`, 4개 API family planner, `EvidenceFusionAgent`, `ResearchSynthesisAgent`
- `BaselineDataAgent`와 `EnrichmentExecutor`는 LLM Agent가 아니라 TourAPI 수집/색인/선택 보강을 실행하는 deterministic 단계
- 수집 데이터 기반 gap profiling: 상세정보, 이미지, 운영시간, 요금, 예약정보, 연관 장소, 동선, 테마 특화 데이터
- 99번 KTO API 명세 기반 capability brief와 선택적 enrichment plan 생성
- `TOURAPI_CANDIDATE_SHORTLIST_LIMIT` 기반 raw 후보 shortlist 및 non-core API용 `ENRICHMENT_MAX_CALL_BUDGET` 예산 제한
- content_id 기반 상세 보강 API
- TourAPI 검색 결과의 상세 주소, 홈페이지, 개요, 좌표, 대표 이미지 보강
- content type별 소개 정보와 이용 시간, 주차, 쉬는 날, 문의, 요금성 안내 저장
- `detailImage2` 결과를 게시 후보가 아닌 `candidate` 이미지 후보로 저장
- 보강된 source document를 Chroma에 재색인
- evidence profile, productization advice, data coverage, unresolved gaps, UI highlights 생성
- Run Detail Evidence에서 상세 정보와 이미지 후보 확인
- Run Detail Data Coverage와 Recommended Data Calls panel
- Run Detail QA Review에서 최초 실행 또는 마지막 revision QA 설정의 Avoid 기준 표시
- LangGraph workflow skeleton
- Planner, Baseline Data, Gap Profiling, API Routing, Data Enrichment, Evidence Fusion, Research Synthesis, Product, Marketing, QA/Compliance Agent
- Planner와 Data 사이에서 자연어 요청의 지역 범위를 해석하는 GeoResolverAgent
- Human Approval Node
- workflow run 생성 시 `awaiting_approval`까지 rule-based 또는 Gemini 실행
- agent step, tool call, LLM call, latency, cost 기록 구조
- approval DB/API
- Result Review UI
- Run Detail UI
- 근거 문서 + QA issue 검토
- approve/reject/request changes 액션
- JSON export
- Gemini LLM gateway
- rule-based 생성 모드와 Gemini LLM 설정 전환
- Product, Marketing, QA/Compliance Agent Gemini 연결
- Gemini JSON 응답 검증과 실패 로그 기록
- Gemini 호출별 token, latency, cost 기록
- `backend/logs/llm_usage.jsonl`, `llm_usage.csv`, `llm_usage_summary.json` 파일 기반 LLM 사용량 로그
- `backend/logs/workflow_errors.jsonl`, `workflow_errors.log` 파일 기반 workflow 실패 로그
- Gemini 2.5 Flash-Lite paid tier 기준 예상 비용 기록
- Revision Workflow
- `workflow_runs.parent_run_id`, `revision_number`, `revision_mode` 저장
- request changes, 선택한 QA issue, QA 설정을 revision context로 전달
- `manual_save`, `manual_edit`, `llm_partial_rewrite`, `qa_only` revision mode
- 모든 revision은 최상위 원본 run 아래에 생성되고 `revision_number`만 증가
- manual save는 수정 내용을 새 revision run에 저장하고 QA를 다시 실행하지 않음
- manual edit은 수정한 products/marketing_assets를 새 revision run에 저장하고 QA만 재실행
- qa_only는 기존 결과를 유지하고 QA/Compliance Agent만 재실행
- llm_partial_rewrite는 전체 재생성 없이 선택한 QA issue와 requested changes를 기반으로 필요한 필드만 patch
- Result Review UI의 AI 수정/직접 수정/QA 재검수, revision metadata, revision history, manual edit form
- revision 실행 전 create run 때의 region/period/target/preferences/avoid 설정을 확인하고 수정 가능
- QA 메시지에서 `disclaimer`, `not_to_claim`, `sales_copy` 같은 내부 필드명은 사용자 친화적 라벨로 표시
- JSON export에 revision metadata 포함

## 사용하지 않는 것

- Tailwind CSS
- shadcn/ui
- Bootstrap
- React-Bootstrap

## TourAPI 설정

TourAPI는 실제 한국관광공사 API만 사용합니다. API 키가 없거나 호출이 실패하면 tool call과 workflow run이 실패 상태로 기록되고 FastAPI 로그에 에러가 출력됩니다.

```env
TOURAPI_SERVICE_KEY=
TOURAPI_DETAIL_ENRICHMENT_LIMIT=5
TOURAPI_CANDIDATE_SHORTLIST_LIMIT=20
ENRICHMENT_MAX_CALL_BUDGET=6
```

공공데이터포털에서 한국관광공사 국문 관광정보 서비스_GW 활용신청 후 키를 넣습니다.

```env
TOURAPI_SERVICE_KEY=your_tourapi_service_key
```

Phase 9.6부터 workflow 지역 검색은 기존 `areaCode`가 아니라 TourAPI v4.4 법정동 코드와 신분류체계 기준으로 동작합니다. 지역 catalog는 `ldongCode2?lDongListYn=Y` 전체 목록을 paging해 동기화합니다.

```bash
conda activate paravoca-ax-agent-studio
cd backend
python -m app.tools.sync_tourapi_catalogs
```

잘못 저장된 catalog를 다시 받을 때는 `python -m app.tools.sync_tourapi_catalogs --reset`을 실행합니다.

`GeoResolverAgent`는 사용자의 자연어 요청에서 지역 의도를 먼저 해석합니다. 공식 TourAPI `ldongCode2`로 동기화한 전국 시도/시군구 catalog를 먼저 확인하며, 코드에 특정 지명 예시를 하드코딩해 강제 매핑하지 않습니다. catalog가 비어 있으면 임의 값으로 추측하거나 전국 검색으로 넘어가지 않고 catalog 동기화가 필요하다고 중단합니다. 예를 들어 `대전 유성구`, `전남 장흥`, `부산 중구 남포동 일대`, `부산에서 시작해서 양산에서 끝나는 상품`처럼 행정구역명, 세부 동네명, route형 요청을 catalog 후보로 변환합니다. `전포동`처럼 TourAPI 검색 필터에 직접 넣을 수 없는 좁은 동네명은 상위 시군구가 확정된 경우 keyword로 유지합니다. UI는 별도 Region 입력을 받지 않고 자연어 요청을 기준으로 처리합니다. 확신이 낮거나 `중구`처럼 후보가 여러 개인 경우에는 전국 검색으로 넘어가지 않고 run status를 `failed`로 저장한 뒤 지역 후보 안내를 표시합니다. 전국 검색은 사용자가 `전국`, `국내 전체`처럼 명시한 경우에만 허용됩니다. `도쿄`, `오사카`, `파리` 같은 해외 목적지는 PARAVOCA의 현재 지원 범위 밖으로 판단해 검색을 시작하지 않습니다.

LLM 키는 로컬 개발/테스트에서는 필수는 아닙니다. `LLM_ENABLED=false`이면 Gemini 키 없이도 호환 workflow를 실행할 수 있습니다. 실제 LLM 연동과 신규 판단 Agent production 경로는 우선 Gemini만 사용합니다.

Gemini를 사용하려면 `.env`에 아래 값을 넣습니다.

```env
GEMINI_API_KEY=
GEMINI_CHECK_MODEL=gemini-2.5-flash-lite
GEMINI_GENERATION_MODEL=gemini-2.5-flash-lite
GEMINI_MAX_RETRIES=3
GEMINI_JSON_MAX_RETRIES=2
GEMINI_RETRY_BASE_SECONDS=1.5
GEMINI_RETRY_MAX_SECONDS=12
LLM_USAGE_LOG_DIR=logs
LLM_PROMPT_DEBUG_LOG_ENABLED=false
LLM_PROMPT_DEBUG_LOG_DIR=logs/prompt_debug
LLM_ENABLED=true
```

LLM mode:

- `LLM_ENABLED=false`: API 키 없이 로컬 개발/테스트를 실행하는 호환 모드입니다. Phase 10.2 신규 DataGap/Router/Planner/Fusion 판단은 Gemini production 경로가 기준이며, false 모드에서는 fake 결과를 꾸미지 않고 테스트 가능한 로컬 호환 계산만 수행합니다.
- `LLM_ENABLED=true`: Planner, GeoResolver, DataGapProfiler, ApiCapabilityRouter, 4개 API family planner, EvidenceFusion, ResearchSynthesis, Product, Marketing, QA와 AI revision patch가 Gemini를 호출합니다. BaselineDataAgent는 기본 수집을 담당하고, `EnrichmentExecutor`는 Gemini가 아니라 실제 provider/tool 실행만 담당합니다.
- `LLM_ENABLED=true`에서 Gemini 응답의 JSON 파싱/스키마 검증이 실패하면 `GEMINI_JSON_MAX_RETRIES` 횟수만큼 같은 provider로 다시 호출합니다.
- 재시도 후에도 Gemini 호출, JSON 검증, 한글 출력 검증이 실패하면 workflow run은 `failed`가 됩니다.
- 실패한 Agent는 `agent_steps.error`에 남고, Gemini 호출과 JSON 재시도 호출은 `llm_calls`에 token/latency/cost와 함께 저장됩니다. `data_summary` 같은 deterministic 수집 로그는 LLM 호출이 아니므로 새 run부터 `llm_calls`에 저장하지 않고 `agent_steps`/`tool_calls`에서 확인합니다.
- `LLM_PROMPT_DEBUG_LOG_ENABLED=true`이면 각 Gemini 호출의 전체 input prompt, schema가 포함된 full prompt, raw output, parsed JSON, error를 `LLM_PROMPT_DEBUG_LOG_DIR/<run_id>/` 아래에 agent/purpose별로 저장합니다. 기계 확인용 `*.json`과 사람이 읽기 쉬운 `*.md`가 함께 생성되며, Markdown 로그에서는 프롬프트와 응답이 이스케이프되지 않은 텍스트 블록으로 보입니다. prompt에는 사용자 요청과 source evidence가 포함될 수 있으므로 로컬 디버깅 때만 켭니다.

비용 주의:

- 기본 모델은 `gemini-2.5-flash-lite`입니다.
- DB의 `llm_calls.cost_usd`에는 Gemini 2.5 Flash-Lite paid tier 예상 비용을 기록합니다.
- 비용은 공식 invoice 조회값이 아니며 token usage와 코드의 pricing table 기준 추정치입니다.
- LLM 사용량 파일 로그는 기본적으로 `backend/logs` 아래에 저장됩니다.
  - `llm_usage.jsonl`: 호출별 상세 로그
  - `llm_usage.csv`: 스프레드시트로 열기 쉬운 호출별 로그
  - `llm_usage_summary.json`: 총 호출 수, 실패 수, token, 비용 합계와 provider/model/purpose별 집계
- Gemini API quota 제한에 걸리면 `Quota exceeded ... Please retry in N seconds` 에러가 발생하며, 해당 workflow run은 `failed`로 기록됩니다.
- Gemini 503 high demand/temporary overload 응답은 같은 모델로 짧게 재시도합니다. 재시도 후에도 실패하면 workflow run은 `failed`가 됩니다.
- Gemini가 JSON 뒤에 추가 객체나 설명을 붙인 경우 첫 JSON 객체를 우선 파싱하고, 파싱/스키마 검증이 불가능한 경우 Gemini JSON 재시도를 수행합니다.
- workflow 실패 traceback은 `backend/logs/workflow_errors.log`와 `backend/logs/workflow_errors.jsonl`에 저장됩니다.
- OpenAI/GPT는 현재 workflow에서 사용하지 않습니다.
- 웹 검색/Google Search grounding은 현재 workflow에 구현되어 있지 않습니다. P2 이후 Data Agent 보강 기능으로 추가하며, 기본값은 비활성화하고 run당 query/grounded prompt 한도를 둘 계획입니다.
- Google Cloud 가격표 기준으로 Gemini 2.0/2.5 Flash 계열의 Google Search grounding은 grounded prompt 단위로 계산됩니다. 하루 1,500 grounded prompts 추가요금 무료 구간은 검색 grounding 추가요금에 대한 것이며, 모델 token 비용은 별도입니다. Gemini 3 계열은 search query 단위 과금이 적용될 수 있어 별도 계산이 필요합니다.

## Local Semantic Embedding

기본 embedding provider는 빠른 개발과 기존 Chroma 호환을 위해 `legacy_hash`입니다. 실제 semantic retrieval을 확인하려면 로컬 `sentence-transformers` provider를 사용합니다. 이 방식은 Gemini/OpenAI embedding API를 호출하지 않으므로 embedding API 비용이 발생하지 않습니다.

```env
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_DEVICE=cpu
EMBEDDING_BATCH_SIZE=32
```

`EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, vector dimension이 바뀌면 기존 Chroma collection과 충돌할 수 있습니다. provider 또는 model 변경 후에는 reset reindex를 실행합니다.

```bash
conda activate paravoca-ax-agent-studio
cd backend
python -m pip install -e ".[dev]"
python -m app.rag.reindex --collection source_documents --reset
```

빠른 개발/테스트만 필요하면 `.env`에서 `EMBEDDING_PROVIDER=legacy_hash`를 유지할 수 있습니다. semantic retrieval 품질 확인과 데모 전 재색인은 `EMBEDDING_PROVIDER=local`에서 실행합니다.

## 로컬 실행

### 1. 환경변수 준비

```bash
cp .env.example .env
```

### 2. Backend

```bash
cd backend
conda create -y -n paravoca-ax-agent-studio python=3.11
conda activate paravoca-ax-agent-studio
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Backend URL:

```text
http://localhost:8000
```

Health check:

```bash
curl http://localhost:8000/api/health
```

Tourism search:

```bash
curl -G http://localhost:8000/api/data/tourism/search \
  --data-urlencode "ldong_regn_cd=26" \
  --data-urlencode "keyword=야경" \
  --data-urlencode "limit=5"
```

상세 보강까지 함께 확인하려면 `enrich_details=true`를 사용합니다. 이 호출은 검색 결과 중 지정한 개수에 대해 `detailCommon2`, `detailIntro2`, `detailInfo2`, `detailImage2`를 실제 TourAPI로 호출하고, `tourism_entities`, `tourism_visual_assets`, `source_documents`, Chroma index를 갱신합니다.

```bash
curl -G http://localhost:8000/api/data/tourism/search \
  --data-urlencode "ldong_regn_cd=30" \
  --data-urlencode "content_type=event" \
  --data-urlencode "start_date=2026-05-01" \
  --data-urlencode "limit=1" \
  --data-urlencode "enrich_details=true" \
  --data-urlencode "detail_limit=1"
```

이미 DB에 저장된 content_id를 상세 보강하려면:

```bash
curl -X POST http://localhost:8000/api/data/tourism/details/enrich \
  -H "Content-Type: application/json" \
  -d '{
    "content_ids": ["2786391"],
    "limit": 1
  }'
```

사용 가능한 데이터 source와 현재 활성화 여부는 아래 API로 확인합니다.

```bash
curl http://localhost:8000/api/data/sources/capabilities
```

Tool call logging까지 확인하려면 먼저 workflow run을 만들고 `run_id`를 검색 요청에 넘깁니다.

```bash
curl -X POST http://localhost:8000/api/workflow-runs \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": "default_product_planning",
    "input": {
      "message": "부산 외국인 야간 관광",
      "period": "2026-05",
      "target_customer": "외국인",
      "product_count": 3,
      "preferences": ["야간 관광"]
    }
}'
```

생성 응답은 즉시 `pending` 상태로 반환됩니다. 이후 백그라운드에서 Planner/GeoResolver/Data/Research/Product/Marketing/QA/Human Approval 단계가 실행되고, 완료되면 `awaiting_approval` 상태가 됩니다. 지역이 애매하면 `failed` 상태로 종료하되 지역 후보 안내를 보여주고, 해외 목적지처럼 PARAVOCA의 현재 지원 범위 밖이면 `unsupported`로 종료됩니다. 두 경우 모두 TourAPI 검색은 시작하지 않습니다.

```bash
curl -G http://localhost:8000/api/data/tourism/search \
  --data-urlencode "ldong_regn_cd=26" \
  --data-urlencode "keyword=야경" \
  --data-urlencode "run_id=RUN_ID_FROM_RESPONSE"
```

```bash
curl http://localhost:8000/api/workflow-runs/RUN_ID_FROM_RESPONSE/tool-calls
```

LLM call log:

```bash
curl http://localhost:8000/api/workflow-runs/RUN_ID_FROM_RESPONSE/llm-calls
```

Approval action:

```bash
curl -X POST http://localhost:8000/api/workflow-runs/RUN_ID_FROM_RESPONSE/approve \
  -H "Content-Type: application/json" \
  -d '{"reviewer": "operator", "comment": "Ready to publish"}'
```

```bash
curl -X POST http://localhost:8000/api/workflow-runs/RUN_ID_FROM_RESPONSE/request-changes \
  -H "Content-Type: application/json" \
  -d '{
    "reviewer": "operator",
    "comment": "Need clearer meeting point",
    "requested_changes": ["집결지 설명 보강"]
  }'
```

Revision run 생성:

```bash
curl -X POST http://localhost:8000/api/workflow-runs/RUN_ID_FROM_RESPONSE/revisions \
  -H "Content-Type: application/json" \
  -d '{
    "revision_mode": "llm_partial_rewrite",
    "comment": "Request changes 반영",
    "requested_changes": ["집결지 설명 보강", "과장 표현 완화"],
    "qa_issues": [
      {
        "product_id": "product_1",
        "severity": "medium",
        "type": "general",
        "message": "상세 설명에 과장 표현이 있습니다.",
        "suggested_fix": "완화된 표현으로 수정하세요."
      }
    ],
    "qa_settings": {
      "region": "부산",
      "period": "2026-05",
      "target_customer": "외국인",
      "product_count": 3,
      "preferences": ["야간 관광", "축제"],
      "avoid": ["가격 단정 표현", "과장 표현"],
      "output_language": "ko"
    }
  }'
```

QA만 다시 실행하려면:

```bash
curl -X POST http://localhost:8000/api/workflow-runs/RUN_ID_FROM_RESPONSE/revisions \
  -H "Content-Type: application/json" \
  -d '{
    "revision_mode": "qa_only",
    "requested_changes": ["고객 노출 문구만 다시 확인"],
    "qa_settings": {
      "region": "부산",
      "period": "2026-05",
      "target_customer": "외국인",
      "product_count": 3,
      "preferences": ["야간 관광", "축제"],
      "avoid": ["가격 단정 표현", "과장 표현"],
      "output_language": "ko"
    }
  }'
```

`manual_edit`은 frontend의 직접 수정 modal에서 수정한 products/marketing_assets를 함께 전송합니다. `manual_save`는 같은 payload를 저장하되 QA를 다시 실행하지 않습니다. `llm_partial_rewrite`는 Product/Marketing 전체를 다시 만들지 않고, 선택된 QA issue와 수정 요청에 해당하는 필드만 patch합니다.

RAG search:

```bash
curl -X POST http://localhost:8000/api/rag/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "광안리 야경 외국인 액티비티",
    "filters": {"ldong_regn_cd": "26"},
    "top_k": 5
  }'
```

Source document 재색인:

```bash
python -m app.rag.reindex --collection source_documents --reset
```

현재 `.env`의 `EMBEDDING_PROVIDER`와 `EMBEDDING_MODEL` 기준으로 Chroma `source_documents` collection을 다시 생성하고, DB의 `source_documents.embedding_status`를 `indexed` 또는 `failed`로 갱신합니다.

Phase 9.6 이후에는 source document metadata에 `ldong_regn_cd`, `ldong_signgu_cd`, `lcls_systm_1/2/3`가 추가됩니다. 기존 Chroma collection에는 이 metadata가 없으므로 provider/model 변경 여부와 관계없이 reset reindex를 실행해야 지역 filter가 정확히 적용됩니다.

Gemini key check:

```bash
curl -X POST http://localhost:8000/api/llm/key-check \
  -H "Content-Type: application/json" \
  -d '{"providers": ["gemini"], "max_output_tokens": 16}'
```

이 API는 실제 청구서를 조회하지 않습니다. API 응답의 token usage와 pricing table 기준 예상 비용을 `workflow_runs`와 `llm_calls`에 기록합니다.

Gemini workflow 실행:

```bash
LLM_ENABLED=true uvicorn app.main:app --reload
```

```bash
curl -X POST http://localhost:8000/api/workflow-runs \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": "default_product_planning",
    "input": {
      "message": "이번 달 부산에서 외국인 대상 액티비티 상품을 2개 기획해줘",
      "period": "2026-05",
      "target_customer": "외국인",
      "product_count": 2,
      "preferences": ["야간 관광", "축제"]
    }
}'
```

생성 응답은 먼저 `pending`으로 돌아옵니다. 잠시 후 run을 다시 조회했을 때 `awaiting_approval`이 되면 `final_output.agent_execution`에서 각 Agent가 `rule_based`인지 `gemini`인지 확인할 수 있습니다.

```bash
curl http://localhost:8000/api/workflow-runs/RUN_ID_FROM_RESPONSE/llm-calls
```

파일 로그로 전체 사용량을 빠르게 확인하려면 아래 파일을 봅니다.

```bash
cat backend/logs/llm_usage_summary.json
tail -n 20 backend/logs/llm_usage.jsonl
```

Gemini Agent가 실행되면 `llm_calls`에 아래 purpose가 `provider=gemini`로 저장됩니다.

```text
planner
geo_resolution
data_gap_profile
api_capability_routing
tourapi_detail_planning
visual_data_planning
route_signal_planning
theme_data_planning
evidence_fusion
research_synthesis
product_generation
marketing_generation
qa_review
revision_patch
```

### 3. Frontend

```bash
cd frontend
conda activate paravoca-ax-agent-studio
conda install -y -n paravoca-ax-agent-studio nodejs=20
npm install
npm run dev
```

Frontend URL:

```text
http://localhost:5173
```

## Docker 실행

```bash
cp .env.example .env
docker compose up --build
```

## 테스트

Backend:

```bash
cd backend
conda activate paravoca-ax-agent-studio
pytest
```

Frontend:

```bash
cd frontend
conda activate paravoca-ax-agent-studio
npm run build
```

로컬 PATH가 Homebrew Node를 먼저 잡아 빌드가 실패하면 conda env의 bin을 앞에 둡니다.

```bash
PATH="$CONDA_PREFIX/bin:$PATH" npm run build
```

현재 확인된 검증 결과:

- Backend: `76 passed`
- Frontend: production build 성공
- Frontend: `npm run build`의 TypeScript check와 Vite production build 통과
- `GET /api/health` 응답 확인
- `POST /api/workflow-runs`가 즉시 `pending`을 반환하고 백그라운드 실행 후 `awaiting_approval`까지 진행되는 것 확인
- approve/reject/request changes API 동작 확인
- 실제 TourAPI 키로 부산 행사/숙박 데이터 조회 확인
- Chroma RAG search 결과 반환 확인
- `agent_steps`, `tool_calls`, `llm_calls` 저장 확인
- Gemini key check 성공 확인: paid tier 예상 비용 기록
- `LLM_ENABLED=false` 로컬 호환 workflow 테스트 통과
- `LLM_ENABLED=true` Gemini workflow 1회 실행 확인
- Product/Marketing/QA Agent의 `llm_calls`가 `provider=gemini`로 저장되는 것 확인
- Gemini 2.5 Flash-Lite paid tier 기준 workflow 예상 비용 기록 확인
- request changes가 있는 run에서 revision run 생성 확인
- manual_edit revision에서 Product/Marketing 재생성 없이 QA만 재실행 확인
- llm_partial_rewrite revision에서 Product/Marketing 전체 재생성 없이 필요한 필드만 patch한 뒤 QA 재실행 확인
- parent/revision 관계가 DB와 UI에서 원본 run 중심으로 확인되는 것 확인
- revision 실행 전 run settings와 QA settings 확인/수정 UI 확인
- QA 메시지의 내부 필드명 노출 방지와 안전한 완화 문구 오판 방지 확인
- `/api/data/sources/capabilities` 응답 확인
- 실제 TourAPI 키로 부산 행사 1건 상세 보강 확인
- `detailCommon2`, `detailIntro2`, `detailInfo2`, `detailImage2` 호출과 저장 확인
- `tourism_entities` canonical entity 저장 확인
- `tourism_visual_assets` 이미지 후보 `candidate` 저장 확인
- Run Detail Evidence에서 상세 정보와 이미지 후보 표시 확인
- `legacy_hash` embedding provider routing과 RAG retrieval smoke test 확인
- source document reindex command 확인
- `GeoResolverAgent` 지역 해석 테스트 확인
- TourAPI v4.4 `ldong/lcls` metadata 기반 workflow 검색 테스트 확인
- 지역 해석 실패 시 전국 fallback 차단 테스트 확인

## 다음 Phase

Phase 10에서는 기존 Data 단계를 `BaselineDataAgent`로 분리하고, 수집된 TourAPI evidence의 공백을 분석한 뒤 필요한 KorService2 상세/이미지 보강만 선택적으로 실행하도록 변경했습니다. Phase 10.2에서는 `DataGapProfilerAgent`, `ApiCapabilityRouterAgent`, 4개 API family planner, `EvidenceFusionAgent`를 Gemini prompt + JSON schema 기반으로 전환했습니다. Baseline raw 후보는 `TOURAPI_CANDIDATE_SHORTLIST_LIMIT` 기준 shortlist로 줄인 뒤 Agent에 입력하고, KorService2 상세 보강은 shortlist 안에서 실행 가능한 `contentId` 대상을 임의 budget 6개로 자르지 않고 처리합니다. Router는 gap을 planner lane으로만 분배하고, `TourApiDetailPlannerAgent`, `VisualDataPlannerAgent`, `RouteSignalPlannerAgent`, `ThemeDataPlannerAgent`가 각자 필요한 짧은 입력만 보고 계획을 만듭니다. `DataGapProfilerAgent`와 `EvidenceFusionAgent`의 `maxOutputTokens`는 후보별 판단을 충분히 남길 수 있도록 16,384로 설정했습니다. 보강 결과는 `enrichment_runs`, `enrichment_tool_calls`, `tourism_entities`, `tourism_visual_assets`, `source_documents`에 남고, `EvidenceFusionAgent`는 전체 evidence profile을 다시 복사하지 않되 후보별 `candidate_evidence_cards`를 생성해 사용할 수 있는 사실, 경험 hook, 상품화 각도, 제한 claim, 운영자 확인 항목을 분리합니다.

Run 생성 전에는 `PreflightValidationAgent`가 요청 범위와 상품 개수 상한을 먼저 확인합니다. 자연어 요청이 관광 상품 기획과 무관하거나, 자연어에서 6개 이상 상품 생성을 요구하면 workflow run을 만들지 않고 생성 modal에서 바로 안내합니다.

Phase 10.1 AppShell Navbar and Global Navigation은 구현 완료되었습니다. 현재 frontend는 Mantine `AppShell.Header`/`AppShell.Navbar` 기반 전역 navigation shell을 사용합니다. Dashboard는 기존처럼 summary와 Runs table을 함께 보여주고, Workflow Preview는 전역 Navbar에서 독립적으로 접근합니다. Data Sources, Evaluation, Costs, Poster Studio, Settings는 아직 실제 기능이 연결되지 않은 `향후 연결 예정` placeholder입니다.

Phase 10.5 UI and Operations Surface Cleanup도 구현 완료되었습니다. Run Detail은 `Result Review`, `Evidence + QA`, `Developer` 탭으로 정리되어 있고, 일반 사용자 화면에서는 내부 agent/planner lane 대신 `요청 확인`, `지역 해석`, `관광 데이터 확인`, `보강 정보 확인`, `상품 초안 생성`, `검수 및 승인` 단계로 진행 상태를 보여줍니다. `agent_steps`, `tool_calls`, `llm_calls`, Raw JSON은 `Developer` 탭으로 이동했습니다. Data Coverage / Enrichment / Evidence는 충분/부족/확인 필요, 호출됨/보류됨/향후 연결 예정/실패함처럼 사람이 읽을 수 있는 상태 중심으로 표시합니다.

Phase 11 Evidence-based ProductAgent Actualization은 구현 완료되었습니다. Product/Marketing/QA는 `evidence_profile`, `productization_advice`, `data_coverage`, `unresolved_gaps`, `source_confidence`, `ui_highlights`를 공유하고, 근거 없는 운영시간/요금/예약/외국어/안전/의료/웰니스 claim은 `assumptions`, `not_to_claim`, `needs_review`, `claim_limits`로 분리합니다.

Phase 11.5 Gemini Planner/Research Actualization and LLM Call Surface Cleanup도 구현 완료되었습니다. `PlannerAgent`는 Gemini JSON schema 기반으로 요청 의도, 상품 개수, 선호/회피 조건, evidence requirement를 정리하고 지역 코드는 확정하지 않습니다. `ResearchSynthesisAgent`는 EvidenceFusion 직후 후보별 `candidate_evidence_cards`의 usable facts, operational unknowns, restricted claims, evidence document ids를 보존한 채 ProductAgent용 research brief를 만듭니다. `data_summary`는 LLM이 아니라 deterministic collection log였으므로 새 run부터 LLM Calls에 저장하지 않고, Developer UI의 LLM Calls tab은 Gemini 호출과 과거 run에 남아 있는 legacy/offline agent call을 표시하되 `data_summary` row만 숨깁니다. `ApiCapabilityRouterAgent`는 baseline 이후 gap을 보강 API family lane으로 분배하는 Agent이며, baseline 검색 전략을 세우는 future `BaselineSearchPlanner`/`TourAPIQueryPlanner`와는 별도 역할입니다.

다음 Phase는 Phase 12.1/12.2/12.3입니다. 99번 문서에 정리된 추가 KTO API를 실제 provider/executor로 붙이고, 가져온 데이터를 DB/source document/RAG/Product UI에 반영합니다. RAG retrieval recall, faithfulness, tool call accuracy, task success rate, cost per task, latency를 dataset 기반으로 측정하고 Evaluation Dashboard에서 확인하는 작업은 Phase 12 이후 운영/평가 단계에서 강화합니다.

별도 후속 Phase에서는 웹 검색/검색 grounding과 사용자 추가 정보 수집을 Data Agent 보강 기능으로 추가합니다. TourAPI에 없는 운영 시간, 예약 조건, 집결지, 가격/포함사항, 최신 행사 공지 같은 정보를 출처 URL과 조회 시각이 있는 `source=web` 근거로 저장하고, 공식 출처가 약한 정보는 `needs_review`로 분리합니다.

후속 Phase에서는 Poster Studio를 추가해 상품 기획 결과를 홍보 이미지 제작까지 확장합니다. 이 단계에서는 Poster Prompt Agent, poster option review UI, OpenAI Image API 기반 이미지 생성, poster asset 저장, 이미지 생성 비용 추적을 구현합니다.
