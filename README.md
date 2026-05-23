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
- Gemini API 기반 Agent workflow와 로컬 semantic embedding을 사용해 비싼 GPU나 embedding API 비용 없이 실무형 AI 자동화 흐름을 구성할 수 있습니다.
- 웹 검색/공식 웹 근거 수집은 현재 계획에서 제외하고, 공공 KTO/TourAPI 근거와 운영자 확인 항목 분리를 우선합니다.
- Poster Studio에서 Run Review 결과를 활용해 상품별 홍보 포스터 초안을 생성하고 다운로드할 수 있습니다.

## Poster Studio

Poster Studio는 workflow run 결과를 바탕으로 여행 상품 홍보 포스터 초안을 만드는 Phase 14 기능입니다. 상품 초안, 마케팅 카피, SNS 문구, claim 제한, 근거 요약을 사용자가 선택하면 서버가 영어 이미지 생성 프롬프트를 deterministic template으로 구성하고 OpenAI Image API로 이미지를 생성합니다. 생성 요청은 poster asset을 `running`으로 저장한 뒤 background task로 처리하므로, 사용자가 modal을 닫거나 화면을 이동해도 완료 후 Run Detail과 Poster Studio에서 같은 기록을 확인할 수 있습니다.

현재 workflow:

1. Run Detail의 상품 카드 또는 AppShell의 Poster Studio 탭에서 포스터 생성을 시작합니다.
2. 사용자가 포함할 내용 범위와 3개 style preset 중 하나를 선택합니다.
3. 선택한 상품의 근거 자료에 연결된 이미지 후보를 관련도 순서로 확인하고, 필요한 경우 최대 3개까지 참조 이미지로 선택합니다. 직접 URL 입력은 제공하지 않습니다.
4. 서버가 상품/마케팅/근거/claim 제한/선택 이미지 데이터를 기반으로 영어 프롬프트를 구성합니다.
5. OpenAI Image API가 `OPENAI_API_KEY`로 포스터 이미지를 생성합니다.
6. 생성된 포스터는 원본 run, 상품, 프롬프트, 선택 옵션, latency, 추정 비용과 함께 저장됩니다.
7. UI에서 포스터 초안을 바로 미리보고 다운로드합니다.
8. 상품 1개당 저장 가능한 포스터 초안은 최대 3개입니다. 기존 포스터를 삭제하면 다시 생성할 수 있습니다.

현재 선택 가능한 style preset:

- `editorial_travel`: 조용한 프리미엄 여행 매거진 스타일
- `night_city`: 야간 도시/로컬 경험 중심의 cinematic 스타일
- `minimal_event`: 정보가 명확한 미니멀 홍보 포스터 스타일

현재는 자유 prompt 입력이나 후보 여러 개 생성 후 선택하는 review flow를 제공하지 않습니다. 자유 커스터마이즈는 후속 단계에서 확장합니다. 기본 이미지 모델은 `gpt-image-2`, 기본 크기는 `1024x1536`, 기본 품질은 `medium`입니다. API key가 없거나 provider/storage 오류가 발생하면 fake poster를 만들지 않고 failed 상태와 에러를 표시합니다. 생성된 이미지는 게시 확정물이 아니라 포스터 초안 이미지입니다.

Run Detail과 Poster Studio의 참조 이미지 선택 UI는 동일한 원칙을 따릅니다. 상품 `source_ids`와 직접 연결된 evidence 이미지를 먼저 보여주고, 같은 `content_id`로 묶이는 후보를 그 다음에 보여줍니다. 후보는 작은 URL 목록이나 API 태그가 아니라 이미지명과 큰 thumbnail 카드로 표시하며, 이미지를 클릭하면 원본 이미지를 확대해서 확인할 수 있습니다.

Poster Studio의 run/product 선택은 텍스트 편집형 dropdown이 아니라 Dashboard table과 비슷한 compact row selector로 표시합니다. Dashboard run table에는 연결된 포스터 수가 있는 run에만 `Posters` 숫자를 표시합니다. 포스터와 참조 이미지 preview modal은 확대/축소를 지원하며, nested modal에서 `Esc`를 눌러도 가장 위의 창만 닫히도록 처리합니다.

비용은 OpenAI Image API 응답의 `usage`가 있으면 text input/image input/image output token별로 계산해 `poster_assets.cost_usd`와 `provider_response_summary.cost_breakdown`에 저장합니다. 응답에 usage가 없으면 prompt 글자 수와 size/quality별 image output token 표를 기준으로 추정합니다. Poster usage file log는 `backend/logs/poster_usage.jsonl`, `poster_usage.csv`, `poster_usage_summary.json`에 저장됩니다. 생성에 사용된 prompt는 사용자 화면에 기본 노출하지 않고 `backend/logs/poster_prompts/<run_id>/<poster_id>.json`과 `.md` 파일로 저장합니다.

