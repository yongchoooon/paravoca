# Phase 8 이후 구현 계획

작성 기준일: 2026-05-07

이 문서는 Phase 10.2까지 구현된 PARAVOCA AX Agent Studio를 기준으로, 평가와 배포 전에 보강해야 할 구현 단계를 다시 정리한 문서입니다. 기존 `11_IMPLEMENTATION_ROADMAP.md`의 Phase 8/9는 초기 계획 기준이며, 실제 다음 개발은 이 문서의 순서를 우선합니다.

## 현재 구현 기준

현재 코드의 핵심 흐름:

```text
Planner
  -> GeoResolver
  -> Data
  -> Research
  -> Product
  -> Marketing
  -> QA
  -> Human Approval
  -> Revision
```

현재 구현된 주요 기능:

- FastAPI backend scaffold
- React + Mantine UI frontend
- SQLite + SQLAlchemy DB
- workflow run 생성/조회/승인/반려/수정 요청
- revision run 생성
- TourAPI 기반 기본 데이터 조회
- TourAPI v4.4 `ldongCode2`/`lclsSystmCode2` catalog sync
- GeoResolverAgent 기반 자연어 지역 해석
- `lDongRegnCd`/`lDongSignguCd` 기반 workflow 검색
- 지역 후보 안내/지원 범위 밖 조기 종료
- TourAPI content_id 기반 상세 보강
- source document 생성
- Chroma 기반 vector search
- local semantic embedding provider와 source document reindex command
- Gemini 기반 Product, Marketing, QA, Revision patch
- LLM/tool/error usage log
- KTO API capability catalog
- 데이터 보강용 DB foundation
- 상세 이미지 후보 저장
- Run Detail, Result Review, QA issue 삭제, revision history UI
- Run Detail Evidence 상세 정보/이미지 후보 UI
- 현재 frontend는 단일 Dashboard 중심 화면이며, Mantine `AppShell.Navbar` 기반 앱 전체 navigation shell은 아직 구현되지 않음

현재 TourAPI 사용 범위:

- `areaCode2` backward compatibility
- `ldongCode2`
- `lclsSystmCode2`
- `areaBasedList2`
- `searchKeyword2`
- `searchFestival2`
- `searchStay2`
- `detailCommon2`
- `detailIntro2`
- `detailInfo2`
- `detailImage2`
- `categoryCode2`
- `locationBasedList2`

아직 부족한 부분:

- 주변 관광지와 분류 코드는 provider method만 추가되어 있고 workflow 보강 판단에는 아직 직접 연결되지 않음
- Product/Marketing이 evidence 내용을 완전히 반영하는 생성 품질은 Phase 10 이후 Data Enrichment/EvidenceFusion/Agent 실제화에서 보강 필요
- 방문 수요, 혼잡도 같은 운영 판단 신호
- 웰니스, 반려동물, 두루누비, 오디오 가이드, 생태, 의료 같은 테마별 공공데이터
- 공식 홈페이지/예약 페이지/행사 공지에서 최신 운영 정보를 확인하는 웹 근거 수집
- Planner, Data, Research Agent의 실제 데이터 기반 판단
- Poster Studio용 이미지 후보와 poster context
- 데이터 보강 품질까지 포함한 evaluation
- Dashboard 내부 탭을 넘어서는 Mantine `AppShell.Header`/`AppShell.Navbar` 기반 전역 navigation과 route 구조

## 구현 원칙

- 실제 KTO OpenAPI와 공식 웹 근거를 우선 사용한다.
- 데이터가 부족하면 고정 데이터로 채우지 않고 공백을 구조화한다.
- 사용자에게 바로 묻기 전에 공식 홈페이지, 예약 페이지, 행사 공지, 운영사 정책 페이지를 먼저 확인한다.
- 공식 웹 근거로도 확정할 수 없는 항목만 사용자 입력 또는 내부 DB 확인 대상으로 넘긴다.
- 가격, 예약 가능 시간, 취소/환불 정책, 파트너 조건, 최종 판매가는 확정 근거와 검토 상태를 분리한다.
- 방문 수요, 집중률, 연관 관광지 데이터는 운영 판단 보조 신호로만 사용한다.
- 의료관광 API는 별도 feature flag가 켜졌을 때만 사용한다.
- 이미지와 사진 데이터는 게시 가능 후보와 prompt/reference 후보를 구분한다.
- 모든 API/tool/LLM/web evidence 호출은 DB와 로그 파일에서 추적 가능해야 한다.

## Phase 8: KTO Data Foundation

목표:

- 여러 KTO OpenAPI를 붙일 수 있는 provider, schema, capability 기반을 만든다.

현재 상태:

- 구현 완료.
- `/api/data/sources/capabilities`에서 source family와 tool capability를 확인할 수 있다.
- API key나 설정이 없는 source는 disabled로 표시한다.
- 보강용 DB 모델 foundation이 추가되어 있고, 실제 workflow 연결은 Phase별로 순차 적용한다.

작업:

- `TourApiProvider`를 확장 가능한 구조로 정리
- `kto_capabilities` catalog 추가
- source family, gap type, tool name, TTL, risk level, enabled flag 정의
- `/api/data/sources/capabilities` API 추가
- `source_documents` metadata 확장
- 데이터 보강용 DB 모델 추가

