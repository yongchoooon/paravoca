# Phase 10.2 Gemini Data Enrichment Agent 전환

작성 기준일: 2026-05-09

구현 상태: 완료

## 목적

Phase 10.2는 Phase 10에서 만든 Data Enrichment workflow를 실제 운영 가능한 Agent 구조에 가깝게 정리한 단계입니다.

핵심 목표는 세 가지입니다.

- DataGap, API Routing, API Planner, Evidence Fusion 판단을 Gemini prompt + strict JSON schema 기반으로 전환한다.
- 99번 KTO API 명세를 바탕으로 어떤 API가 어떤 정보 공백을 채울 수 있는지 capability로 정리하되, Agent prompt에는 필요한 요약만 넣는다.
- Product/Marketing/QA가 이후 Phase에서 활용할 수 있는 `evidence_profile`, `productization_advice`, `data_coverage`, `unresolved_gaps`, `ui_highlights`를 만든다.

## 현재 Workflow

Run 생성 전:

```text
PreflightValidationAgent
  -> 지원 범위 확인
  -> 상품 수 상한 5개 확인
  -> 통과한 요청만 workflow run 생성
```

Run 생성 후:

```text
Planner
  -> GeoResolverAgent
  -> BaselineDataAgent
  -> DataGapProfilerAgent
  -> 보강 필요?
     -> ApiCapabilityRouterAgent
     -> TourApiDetailPlannerAgent
     -> VisualDataPlannerAgent
     -> RouteSignalPlannerAgent
     -> ThemeDataPlannerAgent
     -> EnrichmentExecutor
     -> EvidenceFusionAgent
  -> Research
  -> Product
  -> Marketing
  -> QA
  -> Human Approval
```

`EnrichmentExecutor`는 Agent가 아닙니다. Gemini가 만든 plan을 받아 실제 provider/tool call을 실행하는 deterministic code action입니다.

## 실행 전 검증

Run 생성 modal에서 workflow run을 만들기 전에 `PreflightValidationAgent`가 요청을 검증합니다.

검증 항목:

- 관광 상품 기획과 무관한 요청 차단
- 국내 관광 데이터 지원 범위 확인
- 자연어에 6개 이상 상품 생성 요청이 들어오면 차단
- schema의 `product_count`도 최대 5개로 제한

Preflight 실패는 run review 단계로 넘어가지 않습니다. 생성 화면에서 사용자에게 안내만 표시합니다.

## Baseline Data와 Shortlist

`BaselineDataAgent`는 GeoResolver가 확정한 `geo_scope` 기준으로 TourAPI 기본 후보를 수집합니다.

현재 호출하는 기본 TourAPI:

- `searchKeyword2`
- `areaBasedList2` 관광지
- `areaBasedList2` 레포츠
- `searchFestival2`
- `searchStay2`
- Chroma vector search

수집된 raw 후보 전체를 그대로 Gemini Agent에 넣지 않습니다. raw 후보는 먼저 shortlist로 줄입니다.

설정:

```env
TOURAPI_CANDIDATE_SHORTLIST_LIMIT=20
```

shortlist 기준:

- 요청 테마와 content type 적합도
- `content_id` 존재 여부
- 이미지/개요 존재 여부
- 행사/레포츠/관광지 우선순위
- 숙박은 숙박 요청이 없으면 낮은 우선순위
- RAG top result에 포함된 후보 가산

`candidate_pool_summary`에는 raw 후보 수, shortlist 수, content type별 분포를 저장합니다. Agent에는 raw 전체 대신 shortlist와 요약만 전달합니다.

## DataGapProfilerAgent

역할:

현재 shortlist 후보를 보고 상품화에 필요한 근거 중 부족한 항목을 찾습니다.

입력:

- 사용자 요청
- GeoResolver 결과
- `candidate_pool_summary`
- shortlist `source_items`
- RAG `retrieved_documents`
- 자연어 `api_capability_brief`

중요한 변경:

- 거대한 `kto_api_capability_matrix` JSON을 더 이상 prompt에 넣지 않습니다.
- API 명세 전체가 아니라 “어떤 API가 어떤 정보를 줄 수 있는지”만 자연어 요약으로 전달합니다.
- shortlist 밖 raw 후보에 대해서는 개별 gap을 만들지 않습니다.
- `data_gap_profile`의 `maxOutputTokens`는 16,384로 설정합니다.