## 공모전/포트폴리오 관점

이 프로젝트의 중심은 여행 상품화입니다. 공공 관광 데이터를 운영자가 바로 검토할 수 있는 상품 초안, 마케팅 문구, FAQ, 리스크 체크리스트, 승인 이력으로 연결합니다.

심사위원이나 채용 평가자가 확인할 수 있는 지점은 명확합니다.

- 여행 플랫폼 운영 업무의 실제 반복 작업을 모델링했습니다.
- 공공데이터를 비즈니스 업무 결과물로 변환합니다.
- LLM 생성 결과에 근거 문서, QA 검수, 사람 승인 절차를 붙였습니다.
- API 사용량, latency, 예상 비용을 기록해 운영 비용 감각을 보여줍니다.
- 작은 여행사와 지역 관광사업자도 접근 가능한 API 기반 구조를 지향합니다.

현재 구현 범위는 Phase 0부터 Phase 16까지입니다.

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
- `GET /api/evaluations`
- `GET /api/evaluations/{eval_id}`
- `GET /api/evaluations/{eval_id}/cases`
- `GET /api/posters`
- `GET /api/posters/{poster_id}`
- `GET /api/posters/{poster_id}/download`
- `GET /api/workflow-runs/{run_id}/posters`
- `POST /api/workflow-runs/{run_id}/products/{product_id}/posters`
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
- 로컬 `sentence-transformers` semantic embedding provider
- source document 재색인 command
- source document role/origin/lifecycle metadata
- RAG query/filter/retrieval diagnostics
- KTO API capability catalog
- source family, trust level, license note, data quality metadata 저장 구조
- KTO 데이터 보강용 DB 모델 기본 구조
- `tourism_entities`, `tourism_visual_assets`, `tourism_route_assets`, `tourism_signal_records`
- `enrichment_runs`, `enrichment_tool_calls`
- KorService2 상세 보강 provider method
- `detailCommon2`, `detailIntro2`, `detailInfo2`, `detailImage2`
- `categoryCode2`, `locationBasedList2`
- TourAPI v4.4 `ldongCode2`, `lclsSystmCode2` catalog sync
- `PreflightValidationAgent` 기반 run 생성 전 지원 범위 검증
- 한 번의 workflow run에서 생성 가능한 상품 수는 최대 20개
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
- Visual 계열 KTO API provider/executor
- `kto_tourism_photo` `gallerySearchList1`, `kto_photo_contest` `phokoAwrdList`
- feature flag가 켜진 경우에만 관광사진/공모전 사진 이미지 후보 실제 조회
- visual API 결과를 `tourism_visual_assets`와 `source_documents`에 저장하고 Chroma에 색인
- 이미지 후보는 게시 확정 이미지가 아니라 `needs_license_review` 상태로 표시
- 보강된 source document를 Chroma에 재색인
- evidence profile, productization advice, data coverage, unresolved gaps, UI highlights 생성
- Run Detail Evidence에서 상세 정보와 이미지 후보 확인
- Run Detail Data Coverage와 Recommended Data Calls panel
- Run Detail QA Review에서 최초 실행 또는 마지막 revision QA 설정의 Avoid 기준 표시
- LangGraph workflow skeleton
- Planner, Baseline Data, Gap Profiling, API Routing, Data Enrichment, Evidence Fusion, Research Synthesis, Product, Marketing, QA/Compliance Agent
- Planner와 Data 사이에서 자연어 요청의 지역 범위를 해석하는 GeoResolverAgent
- Human Approval Node
- workflow run 생성 시 `awaiting_approval`까지 Gemini 기반 Agent workflow 실행
- agent step, tool call, LLM call, latency, cost 기록 구조
- approval DB/API
- Result Review UI
- Run Detail UI
- 근거 문서 + QA issue 검토
- approve/reject/request changes 액션
- JSON export
- Gemini LLM gateway
- Gemini LLM gateway와 호출별 JSON schema 검증
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
- llm_partial_rewrite는 전체 재생성 없이 선택한 QA issue가 가리키는 필드만 patch
- AI 수정과 QA 재검수는 선택한 QA issue만 targeted recheck하고, 선택하지 않은 기존 issue는 revision에 그대로 carryover
- QA report는 사용자-facing issue와 내부 진단을 분리하고, 고객 노출 문제 문구를 인용할 수 없는 issue는 기본 QA 목록에서 제외
- Result Review UI의 AI 수정/직접 수정/QA 재검수, revision metadata, revision history, manual edit form
- revision 실행 전 create run 때의 region/period/target/preferences/avoid 설정을 확인하고 수정 가능
- QA 메시지에서 `disclaimer`, `not_to_claim`, `sales_copy` 같은 내부 필드명은 사용자 친화적 라벨로 표시
- JSON export에 revision metadata 포함
- Evaluation dataset/runner
- `python -m app.evals.run_eval --dataset smoke --limit 5`
- 지역 해석, 데이터 수집, enrichment, evidence/product/QA claim 제한, 비용/latency 진단 metric
- 파일 기반 evaluation report 저장
- AppShell Evaluation Dashboard
- Poster Studio 탭
- Run Detail 상품별 `포스터 만들기`
- poster asset DB 저장과 `backend/data/poster_assets` 파일 저장
- OpenAI Image API 기반 `gpt-image-2` 포스터 생성
- 영어 template 기반 poster prompt builder
- style preset 3종과 포함 내용 선택
- poster preview/download UI