추가 DB 후보:

- `tourism_entities`
- `tourism_visual_assets`
- `tourism_route_assets`
- `tourism_signal_records`
- `web_evidence_documents`
- `enrichment_runs`
- `enrichment_tool_calls`

완료 기준:

- 현재 활성화된 KTO source 목록을 API로 확인할 수 있다.
- API key 또는 설정이 없는 source는 disabled로 표시된다.
- 기존 workflow는 깨지지 않는다.
- source document에 `source_family`, `retrieved_at`, `license_note`, `trust_level` 같은 metadata를 남길 수 있다.

## Phase 9: KorService2 Detail Enrichment

목표:

- 현재 목록 조회 중심 데이터를 상세 정보 중심 evidence로 보강한다.

현재 상태:

- 구현 완료.
- workflow Data 단계에서 기존 TourAPI 검색 결과 일부를 content_id 기반 상세 정보로 보강한다.
- 별도 API로도 저장된 item 또는 content_id 기반 상세 보강을 실행할 수 있다.
- 실제 TourAPI 호출 실패 시 mock/fallback 없이 `tool_calls.error`, FastAPI log, `workflow_errors` log로 확인한다.
- 상세 이미지 후보는 `candidate` 상태로만 저장한다.

추가할 endpoint:

- `detailCommon2`
- `detailIntro2`
- `detailInfo2`
- `detailImage2`
- `categoryCode2`
- `locationBasedList2`

작업:

- content_id 기반 상세 조회 method 추가 완료
- 상세 주소, 홈페이지, 개요, 좌표, 대표 이미지 저장 완료
- content type별 소개 정보 저장 완료
- 이용 시간, 주차, 쉬는 날, 문의, 요금성 안내 등 반복 정보 저장 완료
- 상세 이미지 후보 저장 완료
- 기존 `tourism_items`, `source_documents`, Chroma index에 상세 정보 반영 완료
- Run Detail의 Evidence 패널에서 상세 정보와 이미지 후보 표시 완료
- `GET /api/data/tourism/search?enrich_details=true` 추가
- `POST /api/data/tourism/details/enrich` 추가

저장 매핑:

| endpoint | 저장 대상 | 설명 |
|---|---|---|
| `detailCommon2` | `tourism_items.raw`, `tourism_entities`, `source_documents` | 주소, 개요, 홈페이지, 좌표, 대표 이미지 같은 공통 상세를 canonical entity와 RAG 문서에 반영 |
| `detailIntro2` | `tourism_items.raw`, `source_documents` | content type별 소개 속성을 RAG 근거로 반영 |
| `detailInfo2` | `tourism_items.raw`, `source_documents` | 이용 시간, 주차, 휴무, 문의, 요금성 안내를 별도 section으로 저장 |
| `detailImage2` | `tourism_visual_assets`, `source_documents metadata` | 상세 이미지 후보를 저장하고 게시 가능 여부는 별도 상태로 관리 |
| `categoryCode2` | category cache table 또는 metadata | 분류 코드 정규화와 검색 query 개선에 사용 |
| `locationBasedList2` | `tourism_entities`, `source_documents` | 특정 장소 주변 관광지 후보를 저장하고 코스 구성 후보로 활용 |

주의:

- 상세 정보를 가져오더라도 가격, 예약 가능 여부, 운영 여부를 확정 표현하지 않는다.
- `detailImage2` 이미지는 바로 게시 가능으로 보지 않고 `candidate`로 저장한다.
- 현재 hash 기반 embedding을 유지한 상태라면 source document만 풍부해지고 검색 품질 개선은 제한적일 수 있다.
- `categoryCode2`, `locationBasedList2`는 provider method와 capability에는 추가되어 있지만, 실제 route/candidate ranking workflow에는 Phase 10 이후 연결한다.

완료 기준:

- 기본 검색 결과가 content_id 기반 상세 정보로 보강된다. 완료.
- source evidence에서 어떤 정보가 API로 확인되었는지 볼 수 있다. 완료.
- QA가 “확인된 정보”와 “운영자 확인 필요 정보”를 구분할 수 있다. 부분 완료. source document metadata와 evidence 표시는 완료했고, QA 판단 고도화는 Phase 10 이후 DataGap/EvidenceFusion 단계에서 보강한다.
- 상세 이미지 후보가 `tourism_visual_assets`에 저장된다. 완료.

검증 메모:

- backend test: `20 passed`
- frontend production build 성공
- 실제 TourAPI 키로 부산 행사 1건 상세 보강 확인
- 예시 entity: `entity:tourapi:content:2786391`, `광안리 M(Marvelous) 드론 라이트쇼`
- 예시 visual asset: `usage_status=candidate`, `source_family=kto_tourapi_kor`

## Phase 9.5: Local Semantic Embedding

목표:

- 현재 임시 hash embedding을 실제 semantic embedding으로 교체한다.
- 비용 부담을 줄이기 위해 우선 로컬 `sentence-transformers` 모델을 사용한다.

기본 방향:

- Gemini embedding은 비용과 호출량을 확인하기 전까지 기본값으로 쓰지 않는다.
- OpenAI embedding도 기본값으로 쓰지 않는다.
- 한국어 관광 데이터 검색을 고려해 multilingual sentence-transformers 모델을 우선 검토한다.
- Chroma는 유지하고 embedding 함수만 교체한다.

후보 모델:

| 후보 | 장점 | 주의 |
|---|---|---|
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 가볍고 한국어 포함 multilingual 지원 | 고급 검색 품질은 제한적일 수 있음 |
| `intfloat/multilingual-e5-small` | 검색용 embedding에 적합한 계열 | query/document prefix 규칙 확인 필요 |
| `intfloat/multilingual-e5-base` | small보다 품질 기대치 높음 | 로컬 CPU에서 느릴 수 있음 |

설정:

```text
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_DEVICE=cpu
EMBEDDING_BATCH_SIZE=32
```

작업:

- `backend/app/rag/embeddings.py` 추가
- 기존 `hash` embedding을 `legacy_hash` provider로 분리
- local sentence-transformers provider 구현
- `index_source_documents`와 `search_source_documents`가 provider 설정을 사용하도록 변경
- 기존 Chroma collection 재생성 명령 추가
- `source_documents.embedding_status`를 `pending/indexed/failed`로 관리
- retrieval recall smoke test 추가
- README에 로컬 embedding 설치와 재색인 방법 추가

재색인 명령 후보:

```text
python -m app.rag.reindex --collection source_documents --reset
```

완료 기준:

- `EMBEDDING_PROVIDER=local`에서 source document가 실제 semantic embedding으로 색인된다.
- 기존 workflow run 생성이 정상 동작한다.
- `/api/rag/search` 결과가 hash embedding이 아니라 local embedding 기반으로 반환된다.
- embedding API 비용이 발생하지 않는다.
- 검색 실패나 모델 로딩 실패가 FastAPI log와 workflow error log에 남는다.

## Phase 10: Data Enrichment Workflow

구현 상태: 완료. Phase 10 기준 코드에는 기본 TourAPI 수집 이후 data gap profiling, capability routing, 선택적 KorService2 상세/이미지 보강, evidence fusion, Run Detail Data Coverage/Recommended Data Calls UI가 연결되어 있습니다. Phase 10.2에서 DataGapProfilerAgent, ApiCapabilityRouterAgent, 네 개의 API family planner, EvidenceFusionAgent는 Gemini prompt + JSON schema 기반 판단으로 전환되었습니다.

목표:

- 현재 run의 요청, 수집 데이터, 상품 초안, QA 결과를 보고 필요한 데이터 보강만 실행하는 Agent workflow를 만든다.

추가 Agent:

- `BaselineDataAgent`
- `DataGapProfilerAgent`
- `ApiCapabilityRouterAgent`
- `TourApiDetailPlannerAgent`
- `VisualDataPlannerAgent`
- `RouteSignalPlannerAgent`
- `ThemeDataPlannerAgent`
- `EnrichmentExecutor`
- `EvidenceFusionAgent`

workflow:

```text
Planner
  -> BaselineDataAgent
  -> DataGapProfilerAgent
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

작업:

- 현재 Data Agent를 `BaselineDataAgent` 역할로 분리. 완료.
- 데이터 공백을 `missing_detail_info`, `missing_image_asset`, `missing_operating_hours`, `missing_price_or_fee`, `missing_booking_info`, `missing_related_places`, `missing_route_context`, `missing_theme_specific_data` 구조로 생성. 완료.
- gap type을 API family planner lane으로 변환하고, 각 planner가 call/skip fragment를 생성. 완료.
- max call budget 적용. 완료. 설정값은 `ENRICHMENT_MAX_CALL_BUDGET`.
- enrichment run 생성/조회 API 추가. 완료. `GET /api/workflow-runs/{run_id}/enrichment`.
- KorService2 `detailCommon2`, `detailIntro2`, `detailInfo2`, `detailImage2` 선택 호출과 source document 재색인. 완료.
- 아직 provider가 없는 KTO source family는 실제 호출한 것처럼 표시하지 않고 skipped/future로 기록. 완료.
- Data Coverage panel UI 추가. 완료.
- Recommended Data Calls panel UI 추가. 완료.

다양한 KTO endpoint 저장 매핑:

| 데이터 묶음 | 저장 대상 | 활용 |
|---|---|---|
| 국문 관광정보 상세 | `tourism_entities`, `tourism_items`, `source_documents` | 상품 후보 기본 근거, 운영 정보 확인, QA |
| 상세 이미지, 관광사진, 공모전 사진 | `tourism_visual_assets` | 상세페이지 이미지 후보, Poster Studio, SNS 소재 |
| 두루누비 | `tourism_route_assets`, `source_documents` | 도보/트레킹 코스, 거리, 시작/종료 지점, GPX |
| 관광빅데이터 | `tourism_signal_records` | 지역/기간별 수요 판단 보조 |
| 집중률 예측 | `tourism_signal_records` | 혼잡 리스크, 대체 시간/장소 제안 |
| 연관 관광지 | `tourism_signal_records`, `tourism_entities` | 주변 코스 조합 후보 |
| 웰니스/반려동물/오디오/생태/의료 | `tourism_entities`, `source_documents`, 필요 시 theme-specific metadata | 테마형 상품 근거 |
| 공식 웹 근거 | `web_evidence_documents`, `source_documents` | 집결지, 운영 시간, 예약 조건, 취소 정책 후보 |

Agent별 역할:

- `DataGapProfilerAgent`: 어떤 정보가 부족한지 판단한다.
- `ApiCapabilityRouterAgent`: 부족한 정보를 어느 API family planner가 다룰지 분배한다.
- `TourApiDetailPlannerAgent`: KorService2 상세/이미지 보강 호출을 계획한다.
- `VisualDataPlannerAgent`: 관광사진/공모전 사진 API 후보를 future/skip 포함해 계획한다.
- `RouteSignalPlannerAgent`: 두루누비, 연관 장소, 수요/혼잡 신호 API 후보를 future/skip 포함해 계획한다.
- `ThemeDataPlannerAgent`: 웰니스, 반려동물, 오디오, 생태, 의료 API 후보를 future/skip 포함해 계획한다.
- `EnrichmentExecutor`: Agent 판단자가 아니라 코드 실행 action이다. 계획된 API 호출을 실행하고 DB에 저장한다.
- `EvidenceFusionAgent`: 여러 API에서 온 정보를 같은 장소/상품 근거 묶음으로 병합한다.

주의:

- 모든 endpoint를 매번 호출하지 않는다.
- 이미 cache가 있고 TTL이 유효하면 API 호출을 건너뛴다.
- 의료관광 API는 별도 설정이 켜진 경우에만 라우팅한다.
- 수요, 혼잡도, 연관 관광지는 본문 사실처럼 쓰지 않고 운영 판단 신호로만 사용한다.

완료 기준:

- 이미지 없는 item에서 `missing_image_asset`이 생성된다.
- 운영 시간/요금/예약정보가 부족하면 해당 gap이 생성된다.
- 반려동물, 도보, 웰니스 같은 요청은 해당 theme gap으로 분류된다.
- 불필요한 API를 매번 호출하지 않는다.
- 실패한 enrichment call은 workflow 전체를 깨지 않고 `enrichment_tool_calls.error`에 원인을 남긴다.
- EvidenceFusion 결과가 `evidence_profile`, `productization_advice`, `data_coverage`, `unresolved_gaps`, `source_confidence`로 final output에 포함된다.

## Phase 10.2: Gemini Data Enrichment Agent 전환

구현 상태: 완료. 자세한 내용은 [16_PHASE_10_2_GEMINI_DATA_ENRICHMENT.md](./16_PHASE_10_2_GEMINI_DATA_ENRICHMENT.md)를 기준으로 합니다.

완료한 일:

- `DataGapProfilerAgent`를 Gemini `data_gap_profile` prompt + JSON schema 기반으로 전환
- `ApiCapabilityRouterAgent`를 Gemini `api_capability_routing` prompt + JSON schema 기반 family routing으로 전환
- 4개 API family planner를 Gemini prompt + JSON schema 기반으로 추가
- `EvidenceFusionAgent`를 Gemini `evidence_fusion` prompt + JSON schema 기반으로 전환
- `EnrichmentExecutor`는 Gemini agent가 아니라 deterministic data call action으로 유지
- 99번 KTO API 명세 전체를 `kto_capabilities.py`에 반영하고, Agent prompt에는 compact capability brief만 전달
- Baseline raw 후보를 `TOURAPI_CANDIDATE_SHORTLIST_LIMIT` 기준 shortlist로 줄여 DataGap/Enrichment 입력으로 사용
- KorService2 상세 보강은 shortlist 안의 실행 가능한 `contentId` 대상을 임의 6개 budget으로 자르지 않도록 수정
- EvidenceFusion은 전체 evidence profile을 다시 출력하지 않되, 보강된 후보별 `candidate_evidence_cards`를 만들고 사용할 수 있는 사실, 경험 hook, 상품화 각도, 제한 claim, 운영자 확인 항목을 분리
- Gemini prompt debug log를 JSON과 Markdown으로 저장하도록 추가
- 실제 실행 가능한 API와 future/unsupported API를 분리
- Run Detail에 Gemini reasoning summary, routing/planning reasoning, `ui_highlights` 기반 상품화 판단 메모 표시
- Workflow Preview의 DataGap/Router/4 Planner/Fusion node를 Gemini 기반 구조로 갱신
- Dashboard run table에서 task 선택/전체 선택/선택 삭제 구현. parent task 선택 시 revision task 자동 선택, 실행 중 task 삭제 차단
- Run Detail QA Review에 최초 실행 또는 마지막 revision QA 설정의 `Avoid` 기준 표시

운영 기준:

- `LLM_ENABLED=true`에서는 신규 DataGap/Router/Planner/Fusion agent가 Gemini를 호출한다.
- schema validation이 실패하면 Gemini JSON retry 정책을 따르고, 최종 실패 시 workflow를 실패로 남긴다.
- provider가 없는 99번 KTO API는 실제 호출한 것처럼 표시하지 않고 `skipped/future_provider_not_implemented`로 기록한다.
- 의료관광 API는 `ALLOW_MEDICAL_API=true`가 아니면 planned call로 만들지 않는다.
- `data_gap_profile`과 `evidence_fusion`의 `maxOutputTokens`는 16,384로 설정한다.

## Phase 10.1: AppShell Navbar and Global Navigation

목표:

- 현재 Dashboard 한 화면 중심 UI를 Mantine `AppShell` 기반 운영툴 shell로 전환한다.
- 좌측 `AppShell.Navbar`와 상단 `AppShell.Header`를 추가해 앞으로 생길 Data Sources, Evaluation, Cost, Settings, Poster Studio 화면을 자연스럽게 연결한다.

이 Phase가 필요한 이유:

- Phase 9.6까지는 Dashboard 안의 table, workflow preview, run detail drawer를 중심으로 기능을 붙였습니다.
- Phase 10 이후에는 Data Coverage, Recommended Data Calls, Data Sources, Evaluation Dashboard 같은 독립 화면이 늘어나므로, Dashboard 내부 탭만으로는 정보 구조가 부족합니다.
- AppShell migration은 Data Enrichment workflow 자체와 성격이 다르므로, 별도 frontend architecture phase로 분리합니다.

작업:

- `frontend/src/components/AppShellLayout/` 공통 layout module 추가
- Mantine `AppShell.Header`, `AppShell.Navbar`, `AppShell.Main`, mobile `Burger` 구현
- 좌측 navigation item 구성:
  - Dashboard
  - Workflow Preview
  - Data Sources
  - Evaluation
  - Costs
  - Poster Studio
  - Settings
- 현재 Dashboard 기능을 `AppShell.Main` 안으로 이동하되 기존 run 생성, run table, Run Detail drawer, workflow preview 동작은 유지
- `Runs`는 별도 전역 nav item으로 두지 않고 Dashboard 안에 summary와 table을 함께 유지
- 아직 구현되지 않은 화면은 빈 route 또는 disabled/future nav item으로 표시하고, 실제 기능을 만든 것처럼 보이게 하지 않음
- active route highlight, collapsed mobile state, header action area, notification 영역 정리
- Dashboard 내부에서만 쓰던 navigation성 탭은 전역 navbar와 역할이 겹치지 않도록 재정리
- 사용자용 진행 상태는 내부 agent/debug 단계 전체를 그대로 노출하지 않는다. 개발자 모드에서는 `Planner`, `Geo`, `Gemini Gap`, `Gemini Router`, 개별 planner lane 같은 세부 단계를 볼 수 있게 유지하되, 일반 사용자 모드에서는 `요청 이해`, `관광 데이터 확인`, `보강 정보 확인`, `상품 초안 생성`, `검수`처럼 더 적은 단계로 묶어 보여준다.

하지 않을 것:

- Data Enrichment workflow 구현
- Evaluation Dashboard 실제 지표 구현
- Cost Dashboard 실제 비용 분석 구현
- Poster Studio 이미지 생성 구현

완료 기준:

- 첫 화면 진입 시 Mantine `AppShell.Navbar`가 표시된다.
- Dashboard 안에서 summary와 Runs table의 기존 사용 흐름이 깨지지 않는다.
- Workflow Preview는 전역 Navbar에서 독립적으로 접근할 수 있다.
- mobile width에서는 navbar가 `Burger`로 접히고 펼쳐진다.
- 아직 미구현인 화면은 명확히 future/disabled 상태로 보인다.
- `npm run build`가 통과한다.

구현 결과:

- Phase 10.1은 구현 완료되었습니다.
- `AppShellLayout`이 `activeSection`을 받아 Header/Navbar/Main을 렌더링합니다.
- Dashboard는 기존처럼 summary와 Runs table을 함께 보여줍니다.
- Dashboard 내부 `Tabs`는 제거했고, Workflow Preview는 전역 Navbar에서 접근합니다.
- Data Sources, Evaluation, Costs, Poster Studio, Settings는 `향후 연결 예정` placeholder입니다.
- frontend production build가 통과했습니다.

## Phase 10.5: UI and Operations Surface Cleanup

구현 상태: 완료. Phase 10.5는 backend workflow를 변경하지 않고 Run Detail과 AppShell placeholder의 정보 구조를 정리한 frontend UI phase입니다.

목표:

- AppShell 전환 이후 사용자용 운영 화면을 정리하고, 개발자용 debug 정보와 일반 사용자용 진행/근거 화면을 분리한다.

원칙:

- 일반 사용자는 내부 agent 이름과 planner lane을 모두 볼 필요가 없다.
- 개발자와 운영자는 debug 모드에서 상세 단계, prompt log, tool call을 확인할 수 있어야 한다.
- Evidence, Data Coverage, Enrichment 정보는 raw JSON보다 상품화 판단에 도움이 되는 문장과 상태 중심으로 보여준다.
- 아직 연결되지 않은 Data Sources/Evaluation/Costs/Poster Studio/Settings는 실제 기능처럼 보이면 안 된다.

작업:

- Run Detail의 진행 단계 표시를 사용자용 요약 단계와 개발자용 상세 단계로 분리
- Data Coverage / Enrichment / Evidence 표시 방식 정리
- Evidence table에서 사용자에게 불필요한 raw geo/lcls code와 내부 field 노출 방지 정책 유지
- Recommended Data Calls는 왜 호출했는지, 왜 보류했는지, 어떤 정보가 보강됐는지 중심으로 표시
- unresolved gaps와 needs_review를 운영자가 실제로 확인해야 할 항목으로 정리
- debug prompt log, llm_calls, tool_calls는 개발자용 영역으로 분리
- Data Sources/Evaluation/Costs/Poster Studio/Settings placeholder 문구와 연결 계획 정리

완료 기준:

- 일반 사용자 화면에서 내부 agent 단계가 과도하게 노출되지 않는다.
- 개발자용 상세 정보는 필요할 때만 확인 가능하다.
- Evidence/Data Coverage/Enrichment 패널이 상품화 판단 관점에서 읽히도록 정리된다.
- placeholder 화면은 future 상태임이 명확하다.
- frontend build가 통과한다.

구현 결과:

- Run Detail 탭을 `Result Review`, `Evidence + QA`, `Developer`로 정리했습니다.
- 사용자용 진행 단계는 `요청 확인`, `지역 해석`, `관광 데이터 확인`, `보강 정보 확인`, `상품 초안 생성`, `검수 및 승인`으로 묶었습니다.
- 상세 agent step, tool call, LLM call, Raw JSON은 `Developer` 탭과 accordion 안으로 이동했습니다.
- Data Coverage는 충분/일부 부족/부족/정보 없음/확인 필요 상태로 표시합니다.
- Recommended Data Calls는 호출됨/보류됨/향후 연결 예정/실패함 기준으로 표시합니다.
- Evidence table은 출처, 지역, 유형, 보강 여부, 이미지 후보, 운영자 확인 여부 중심으로 정리했고 raw geo/lcls code는 기본 화면에서 숨깁니다.
- Data Sources, Evaluation, Costs, Poster Studio, Settings placeholder 문구를 후속 Phase 기준으로 정리했습니다.

## Phase 11: Planner, Research, Product Evidence Actualization

구현 상태: Phase 11/11.5 기준 완료. Phase 11에서는 Product/Marketing/QA가 `evidence_profile`, `productization_advice`, `data_coverage`, `unresolved_gaps`, `source_confidence`, `ui_highlights`를 공유하고, 근거 없는 운영시간/요금/예약/외국어/안전/의료/웰니스 claim을 `assumptions`, `not_to_claim`, `needs_review`, `claim_limits`로 분리하도록 전환했습니다. Phase 11.5에서는 `PlannerAgent`와 `ResearchSynthesisAgent`를 Gemini prompt + JSON schema 기반으로 전환했고, `data_summary` deterministic 수집 로그를 LLM Calls에서 분리했습니다.

목표:

- 아직 규칙 기반에 가까운 Planner와 Research를 실제 evidence 기반 Agent로 바꾸고, Product/Marketing/QA가 Phase 10.2의 `evidence_profile`, `productization_advice`, `unresolved_gaps`, `ui_highlights`를 강하게 반영하도록 만든다.

작업:

- Planner Agent를 Gemini structured output 기반으로 전환
- Planner output에 region, period, target, product_count, preferences, avoid, data_need_hints 포함
- Data Agent는 고정 호출이 아니라 enrichment plan을 실행
- ResearchSynthesisAgent는 EvidenceFusion 결과를 압축 요약하지 않고 후보별 `candidate_evidence_cards`의 usable facts, operational unknowns, restricted claims, evidence document ids를 보존한 채 ProductAgent용 research brief를 만든다.
- Product Agent에 raw document list 대신 `evidence_profile`과 `productization_advice` 전달
- Product Agent가 evidence 기반 itinerary를 만들고, source가 없는 운영시간/요금/예약 가능 여부를 단정하지 않도록 prompt와 validation 강화
- data coverage 수준에 따라 상품 card UI를 다양화. 예: 이미지 후보 있음, route 근거 있음, signal만 있음, 운영자 확인 필요
- 이미지/route/signal/wellness/pet 같은 데이터 유형별로 사용자에게 보여줄 표현 방식을 분리
- QA가 `unresolved_gaps`를 기준으로 claim risk를 판단하도록 강화
- 사용자 입력의 `avoid` 항목과 기본 QA 검수 항목을 분리

완료 기준:

- Planner가 입력 요청을 구조화하고 검증 실패 시 명확한 에러를 남긴다.
- Research 결과가 실제 source evidence와 signal에 근거한다.
- Product/Marketing/QA가 같은 evidence profile을 공유한다.
- 근거 없는 claim은 상품 본문이 아니라 assumptions/not_to_claim/needs_review로 분리된다.
- `data_summary`는 LLM Calls에 저장되지 않고 `agent_steps`/`tool_calls`에서 deterministic 실행 기록으로 확인된다.

역할 경계:

- `ApiCapabilityRouterAgent`는 baseline 데이터 수집 이후 gap report를 보고 어떤 보강 API family/planner lane으로 보낼지 결정한다.
- baseline TourAPI 검색 전에 query/API 전략을 결정하는 역할이 필요해지면 Phase 12 이후 `BaselineSearchPlanner` 또는 `TourAPIQueryPlanner`로 별도 분리한다.
- Phase 11.5에서는 새 DataQueryPlanner를 만들지 않는다.

## Phase 12: Additional KTO API Data Utilization

Phase 12는 99번 문서에 정리된 추가 KTO API를 실제 provider/executor로 붙이고, 가져온 데이터를 DB/source document/RAG/Product UI에 반영하는 단계입니다. Phase 10.2까지는 capability catalog, compact capability brief, Gemini routing만 준비되어 있으므로, Phase 12부터는 “필요하다고 판단한 API를 실제로 호출해 저장하고 상품 생성에 활용”하는 것을 완료 기준으로 둡니다.

목표:

- 상품 구성, 이미지 후보, route/연관 장소, 수요 판단, 혼잡 리스크, 테마형 상품 근거를 실제 API 데이터로 보강한다.

### Phase 12.1: Visual APIs

대상 API:

- 관광사진 정보_GW
- 관광공모전 사진 수상작 정보

작업:

- 관광사진/공모전 사진 provider method 추가
- 이미지 후보를 `tourism_visual_assets`에 저장
- 게시 가능 후보와 참고 후보를 분리
- 이미지 저작권/사용 조건 확인 필요 상태를 UI에 표시
- Poster Studio에 넘길 visual hints 생성

### Phase 12.2: Route, Related Places, Demand Signals

대상 API:

- 관광지별 연관 관광지 정보
- 관광지 집중률 방문자 추이 예측 정보
- 관광빅데이터 정보서비스_GW
- 지역별 관광수요 예측 정보
- 두루누비 정보 서비스_GW

작업:

- 연관 관광지를 코스 조합 후보로 저장
- 두루누비 코스/경로를 `tourism_route_assets`와 `source_documents`에 저장
- 방문 수요와 집중률을 `tourism_signal_records`에 저장
- Product ranking에 수요/혼잡/연관성 signal을 반영
- QA에서 혼잡/수요 신호를 확정 정보처럼 쓰지 않는지 검수

### Phase 12.3: Theme APIs

대상 API:

- 웰니스관광정보
- 반려동물 동반여행 서비스
- 관광지 오디오 가이드정보_GW
- 생태 관광 정보_GW
- 의료관광정보

작업:

- 요청 의도에 따라 theme gap 생성
- theme별 provider method 추가
- theme 결과를 `tourism_entities`, `source_documents`, 필요 시 theme-specific metadata에 저장
- 반려동물 조건, 웰니스 속성, 오디오 해설, 생태 맥락을 상품 구성에 반영
- 의료관광 API는 `ALLOW_MEDICAL_API=true`일 때만 활성화
- 테마 API 근거가 Product card와 Run Detail에서 “확인된 정보”와 “운영자 확인 필요”로 나뉘어 보이게 함

완료 기준:

- Run Detail에서 상품별 이미지 후보를 볼 수 있다.
- 상품 초안이 주변 관광지/숙박/음식 조합 근거를 활용한다.
- 반려동물 요청에서 pet policy 근거를 찾는다.
- 도보/트레킹 요청에서 두루누비 코스 근거를 찾는다.
- 외국인 문화/역사 요청에서 오디오 가이드 근거를 활용할 수 있다.
- 웰니스/생태/의료관광 데이터는 과장 claim 없이 운영자 확인 항목과 함께 표시된다.
- 혼잡도는 경고 또는 대체 제안으로만 표시된다.
- 수요 데이터는 판매 보장 문구로 쓰이지 않는다.

## Phase 13: Official Web Evidence + User Detail Request

목표:

- 공공 API에 없는 최신 운영 정보를 사용자에게 묻기 전에 공식 웹 근거로 먼저 확인한다.

추가 Agent:

- `OfficialWebEvidenceAgent`
- `HumanDataRequestAgent`

workflow:

```text
missing_user_business_info
  -> OfficialWebEvidenceAgent
  -> web_evidence_documents 저장
  -> 남은 항목만 HumanDataRequestAgent
  -> 사용자 입력 또는 내부 DB 확인