출력:

- `gaps[]`
- `coverage`
- `reasoning_summary`
- `needs_review`

지원 gap 예:

- `missing_detail_info`
- `missing_image_asset`
- `missing_operating_hours`
- `missing_price_or_fee`
- `missing_booking_info`
- `missing_related_places`
- `missing_route_context`
- `missing_theme_specific_data`

## ApiCapabilityRouterAgent

역할:

gap report를 보고 어떤 planner lane이 담당해야 하는지만 분류합니다.

입력:

- compact gap report
- 4개 planner lane 설명
- feature flag 상태
- non-core/future API용 budget

출력:

- `family_routes[]`
- `skipped_routes[]`
- `routing_reasoning`

Router는 endpoint, request argument, 실제 tool call JSON을 만들지 않습니다. 이 역할은 각 planner와 executor가 나눠서 처리합니다.

## API Family Planner

### TourApiDetailPlannerAgent

역할:

KorService2 상세 보강 대상만 선택합니다.

실행 가능한 보강:

- `detailCommon2`
- `detailIntro2`
- `detailInfo2`
- `detailImage2`

중요한 정책:

- shortlist 안에서 `content_id`가 있고 상세 보강 가능한 대상은 임의로 6개만 고르지 않습니다.
- `ENRICHMENT_MAX_CALL_BUDGET=6`은 core KorService2 상세 보강을 자르는 용도가 아닙니다.
- Gemini가 일부 대상만 출력해도 backend normalize 단계에서 실행 가능한 상세 보강 대상은 자동 포함합니다.
- request-level gap처럼 특정 `content_id`가 없는 항목은 상세 API를 직접 호출할 수 없으므로 skipped 처리합니다.

현재 `TourApiDetailPlannerAgent`의 `max_output_tokens`는 8192입니다. compact output schema는 유지합니다.

출력:

- `selected_targets[]`
- `skipped_gap_ids[]`
- `planning_reasoning`

### VisualDataPlannerAgent

대상 API:

- `kto_tourism_photo`
- `kto_photo_contest`

현재 상태:

- Phase 10.2에서는 capability routing과 skipped/future 기록까지만 합니다.
- 실제 provider/executor 연결은 Phase 12.1 범위입니다.

### RouteSignalPlannerAgent

대상 API:

- `kto_durunubi`
- `kto_related_places`
- `kto_tourism_bigdata`
- `kto_crowding_forecast`
- `kto_regional_tourism_demand`

현재 상태:

- Phase 10.2에서는 capability routing과 skipped/future 기록까지만 합니다.
- 실제 provider/executor 연결은 Phase 12.2 범위입니다.

### ThemeDataPlannerAgent

대상 API:

- `kto_wellness`
- `kto_pet`
- `kto_audio`
- `kto_eco`
- `kto_medical`

현재 상태:

- Phase 10.2에서는 capability routing과 skipped/future 기록까지만 합니다.
- 의료관광은 `ALLOW_MEDICAL_API=true`일 때만 고려합니다.
- 실제 provider/executor 연결은 Phase 12.3 범위입니다.

## EnrichmentExecutor

역할:

planner가 만든 plan 중 현재 실행 가능한 call만 실행합니다.

현재 실제 실행 대상:

- `kto_tour_detail_enrichment`
- 내부적으로 KorService2 `detailCommon2/detailIntro2/detailInfo2/detailImage2`를 묶어서 실행

저장 대상:

- `enrichment_runs`
- `enrichment_tool_calls`
- `tourism_items`
- `tourism_entities`
- `tourism_visual_assets`
- `source_documents`
- Chroma 재색인

실패 정책:

- 개별 tool call 실패는 `enrichment_tool_calls.error`에 남깁니다.
- 가능한 경우 workflow 전체를 즉시 깨지 않고 실패 call을 기록합니다.
- 실행된 상세 보강 결과는 source document로 다시 저장하고 Chroma에 재색인합니다.

## EvidenceFusionAgent

역할:

보강된 근거를 Product/Marketing/QA가 사용할 수 있는 후보별 evidence card와 claim policy로 정리합니다.

중요한 변경:

- 전체 `evidence_profile.entities`를 Gemini에게 다시 출력시키지 않습니다.
- evidence profile 자체는 deterministic code가 구성합니다.
- Gemini는 후보별 `candidate_evidence_cards`, claim policy, 상품화 조언, unresolved gap 요약, UI highlight를 생성합니다.
- 후보별 card에는 사용할 수 있는 사실, 경험 hook, 추천 상품화 각도, 운영자 확인 필요 항목, 사용하면 안 되는 claim을 나눠 담습니다.
- 전체 raw evidence를 복사하지는 않지만, KorService2 상세 보강으로 얻은 `overview`, 상세 소개, 이용정보, 이미지 후보 수 같은 상품화 핵심 정보는 후보별로 보존합니다.
- `kto_api_capability_matrix`는 EvidenceFusion prompt에 넣지 않습니다.

입력:

- compact evidence summary
- 보강 성공 후보 요약
- 후보별 상세 소개/이용정보/이미지 후보 요약
- unresolved gap 요약
- enrichment 실행/skip/fail count
- RAG top evidence 요약

출력:

- `productization_advice`
  - `candidate_evidence_cards`
  - `usable_claims`
  - `restricted_claims`
  - `candidate_recommendations`
  - `needs_review_fields`
- `unresolved_gaps`
- `source_confidence`
- `ui_highlights`

`evidence_profile`과 `data_coverage`는 Gemini 출력보다 deterministic base fusion 결과를 우선합니다.

토큰 정책:

- EvidenceFusion은 후보별 card를 만들기 때문에 planner 계열보다 긴 출력이 허용됩니다.
- `evidence_fusion`의 `maxOutputTokens`는 16,384로 설정합니다.
- 단, 전체 evidence profile을 그대로 재출력하지 않고 후보별 card의 field 수를 제한해 중복 출력을 막습니다.

## 99번 KTO API Capability 요약

| source_family | 99번 문서 | 채울 수 있는 정보 | Phase 10.2 상태 |
|---|---|---|---|
| `kto_tourapi_kor` | `99_01` | 기본 후보, 상세정보, 이미지, 운영시간, 요금, 예약정보 | 실제 실행 |
| `kto_photo_contest` | `99_02` | 사진 공모전 이미지, 시각 참고 | Phase 12.1 |
| `kto_tourism_photo` | `99_09` | 관광사진 이미지, 시각 참고 | Phase 12.1 |
| `kto_durunubi` | `99_06` | 걷기/코스/동선 근거 | Phase 12.2 |
| `kto_related_places` | `99_12` | 주변/연관 장소 | Phase 12.2 |
| `kto_tourism_bigdata` | `99_10` | 방문 수요 신호 | Phase 12.2 |
| `kto_crowding_forecast` | `99_11` | 혼잡 예측 신호 | Phase 12.2 |
| `kto_regional_tourism_demand` | `99_13` | 지역 관광수요 신호 | Phase 12.2 |
| `kto_wellness` | `99_03` | 웰니스 테마 속성 | Phase 12.3 |
| `kto_pet` | `99_05` | 반려동물 동반 조건 | Phase 12.3 |
| `kto_audio` | `99_07` | 해설/스토리/다국어 소재 | Phase 12.3 |
| `kto_eco` | `99_08` | 생태/지속가능성 맥락 | Phase 12.3 |
| `kto_medical` | `99_04` | 의료관광 맥락 | Phase 12.3, feature flag 필요 |

Phase 10.2에서는 99번 API들의 의미와 gap 연결을 정리했지만, KorService2 외 추가 API의 실제 호출은 Phase 12에서 구현합니다.

## Prompt Logging

Gemini prompt 디버깅을 위해 `.env` 설정을 추가했습니다.

```env
LLM_PROMPT_DEBUG_LOG_ENABLED=false
LLM_PROMPT_DEBUG_LOG_DIR=logs/prompt_debug
```

`LLM_PROMPT_DEBUG_LOG_ENABLED=true`이면 각 Gemini 호출마다 아래 파일을 저장합니다.

```text
logs/prompt_debug/<run_id>/<timestamp>__<agent>__<purpose>__<step_id>__retry-<n>__<status>.json
logs/prompt_debug/<run_id>/<timestamp>__<agent>__<purpose>__<step_id>__retry-<n>__<status>.md
```

`*.json`은 기계 분석용이고, `*.md`는 사람이 읽기 쉬운 로그입니다. Markdown 로그에서는 `\"`, `\n` 이스케이프 없이 prompt와 raw output을 코드블록으로 확인할 수 있습니다.