## 사용하지 않는 것

- Tailwind CSS
- shadcn/ui
- Bootstrap
- React-Bootstrap

## TourAPI 설정

TourAPI는 실제 한국관광공사 API만 사용합니다. API 키가 없거나 호출이 실패하면 tool call과 workflow run이 실패 상태로 기록되고 FastAPI 로그에 에러가 출력됩니다.

```env
TOURAPI_ENABLED=true
TOURAPI_SERVICE_KEY=
TOURAPI_TIMEOUT_SECONDS=20
TOURAPI_MAX_RETRIES=2
TOURAPI_RETRY_BASE_SECONDS=0.8
TOURAPI_RETRY_MAX_SECONDS=4
TOURAPI_DETAIL_ENRICHMENT_LIMIT=5
TOURAPI_CANDIDATE_SHORTLIST_LIMIT=20
ENRICHMENT_MAX_CALL_BUDGET=6
KTO_TOURISM_PHOTO_ENABLED=true
KTO_PHOTO_CONTEST_ENABLED=true
KTO_DURUNUBI_ENABLED=true
KTO_RELATED_PLACES_ENABLED=true
KTO_BIGDATA_ENABLED=true
KTO_CROWDING_ENABLED=true
KTO_REGIONAL_TOURISM_DEMAND_ENABLED=true
KTO_WELLNESS_ENABLED=true
KTO_PET_ENABLED=true
KTO_AUDIO_ENABLED=true
KTO_ECO_ENABLED=true
ALLOW_MEDICAL_API=false
```

BaselineDataAgent는 여러 TourAPI endpoint를 순서대로 호출합니다. 각 호출은 설정된 timeout/retry 정책을 따르며, retry 이후에도 endpoint 오류가 계속되면 실제 workflow와 evaluation 모두 해당 실패를 그대로 기록하고 run을 실패시킵니다. API는 정상 응답했지만 결과가 비어 있거나 검색 근거가 부족한 경우에는 `insufficient_source_data` 안내로 종료합니다.

Visual API flag를 켜면 Phase 12.1 visual enrichment가 관광사진/관광공모전 사진 후보를 실제로 조회합니다. 수집된 이미지는 `tourism_visual_assets`와 source document에 저장되지만, 기본 상태는 게시 확정이 아니라 `needs_license_review`입니다.

Route/Related/Demand Signal API flag를 켜면 Phase 12.2 enrichment가 두루누비 코스, 연관 관광지, 관광빅데이터 방문자 신호, 혼잡 예측, 지역 관광수요 신호를 실제로 조회합니다. 수집된 데이터는 `tourism_route_assets`, `tourism_signal_records`, `source_documents`에 저장되지만, 판매량/예약 가능성/안전 보장 claim이 아니라 보조 근거로만 사용합니다.

Theme API flag를 켜면 Phase 12.3 enrichment가 웰니스, 반려동물, 오디오, 생태 후보를 실제로 조회합니다. 의료관광은 `ALLOW_MEDICAL_API=true`일 때만 실제 호출합니다. 수집된 데이터는 `tourism_entities`, `tourism_visual_assets`, `source_documents`에 저장되지만, 건강 효능, 반려동물 동반 가능, 생태 효과, 오디오/다국어 제공 여부를 확정 claim으로 사용하지 않습니다.

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

`GeoResolverAgent`는 사용자의 자연어 요청에서 지역 의도를 먼저 해석합니다. 공식 TourAPI `ldongCode2`로 동기화한 전국 시도/시군구 catalog를 prompt에 포함하고, Gemini가 그 후보 중 실제 검색에 사용할 `resolved_locations`를 선택합니다. Python resolver는 Gemini가 고른 코드가 실제 catalog에 있는지, confidence가 충분한지 검증합니다. 코드에 특정 지명 예시를 하드코딩해 강제 매핑하지 않으며, catalog가 비어 있으면 임의 값으로 추측하거나 전국 검색으로 넘어가지 않고 catalog 동기화가 필요하다고 중단합니다. 예를 들어 `대전 유성구`, `전남 장흥`, `부산 중구 남포동 일대`처럼 행정구역명과 세부 동네명을 catalog 후보로 변환합니다. `전포동`, `대청도`처럼 TourAPI 검색 필터에 직접 넣을 수 없는 좁은 지명은 상위 시군구가 확정된 경우 keyword로 유지하고, 수집 후 item/document title/address/content/metadata에 해당 keyword가 있는 근거만 남깁니다. UI는 별도 Region 입력을 받지 않고 자연어 요청을 기준으로 처리합니다. 확신이 낮거나 `중구`처럼 후보가 여러 개인 경우에는 전국 검색으로 넘어가지 않고 run status를 `failed`로 저장한 뒤 지역 후보 안내를 표시합니다. 지역 이동형 코스나 두 곳 이상의 지역을 한 번에 연결하는 요청도 현재는 지원하지 않으며, 감지된 후보 중 하나만 골라 다시 요청하라는 안내로 종료합니다. 전국 검색은 사용자가 `전국`, `국내 전체`처럼 명시한 경우에만 허용됩니다. `도쿄`, `오사카`, `파리` 같은 해외 목적지는 PARAVOCA의 현재 지원 범위 밖으로 판단해 검색을 시작하지 않습니다.