```

공식 웹 검색 우선순위:

1. 관광지/행사/운영사 공식 홈페이지
2. 공식 예약/판매 페이지
3. 지자체 또는 주최 측 공지
4. 플랫폼 정책 페이지
5. 뉴스/블로그/커뮤니티는 참고 자료로만 분류

먼저 확인할 항목:

- 운영 시간
- 예약 가능 시간
- 집결지
- 취소/환불 정책
- 포함/불포함 사항
- 가격

바로 사용자 또는 내부 DB 확인으로 넘길 항목:

- 파트너 정산 조건
- 최종 판매가
- 플랫폼 자체 취소/환불 정책
- 내부 프로모션 여부
- 공급사 계약 조건

추가 tool:

- `official_web_search`
- `official_page_extract`
- `user_detail_request`

추가 저장 구조:

- `web_evidence_documents`

저장 원칙:

- 공식 출처와 상품 맥락이 명확할 때만 `confirmed`로 저장한다.
- 가격, 예약 가능 시간, 취소 정책은 공식 근거가 있어도 `needs_human_review=true`로 둘 수 있다.
- 비공식 페이지는 `reference_only`로 저장한다.
- API 근거와 웹 근거가 충돌하면 `conflicted`로 저장한다.
- 검색 snippet만으로 확정하지 않고 URL, 조회 시각, source type, 요약을 함께 저장한다.

UI:

- Run Detail에 Web Evidence panel 추가
- “운영자 입력 필요” panel 추가
- 공식 근거로 확인된 항목과 사용자 확인이 필요한 항목을 분리 표시
- 사용자 입력은 revision context와 QA에 전달

완료 기준:

- 집결지 후보가 공식 예약 페이지에서 확인되면 web evidence로 저장된다.
- 공식 근거가 없으면 사용자 입력 요청 후보로 넘어간다.
- 가격과 취소 정책은 공식 페이지가 있어도 검토 필요 상태를 유지할 수 있다.
- 사용자에게 묻는 항목 수가 공식 웹 근거 확인 뒤 줄어든다.

## Phase 14: Evaluation

목표:

- LLM 품질뿐 아니라 데이터 보강 품질까지 평가한다.

평가 항목:

- Retrieval Recall
- Faithfulness
- Tool Call Accuracy
- Task Success Rate
- Cost per Task
- Latency
- Human Revision Rate
- Data Coverage Score
- Enrichment Tool Accuracy
- Image Coverage
- Evidence Conflict Rate
- QA Issue Precision
- Web Evidence Precision
- User Detail Request Reduction Rate

작업:

- eval dataset JSONL 작성
- eval runner 구현
- KTO enrichment 평가 case 작성
- official web evidence 평가 case 작성
- QA issue precision sample 작성
- eval report JSON/Markdown 생성
- frontend Evaluation Dashboard 보강

완료 기준:

- `python -m app.evals.run_eval --sample-size 3` 실행 가능
- 데이터 보강 전/후 coverage 차이를 report에서 볼 수 있다.
- 공식 웹 근거가 필요한 case와 사용자 입력이 필요한 case를 구분해 평가한다.

## Phase 15: Deployment / Demo Hardening

목표:

- 외부에서 README만 보고 데모를 실행할 수 있게 만든다.

작업:

- Dockerfile 정리
- Docker Compose 정리
- DB migration 전략 정리
- `.env.example` 최신화
- LLM usage log, tool call log, workflow error log 위치 명시
- seed command 추가
- demo scenario script 작성
- loading/empty/error state UI 정리

완료 기준:

- 새 환경에서 README 기준으로 backend/frontend 실행 가능
- 실제 TourAPI key와 Gemini key가 있으면 demo workflow 완주 가능
- 실패 시 FastAPI log와 log file에서 원인을 확인할 수 있다.

## Phase 16: Poster Studio

목표:

- 승인 가능 상태의 상품 결과를 바탕으로 포스터 생성 워크플로우를 만든다.

workflow:

```text
Approved or Reviewable Run
  -> PosterContextBuilder
  -> DataGapProfilerAgent
  -> ApiCapabilityRouterAgent
  -> VisualDataEnrichment
  -> PosterPromptAgent
  -> Human Poster Option Review
  -> PosterImageAgent
  -> PosterQAReview