## UI 반영

구현된 UI:

- Run 생성 modal에서 preflight validation warning 표시
- Workflow Preview에 Preflight, Geo decision, DataGap decision, Router, 네 개 planner lane, Data Calls, Evidence Fusion 표현
- Run Detail Data Coverage panel
- Run Detail Recommended Data Calls panel
- 실행/보류/실패 enrichment call 표시
- Evidence table에서 raw geo/lcls code 숨김
- Evidence type 한글 표시
- Dashboard run table에서 task row 체크박스, 전체 선택, 선택 삭제 지원
- parent task를 선택하면 연결된 revision task도 같이 선택되며, 실행 중인 task는 삭제 대상에서 제외
- Run Detail QA Review 영역에 최초 실행 또는 마지막 revision QA 설정의 `Avoid` 기준 표시

후속 UI 정리:

- 현재 Run Detail의 단계별 진행 표시는 개발자 debug 용도에 가깝습니다.
- Phase 10.1 이후 일반 사용자용 진행 단계와 개발자용 agent step 상세를 분리합니다.

## 환경변수

Phase 10.2 관련 주요 설정:

```env
LLM_ENABLED=true
GEMINI_API_KEY=
GEMINI_GENERATION_MODEL=gemini-2.5-flash-lite
GEMINI_JSON_MAX_RETRIES=2

TOURAPI_SERVICE_KEY=
TOURAPI_DETAIL_ENRICHMENT_LIMIT=5
TOURAPI_CANDIDATE_SHORTLIST_LIMIT=20
ENRICHMENT_MAX_CALL_BUDGET=6

KTO_PHOTO_CONTEST_ENABLED=false
KTO_WELLNESS_ENABLED=false
KTO_PET_ENABLED=false
KTO_DURUNUBI_ENABLED=false
KTO_AUDIO_ENABLED=false
KTO_ECO_ENABLED=false
KTO_TOURISM_PHOTO_ENABLED=false
KTO_BIGDATA_ENABLED=false
KTO_CROWDING_ENABLED=false
KTO_RELATED_PLACES_ENABLED=false
KTO_REGIONAL_TOURISM_DEMAND_ENABLED=false
ALLOW_MEDICAL_API=false
```

`ENRICHMENT_MAX_CALL_BUDGET`은 future/non-core API 예산 관리용입니다. KorService2 상세 보강 가능한 shortlist 대상은 이 값 때문에 6개로 잘리지 않습니다.

## 검증

현재 확인된 테스트:

```bash
conda run -n paravoca-ax-agent-studio pytest backend/app/tests/test_data_enrichment.py -q
# 13 passed

cd backend
conda run -n paravoca-ax-agent-studio pytest -q
# 68 passed

cd frontend
PATH=/Users/yongchoooon/miniforge3/envs/paravoca-ax-agent-studio/bin:$PATH npm run build
# built successfully
```

Homebrew Node가 깨진 로컬 환경에서는 conda env의 `bin`을 PATH 앞에 둔 상태로 frontend build를 실행했습니다.

## Phase 11로 넘길 일

Phase 10.2는 Product 생성 품질 자체를 완전히 바꾸는 단계가 아닙니다. Phase 11에서 Product/Marketing/QA가 `evidence_profile`, `productization_advice`, `unresolved_gaps`, `ui_highlights`를 더 강하게 반영해야 합니다.

Phase 11 작업:

- evidence 기반 itinerary 생성
- source별 claim 제한
- data coverage에 따른 상품 card UI 다양화
- 이미지, route, signal, wellness, pet 등 데이터 유형별 표현 방식
- QA가 unresolved gaps를 기준으로 claim risk를 판단하도록 강화
- 공식 웹 근거 또는 사용자 추가 입력이 필요한 항목을 Product card에서 분리 표시

## Phase 12로 넘길 일

Phase 12는 99번 문서에 정리된 추가 KTO API들을 실제 provider/executor로 연결하는 단계입니다.

권장 분리:

- Phase 12.1 Visual APIs: 관광사진, 공모전 사진
- Phase 12.2 Route/Related/Demand Signals: 두루누비, 연관 관광지, 관광빅데이터, 혼잡도, 지역 관광수요
- Phase 12.3 Theme APIs: 웰니스, 반려동물, 오디오, 생태, 의료관광