Gemini를 사용하려면 `.env`에 아래 값을 넣습니다.

```env
GEMINI_API_KEY=
GEMINI_CHECK_MODEL=gemini-2.5-flash-lite
GEMINI_GENERATION_MODEL=gemini-2.5-flash-lite
GEMINI_TIMEOUT_SECONDS=60
GEMINI_MAX_RETRIES=5
GEMINI_JSON_MAX_RETRIES=2
GEMINI_RETRY_BASE_SECONDS=2
GEMINI_RETRY_MAX_SECONDS=30
LLM_USAGE_LOG_DIR=logs
LLM_PROMPT_DEBUG_LOG_ENABLED=false
LLM_PROMPT_DEBUG_LOG_DIR=logs/prompt_debug
EVALUATION_REPORT_DIR=reports/evaluations
```

LLM mode:

- Planner, GeoResolver, DataGapProfiler, ApiCapabilityRouter, 4개 API family planner, EvidenceFusion, ResearchSynthesis, Product, Marketing, QA와 AI revision patch가 Gemini를 호출합니다. BaselineDataAgent는 기본 수집을 담당하고, `EnrichmentExecutor`는 Gemini가 아니라 실제 provider/tool 실행만 담당합니다.
- Gemini 응답의 JSON 파싱/스키마 검증이 실패하면 `GEMINI_JSON_MAX_RETRIES` 횟수만큼 같은 provider로 다시 호출합니다.
- `GEMINI_TIMEOUT_SECONDS`는 Gemini HTTP 호출 timeout입니다. `ResearchSynthesisAgent`는 정상 호출에서 최대 8,192 output token을 사용하고, timeout이 발생하면 `research_synthesis_compact_retry`로 최대 4,096 output token의 compact 재시도를 수행합니다. compact 재시도에서도 원본 evidence는 서버 state에 보존되고, Research 출력은 상품화 판단과 risk guidance만 보강합니다.
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

## Evaluation

Phase 13부터 workflow 품질을 케이스별로 진단하는 evaluation runner와 Dashboard를 제공합니다. 평가는 LLM 문장 품질만 보지 않고 지역 해석, TourAPI/KTO 수집, RAG 검색, enrichment 호출, source_id 연결, evidence 기반 상품 생성, QA claim 제한, 비용과 latency를 함께 확인합니다. 웹 검색/공식 웹 근거 수집은 평가 대상에서 제외합니다.

```bash
conda activate paravoca-ax-agent-studio
cd backend
python -m app.evals.run_eval --dataset smoke --limit 5
python -m app.evals.run_eval --dataset smoke --name "Phase 13 live smoke 5 cases" --limit 5 --sleep-between-cases 5 --stop-on-first-failure
python -m app.evals.run_eval --dataset smoke --case-id smoke_visual_api --output-json
python -m app.evals.run_eval --dataset smoke --limit 3 --no-live-api
python -m app.evals.run_eval --dataset regression --name "Regression live" --sleep-between-cases 5
python -m app.evals.run_eval --dataset quality --name "Quality judge live" --enable-llm-judge --sleep-between-cases 5
```

결과는 기본적으로 `backend/reports/evaluations`에 JSON으로 저장되고, `--output-md`를 주면 Markdown report도 함께 생성됩니다. `--name`을 주면 Evaluation 화면에서 dataset 이름 대신 사람이 읽기 쉬운 실행명이 먼저 표시됩니다. `.env`에 실제 `TOURAPI_SERVICE_KEY`가 없거나 `--no-live-api`를 사용하면 live API가 필요한 케이스는 실패처럼 꾸미지 않고 `skipped`로 기록합니다.

Dataset은 세 가지입니다. `smoke`는 핵심 workflow 생존 확인, `regression`은 과거에 실제로 깨졌던 지역/claim/API 케이스 재발 방지, `quality`는 `--enable-llm-judge`와 함께 상품성, 근거 활용, 마케팅 품질, 암시적 claim 위험을 Gemini judge로 보조 평가하는 실행용 dataset입니다. Judge 모델은 `GEMINI_GENERATION_MODEL`을 사용하며 기본값은 `gemini-2.5-flash-lite`입니다.