```

작업:

- 승인된 run 또는 review 가능한 run에서 poster context 생성
- 관광사진, 공모전 사진, detail image 후보 표시
- 포스터 목적, 타깃, 채널, 문구 길이, 금지 표현 입력 UI 추가
- PosterPromptAgent 구현
- 이미지 생성 모델 연동
- 생성 이미지와 prompt, 비용, source reference 저장
- Poster QA Review 구현

완료 기준:

- 특정 product에서 poster draft를 생성할 수 있다.
- 이미지 후보와 prompt reference의 출처를 볼 수 있다.
- 포스터 문구도 QA 검수를 통과해야 승인 가능하다.

## 다음 구현 시작점

바로 다음 구현은 Phase 12.1 Visual APIs부터 시작합니다. Phase 10 Data Enrichment Workflow, Phase 10.1 AppShell Navbar and Global Navigation, Phase 10.2 Gemini Data Enrichment Agent 전환, Phase 10.5 UI and Operations Surface Cleanup, Phase 11 Evidence-based ProductAgent Actualization, Phase 11.5 Gemini Planner/Research Actualization and LLM Call Surface Cleanup은 구현 완료 상태입니다. 99번 문서에 있는 추가 KTO API를 실제로 호출하고 저장해 상품 생성에 활용하는 작업은 Phase 12에서 `12.1 Visual APIs`, `12.2 Route/Related/Demand Signals`, `12.3 Theme APIs`로 나눠 진행합니다.

Codex에게 줄 다음 작업 범위:

```text
Phase 12.1: Visual APIs Actual Connection을 구현해줘.

범위:
- KTO 사진/이미지 계열 API를 실제 provider/executor로 연결
- 이미지 후보를 tourism_visual_assets/source_documents에 저장
- Evidence + QA와 상품 카드에서 이미지 근거를 후보 상태로 표시
- 실제 호출되지 않은 API를 호출된 것처럼 표시하지 않음
- backend test와 frontend build로 확인

주의:
- Phase 11/11.5 evidence 기반 Product/Research 흐름을 깨지 마.
- 지역 resolve 실패 시 전국 fallback하지 마.
- 구현되지 않은 API를 실제 작동하는 것처럼 보이게 하지 마.
```