Live eval은 여러 workflow를 연속 실행하므로 Gemini/KTO 호출이 짧은 시간에 몰릴 수 있습니다. 기본적으로 case 사이에 2초를 대기하며, `--sleep-between-cases`로 조절할 수 있습니다. `--stop-on-first-failure`는 첫 실패에서 멈춰 원인을 빠르게 확인할 때 사용합니다.

DataGapProfiler는 서버가 만든 gap inventory를 기준으로 Gemini가 필요한 gap ref/group만 선택하게 구성되어 있습니다. 후보별 상세 gap 객체와 원본 관광 후보 데이터는 서버가 보존하고, Gemini 출력은 그 참조와 우선순위 판단만 담습니다.

Frontend의 `Evaluation` 화면에서는 최근 eval run, pass/fail/skip summary, metric별 상태, case별 실패 원인, 연결된 workflow `run_id`, 비용/latency, source family coverage를 확인할 수 있습니다. Evaluation을 위해 생성된 workflow run은 일반 Dashboard 목록에서 숨기고 Evaluation 화면의 case detail에서 확인합니다. Evaluation report를 삭제하면 해당 report가 소유한 workflow run도 함께 삭제됩니다. `--reuse-run-id`로 기존 run을 평가한 경우에는 report만 삭제하고 원본 run은 삭제하지 않습니다.

실행 중인 workflow는 Run Detail에서 중지할 수 있습니다. 중지 요청을 보내면 사용자 화면과 DB 상태는 즉시 `cancelled`로 종료되고, 이미 진행 중이던 외부 LLM/KTO 요청이 늦게 반환되더라도 결과를 덮어쓰지 않습니다.

## 운영 로그와 실패 진단

- Gemini API quota 제한에 걸리면 `Quota exceeded ... Please retry in N seconds` 에러가 발생하며, 해당 workflow run은 `failed`로 기록됩니다.
- Gemini 503 high demand/temporary overload 응답은 같은 모델로 짧게 재시도합니다. 재시도 후에도 실패하면 workflow run은 `failed`가 됩니다.
- Gemini가 JSON 뒤에 추가 객체나 설명을 붙인 경우 첫 JSON 객체를 우선 파싱하고, 파싱/스키마 검증이 불가능한 경우 Gemini JSON 재시도를 수행합니다.
- workflow 실패 traceback은 `backend/logs/workflow_errors.log`와 `backend/logs/workflow_errors.jsonl`에 저장됩니다.
- OpenAI/GPT는 상품 생성 workflow 본체에서는 사용하지 않습니다. Poster Studio 이미지 생성에서만 `.env`의 `OPENAI_API_KEY`를 사용합니다.
- 웹 검색/Google Search grounding은 현재 계획에서 제외되어 있으며 workflow와 evaluation 대상에 포함하지 않습니다.

## Local Semantic Embedding

RAG 검색은 로컬 `sentence-transformers` semantic embedding으로 동작합니다. 기본 모델은 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`이며, Gemini/OpenAI embedding API를 호출하지 않으므로 embedding API 비용이 발생하지 않습니다.

```env
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_DEVICE=cpu
EMBEDDING_BATCH_SIZE=32
```

`EMBEDDING_MODEL` 또는 vector dimension이 바뀌면 Chroma collection과 충돌할 수 있습니다. 모델 변경 후에는 reset reindex를 실행합니다.

Source document는 `runtime_run_evidence`, `existing_catalog`, `seed_catalog`, `manual_ingestion`, `enrichment_result`, `unknown` 역할로 구분됩니다. RAG 검색은 확인된 지역 code, source family, content type, theme, target customer, narrow keyword를 반영하고, 검색 결과가 부족해도 상위 지역/전국/generic evidence로 자동 확장하지 않습니다. 사용한 query/filter/result count/matching signal은 `retrieval_diagnostics`에서 확인합니다.

```bash
conda activate paravoca-ax-agent-studio
cd backend
python -m pip install -e ".[dev]"
python -m app.rag.reindex --collection source_documents --reset
```

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
    "comment": "선택한 QA 이슈 수정",
    "qa_issues": [
      {
        "product_id": "product_1",
        "severity": "medium",
        "type": "source_missing",
        "field_path": "sales_copy.sections[0].body",
        "message": "상세 설명에 문제 문구 '예약 즉시 확정'이 있습니다. 예약 가능 여부를 단정하고 있습니다.",
        "suggested_fix": "예약 확정 여부는 운영자 확인 후 안내한다고 수정하세요."
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
    "qa_issues": [
      {
        "product_id": "product_1",
        "severity": "medium",
        "type": "source_missing",
        "field_path": "sales_copy.sections[0].body",
        "message": "상세 설명에 문제 문구 '예약 즉시 확정'이 있습니다. 예약 가능 여부를 단정하고 있습니다.",
        "suggested_fix": "예약 확정 여부는 운영자 확인 후 안내한다고 수정하세요."
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

`manual_edit`은 frontend의 직접 수정 modal에서 수정한 products/marketing_assets와 현재 QA issue 목록을 함께 전송합니다. 사용자는 직접 수정 창 안에서 전체 QA issue를 왼쪽 열로 보면서 오른쪽 편집 영역에서 전체 상품/마케팅 내용을 수정할 수 있습니다. `manual_save`는 같은 payload를 저장하되 QA를 다시 실행하지 않습니다. `llm_partial_rewrite`는 Product/Marketing 전체를 다시 만들지 않고, 선택된 QA issue가 가리키는 field path만 patch합니다. AI 수정과 QA 재검수는 새 문제를 찾는 broad QA가 아니라 선택한 QA issue가 해결됐는지만 확인하는 targeted QA입니다. 선택하지 않은 기존 QA issue는 사라진 것처럼 보이지 않도록 revision 결과에 그대로 남깁니다.

RAG search:

```bash
curl -X POST http://localhost:8000/api/rag/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "광안리 야경 외국인 액티비티",
    "filters": {"source": "tourapi", "source_family": "kto_tourapi_kor", "ldong_regn_cd": "26"},
    "top_k": 5,
    "search_context": {
      "target_customer": "외국인",
      "preferred_themes": ["야경", "해변"],
      "narrow_keywords": ["광안리"]
    }
  }'
```

Source document 재색인:

```bash
python -m app.rag.reindex --collection source_documents --reset
```

현재 `.env`의 `EMBEDDING_MODEL` 기준으로 Chroma `source_documents` collection을 다시 생성하고, DB의 `source_documents.embedding_status`를 `indexed` 또는 `failed`로 갱신합니다.

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
uvicorn app.main:app --reload
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

생성 응답은 먼저 `pending`으로 돌아옵니다. 잠시 후 run을 다시 조회했을 때 `awaiting_approval`이 되면 `final_output.agent_execution`에서 각 Agent 실행 결과를 확인할 수 있습니다.

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

- Backend: `conda run -n paravoca-ax-agent-studio pytest -q backend/app/tests` 기준 `161 passed, 2 skipped`
- Frontend: production build 성공
- Frontend: `npm run build`의 TypeScript check와 Vite production build 통과
- `GET /api/health` 응답 확인
- `POST /api/workflow-runs`가 즉시 `pending`을 반환하고 백그라운드 실행 후 `awaiting_approval`까지 진행되는 것 확인
- approve/reject/request changes API 동작 확인
- 실제 TourAPI 키로 부산 행사/숙박 데이터 조회 확인
- Chroma RAG search 결과 반환 확인
- `agent_steps`, `tool_calls`, `llm_calls` 저장 확인
- Gemini key check 성공 확인: paid tier 예상 비용 기록
- Gemini workflow 1회 실행 확인
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
- 로컬 sentence-transformers embedding 기반 RAG retrieval smoke test 확인
- source document reindex command 확인
- `GeoResolverAgent` 지역 해석 테스트 확인
- TourAPI v4.4 `ldong/lcls` metadata 기반 workflow 검색 테스트 확인
- 지역 해석 실패 시 전국 fallback 차단 테스트 확인
- Phase 16 QA hardening 확인: 사용자-facing QA issue와 내부 진단 분리, 안전한 불확실성 표현 false positive 방지, 선택 QA issue만 targeted revision recheck, 선택하지 않은 기존 issue carryover, AI patch field scope 제한

## 다음 Phase

Phase 10에서는 기존 Data 단계를 `BaselineDataAgent`로 분리하고, 수집된 TourAPI evidence의 공백을 분석한 뒤 필요한 KorService2 상세/이미지 보강만 선택적으로 실행하도록 변경했습니다. Phase 10.2에서는 `DataGapProfilerAgent`, `ApiCapabilityRouterAgent`, 4개 API family planner, `EvidenceFusionAgent`를 Gemini prompt + JSON schema 기반으로 전환했습니다. Baseline raw 후보는 `TOURAPI_CANDIDATE_SHORTLIST_LIMIT` 기준 shortlist로 줄인 뒤 Agent에 입력하고, KorService2 상세 보강은 shortlist 안에서 실행 가능한 `contentId` 대상을 임의 budget 6개로 자르지 않고 처리합니다. Router는 gap을 planner lane으로만 분배하고, `TourApiDetailPlannerAgent`, `VisualDataPlannerAgent`, `RouteSignalPlannerAgent`, `ThemeDataPlannerAgent`가 각자 필요한 짧은 입력만 보고 계획을 만듭니다. Phase 12.0에서는 `DataGapProfilerAgent`가 반복적인 `missing_overview`를 후보마다 길게 펼치지 않도록 `missing_detail_info`로 통합하고, item-level gap을 후보당 최대 1개, 전체 gap을 최대 24개로 제한했습니다. Phase 12.1에서는 `VisualDataPlannerAgent`가 활성화된 `kto_tourism_photo`/`kto_photo_contest` source family에 한해 실제 visual API call을 계획하고, `EnrichmentExecutor`가 이미지 후보를 `tourism_visual_assets`와 `source_documents`에 저장합니다. Phase 12.2에서는 `RouteSignalPlannerAgent`가 활성화된 `kto_durunubi`, `kto_related_places`, `kto_tourism_bigdata`, `kto_crowding_forecast`, `kto_regional_tourism_demand` source family에 한해 route/signal API call을 계획하고, `EnrichmentExecutor`가 코스 후보와 보조 신호를 `tourism_route_assets`, `tourism_signal_records`, `source_documents`에 저장합니다. Phase 12.3에서는 `ThemeDataPlannerAgent`가 활성화된 `kto_wellness`, `kto_pet`, `kto_audio`, `kto_eco`, `kto_medical` source family에 한해 theme API call을 계획하고, `EnrichmentExecutor`가 테마 후보를 `tourism_entities`, `tourism_visual_assets`, `source_documents`에 저장합니다. 의료관광은 `ALLOW_MEDICAL_API=true`일 때만 실제 호출합니다. 보강 결과는 `enrichment_runs`, `enrichment_tool_calls`, `tourism_entities`, `tourism_visual_assets`, `tourism_route_assets`, `tourism_signal_records`, `source_documents`에 남고, `EvidenceFusionAgent`는 전체 evidence profile을 다시 복사하지 않되 후보별 `candidate_evidence_cards`를 생성해 사용할 수 있는 사실, 이미지 후보, route/signal 보조 근거, theme 후보, 경험 hook, 상품화 각도, 제한 claim, 운영자 확인 항목을 분리합니다.

Run 생성 전에는 `PreflightValidationAgent`가 요청 범위와 상품 개수 상한을 먼저 확인합니다. 자연어 요청이 관광 상품 기획과 무관하거나, 자연어에서 21개 이상 상품 생성을 요구하면 workflow run을 만들지 않고 생성 modal에서 바로 안내합니다. 상품 생성은 최대 20개까지 허용하며, 직접 연결 가능한 근거 데이터가 요청 수보다 적어도 상품 개수를 줄이지 않습니다. 직접 근거가 부족한 상품은 `source_ids`를 빈 배열로 두고 부족 사유를 `needs_review`/`coverage_notes`에 남깁니다.

Phase 10.1 AppShell Navbar and Global Navigation은 구현 완료되었습니다. 현재 frontend는 Mantine `AppShell.Header`/`AppShell.Navbar` 기반 전역 navigation shell을 사용합니다. Dashboard는 기존처럼 summary와 Runs table을 함께 보여주고, Workflow Preview는 전역 Navbar에서 독립적으로 접근합니다. Evaluation은 Phase 13에서 실제 화면으로 전환되었고, Poster Studio는 Phase 14에서 실제 생성 화면으로 전환되었습니다. Costs와 Settings는 아직 실제 기능이 연결되지 않은 `향후 연결 예정` placeholder입니다.

Phase 10.5 UI and Operations Surface Cleanup도 구현 완료되었습니다. Run Detail은 `Result Review`, `Evidence + QA`, `Developer` 탭으로 정리되어 있고, 일반 사용자 화면에서는 내부 agent/planner lane 대신 `요청 확인`, `지역 해석`, `관광 데이터 확인`, `보강 정보 확인`, `상품 초안 생성`, `검수 및 승인` 단계로 진행 상태를 보여줍니다. `agent_steps`, `tool_calls`, `llm_calls`, Raw JSON은 `Developer` 탭으로 이동했습니다. Data Coverage / Enrichment / Evidence는 충분/부족/확인 필요, 호출됨/보류됨/향후 연결 예정/실패함처럼 사람이 읽을 수 있는 상태 중심으로 표시합니다.

Phase 11 Evidence-based ProductAgent Actualization은 구현 완료되었습니다. Product/Marketing/QA는 `evidence_profile`, `productization_advice`, `data_coverage`, `unresolved_gaps`, `source_confidence`, `ui_highlights`를 공유하고, 근거 없는 운영시간/요금/예약/외국어/안전/의료/웰니스 claim은 `assumptions`, `not_to_claim`, `needs_review`, `claim_limits`로 분리합니다.

Phase 11.5 Gemini Planner/Research Actualization and LLM Call Surface Cleanup도 구현 완료되었습니다. `PlannerAgent`는 Gemini JSON schema 기반으로 요청 의도, 상품 개수, 선호/회피 조건, evidence requirement를 정리하고 지역 코드는 확정하지 않습니다. `ResearchSynthesisAgent`는 EvidenceFusion 직후 후보별 `candidate_evidence_cards`의 usable facts, operational unknowns, restricted claims, evidence document ids를 보존한 채 ProductAgent용 research brief를 만듭니다. Developer UI의 LLM Calls tab은 Gemini 호출과 agent call 기록을 표시합니다. `ApiCapabilityRouterAgent`는 baseline 이후 gap을 보강 API family lane으로 분배하는 Agent이며, baseline 검색 전략을 세우는 future `BaselineSearchPlanner`/`TourAPIQueryPlanner`와는 별도 역할입니다.

Phase 12.0 Data Retrieval Stability and Empty Result UX도 구현 완료되었습니다. Chroma metadata filter를 query `where` 조건에 먼저 적용하고, TourAPI raw 수집 수, geo-filter 수, source document upsert/indexing 수, vector search filter/result 수를 retrieval diagnostics로 남깁니다. 특정 지역/조건에서 근거가 부족하면 내부 stack trace 대신 `insufficient_source_data` final output과 사용자 안내를 보여주며, 자동으로 상위 지역이나 전국으로 넓히지 않습니다. GeoResolverAgent는 catalog 후보 중 `resolved_locations`를 Gemini가 선택하고, `대청도`처럼 상위 시군구 코드로만 검색 가능한 좁은 지명은 keyword로 보존해 수집 후 item/document를 다시 좁힙니다.

Phase 12.2 Route/Related/Demand Signal API 연결도 구현 완료되었습니다. 두루누비, 연관 관광지, 관광빅데이터, 혼잡 예측, 지역 관광수요 API는 실제 호출된 경우에만 route asset/signal record/source document로 저장되며, API 결과 0개는 workflow 실패가 아니라 후보 없음으로 기록합니다. 이 데이터는 동선과 우선순위 판단 보조 근거이며, 판매량/예약 가능성/안전 보장 claim으로 사용하지 않습니다.

Phase 12.3 Theme API 연결도 구현 완료되었습니다. 웰니스, 반려동물, 오디오, 생태, 의료관광 API는 실제 호출된 경우에만 theme candidate/source document/visual asset 후보로 저장되며, API 결과 0개는 workflow 실패가 아니라 후보 없음으로 기록합니다. 이 데이터는 테마 상품화 보조 근거이며, 의료/웰니스 효능, 반려동물 허용, 생태 효과, 오디오/다국어 제공 여부는 운영자 확인 없이 단정하지 않습니다.

Phase 13 Evaluation and Quality Dashboard도 구현 완료되었습니다.

Phase 14 Poster Studio도 구현 완료되었습니다. Run Detail과 Poster Studio 탭에서 상품별 포스터 초안을 생성할 수 있고, 생성 결과는 poster asset DB row와 이미지 파일로 저장됩니다. prompt는 영어 template 기반이며, claim 제한과 확인 필요 항목은 visible copy가 아니라 이미지 생성 constraints로 들어갑니다.

Phase 15 Quality Audit은 완료되었습니다. 지정된 9개 run을 기준으로 QA, Marketing, RAG/Evidence, Image candidate selection, UI copy 문제를 각각 문서화했고, revision QA regression은 별도 15.1 문서로 정리했습니다.

Phase 16 QA Quality Hardening도 구현 완료되었습니다. QA는 사용자 `avoid`와 명백한 evidence risk 중심으로 좁히고, copy 품질 평가는 QA evidence-risk 검수에서 제외합니다. 사용자-facing QA message는 실제 문제 문구를 인용하도록 보정하고, `source_id`, `field_path`, `missing_pet_policy`, source-id correction 같은 내부 진단은 기본 QA 목록에서 분리합니다. AI 수정/QA 재검수는 선택한 QA issue만 targeted recheck하며, 선택하지 않은 기존 issue는 revision에서 그대로 유지됩니다. 직접 수정 modal은 왼쪽에서 전체 QA issue를 참고하고 오른쪽에서 전체 상품/마케팅 내용을 편집하는 구조입니다.

Phase 17.1 Source/RAG Structure Cleanup도 구현 완료되었습니다. Source document role/origin/lifecycle metadata를 추가하고, RAG 검색에 지역/theme/content type/target customer/narrow keyword를 반영하며, 검색 부족 시 자동 fallback 없이 retrieval diagnostics에 query/filter/result count/reason을 남깁니다.

다음 순서는 Phase 17.2 Product-level Evidence Bundle, Phase 17.3 source_id 검증과 Revision 안정화입니다. 이후 Phase 18 Evidence and Visual Evidence UX Redesign, Phase 19 Marketing Output Hardening, Phase 20 UI Copy and Product Surface Polish, Phase 21 Costs Dashboard, Phase 22 Deployment / Demo Hardening 순서로 진행합니다.
