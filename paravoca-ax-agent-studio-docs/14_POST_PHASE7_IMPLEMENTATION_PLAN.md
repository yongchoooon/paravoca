# Phase 8 이후 구현 계획

작성 기준일: 2026-05-07

이 문서는 Phase 9.6까지 구현된 PARAVOCA AX Agent Studio를 기준으로, 평가와 배포 전에 보강해야 할 구현 단계를 다시 정리한 문서입니다. 기존 `11_IMPLEMENTATION_ROADMAP.md`의 Phase 8/9는 초기 계획 기준이며, 실제 다음 개발은 이 문서의 순서를 우선합니다.

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

## Phase 10: Data Enrichment Agent Workflow

목표:

- 현재 run의 요청, 수집 데이터, 상품 초안, QA 결과를 보고 필요한 데이터 보강만 실행하는 Agent workflow를 만든다.

추가 Agent:

- `BaselineDataAgent`
- `DataGapProfilerAgent`
- `ApiCapabilityRouterAgent`
- `DataEnrichmentAgent`
- `EvidenceFusionAgent`

workflow:

```text
Planner
  -> BaselineDataAgent
  -> DataGapProfilerAgent
  -> ApiCapabilityRouterAgent
  -> DataEnrichmentAgent
  -> EvidenceFusionAgent
  -> Research
  -> Product
  -> Marketing
  -> QA
  -> Human Approval
```

작업:

- 현재 Data Agent를 `BaselineDataAgent` 역할로 분리
- 데이터 공백을 `missing_detail_info`, `missing_image_asset`, `missing_related_places` 같은 구조로 생성
- gap type을 tool call plan으로 변환
- max call budget 적용
- enrichment run 생성/조회 API 추가
- 보강 결과를 source document와 signal table에 저장
- Data Coverage panel UI 추가
- Recommended Data Calls panel UI 추가

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
- `ApiCapabilityRouterAgent`: 부족한 정보를 어떤 KTO API나 공식 웹 근거 검색으로 채울지 계획한다.
- `DataEnrichmentAgent`: 계획된 API 호출을 실행하고 DB에 저장한다.
- `EvidenceFusionAgent`: 여러 API에서 온 정보를 같은 장소/상품 근거 묶음으로 병합한다.

주의:

- 모든 endpoint를 매번 호출하지 않는다.
- 이미 cache가 있고 TTL이 유효하면 API 호출을 건너뛴다.
- 의료관광 API는 별도 설정이 켜진 경우에만 라우팅한다.
- 수요, 혼잡도, 연관 관광지는 본문 사실처럼 쓰지 않고 운영 판단 신호로만 사용한다.

완료 기준:

- 이미지 없는 item에서 `missing_image_asset`이 생성된다.
- 운영 시간/요금/휴무가 부족하면 `missing_detail_info`가 생성된다.
- 반려동물, 도보, 웰니스 같은 요청은 해당 theme gap으로 분류된다.
- 불필요한 API를 매번 호출하지 않는다.

## Phase 10.5: Cached Fetch and Scheduled Sync

목표:

- 사용자가 실행할 때마다 모든 데이터를 새로 가져오는 구조에서 벗어나, 자주 쓰는 지역과 데이터는 미리 쌓아두고 갱신한다.

원칙:

- 전국 전체 데이터를 처음부터 모두 수집하지 않는다.
- 데모와 상품 품질에 중요한 지역부터 사전 수집한다.
- 사용자가 요청한 지역은 on-demand로 수집하고, 반복 사용되는 지역은 scheduled sync 대상으로 승격한다.
- TTL이 유효한 데이터는 API를 다시 호출하지 않고 cache를 사용한다.

우선 지역:

- 부산
- 서울
- 제주
- 강원
- 경주

권장 TTL:

| 데이터 | TTL |
|---|---:|
| 지역코드 | 30일 |
| 분류코드 | 30일 |
| 관광지 상세 | 7일 |
| 행사정보 | 1일 |
| 이미지정보 | 7일 |
| 관광사진/공모전 사진 | 7일 |
| 연관 관광지 | 7일 |
| 집중률 예측 | 1일 |
| 수요 지표 | 원 데이터 갱신 주기에 맞춤 |
| 공식 웹 근거 | 1일~7일, 가격/예약/취소 정책은 짧게 |

작업:

- cache lookup layer 추가
- `last_synced_at`, `retrieved_at`, TTL 기준 stale 판단
- 사전 수집 command 추가
- scheduled sync command 추가
- sync 대상 region/source family 설정 추가
- sync 실행 결과를 `enrichment_runs`와 `enrichment_tool_calls`에 기록
- 실패한 API 호출은 workflow 전체를 깨지 않되 sync log에 남김
- frontend Data Sources 화면에서 cache/sync 상태 표시

명령 후보:

```text
python -m app.data.sync --region-code 6 --source kto_tourapi_kor --mode detail
python -m app.data.sync --region-code 6 --source kto_tourism_photo --mode visual
python -m app.data.reindex --source source_documents
```

완료 기준:

- 부산 기본 데이터는 workflow 실행 전에 미리 source document와 Chroma에 쌓을 수 있다.
- workflow 실행 시 TTL이 유효한 데이터는 cache를 우선 사용한다.
- 새 지역 요청은 on-demand로 수집되고 이후 cache에 남는다.
- scheduled sync 결과와 실패 로그를 확인할 수 있다.

## Phase 11: Planner, Data, Research Agent 실제화

목표:

- 아직 규칙 기반에 가까운 Planner, Data, Research를 실제 evidence 기반 Agent로 바꾼다.

작업:

- Planner Agent를 Gemini structured output 기반으로 전환
- Planner output에 region, period, target, product_count, preferences, avoid, data_need_hints 포함
- Data Agent는 고정 호출이 아니라 enrichment plan을 실행
- Research Agent는 evidence profile을 읽고 지역/시즌/타깃/리스크를 요약
- Product Agent에 raw document list 대신 `evidence_profile`과 `productization_advice` 전달
- 사용자 입력의 `avoid` 항목과 기본 QA 검수 항목을 분리

완료 기준:

- Planner가 입력 요청을 구조화하고 검증 실패 시 명확한 에러를 남긴다.
- Research 결과가 실제 source evidence와 signal에 근거한다.
- Product/Marketing/QA가 같은 evidence profile을 공유한다.

## Phase 12: Visual, Related Places, Demand Signals

목표:

- 상품 구성, 이미지 후보, 수요 판단, 혼잡 리스크를 보강한다.

대상 API:

- 관광사진 정보_GW
- 관광공모전 사진 수상작 정보
- 관광지별 연관 관광지 정보
- 관광지 집중률 방문자 추이 예측 정보
- 관광빅데이터 정보서비스_GW

작업:

- 이미지 후보를 `tourism_visual_assets`에 저장
- 게시 가능 후보와 참고 후보를 분리
- 연관 관광지를 코스 조합 후보로 저장
- 방문 수요와 집중률을 `tourism_signal_records`에 저장
- Product ranking에 수요/혼잡/연관성 signal을 반영
- QA에서 혼잡/수요 신호를 확정 정보처럼 쓰지 않는지 검수
- Poster Studio에 넘길 visual hints 생성

완료 기준:

- Run Detail에서 상품별 이미지 후보를 볼 수 있다.
- 상품 초안이 주변 관광지/숙박/음식 조합 근거를 활용한다.
- 혼잡도는 경고 또는 대체 제안으로만 표시된다.
- 수요 데이터는 판매 보장 문구로 쓰이지 않는다.

## Phase 13: Theme-Specific KTO APIs

목표:

- 상품 카테고리를 일반 관광지 중심에서 테마형 상품으로 확장한다.

대상 API:

- 웰니스관광정보
- 반려동물 동반여행 서비스
- 두루누비 정보 서비스_GW
- 관광지 오디오 가이드정보_GW
- 생태 관광 정보_GW
- 의료관광정보

작업:

- 요청 의도에 따라 theme gap 생성
- theme별 provider method 추가
- theme 결과를 source document와 theme-specific table에 저장
- 반려동물 조건, 도보 코스, 오디오 해설, 생태 맥락을 상품 구성에 반영
- 의료관광 API는 `ALLOW_MEDICAL_API=true`일 때만 활성화

완료 기준:

- 반려동물 요청에서 pet policy 근거를 찾는다.
- 도보/트레킹 요청에서 두루누비 코스 근거를 찾는다.
- 외국인 문화/역사 요청에서 오디오 가이드 근거를 활용할 수 있다.
- 의료관광 데이터는 별도 설정 없이는 호출되지 않는다.

## Phase 14: Official Web Evidence + User Detail Request

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

## Phase 15: Evaluation

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

## Phase 16: Deployment / Demo Hardening

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

## Phase 17: Poster Studio

목표:

- 승인 가능 상태의 상품 결과를 바탕으로 포스터 생성 워크플로우를 만든다.

workflow:

```text
Approved or Reviewable Run
  -> PosterContextBuilder
  -> DataGapProfilerAgent
  -> ApiCapabilityRouterAgent
  -> VisualDataEnrichmentAgent
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

바로 다음 구현은 Phase 10 Data Enrichment Agent Workflow부터 시작합니다.

Codex에게 줄 첫 작업 범위:

```text
Phase 10: Data Enrichment Agent Workflow를 구현해줘.

범위:
- 현재 Phase 9.6의 GeoResolver/TourAPI v4.4 ldong/lcls/RAG metadata 구조를 유지
- DataGapAnalyzer, BaselineDataAgent, EvidenceFusionAgent 범위 확정
- TourAPI 상세 보강으로도 부족한 운영 시간, 예약 조건, 집결지, 가격/포함사항 공백을 구조화
- Product/Marketing/QA가 evidence와 data_gap을 더 강하게 사용하도록 연결
- 외부 웹 검색/grounding은 feature flag와 비용 한도 뒤에만 연결
- backend test와 frontend build로 확인

주의:
- 아직 관광사진/공모전/수요/혼잡/두루누비/웰니스 API는 붙이지 마.
- Gemini/OpenAI embedding은 기본값으로 쓰지 마.
- 기존 local CPU sentence-transformers embedding provider를 유지해 embedding API 비용이 발생하지 않게 해.
- TourAPI mock, fixture, fallback은 사용하지 마.
- 지역 resolve 실패 시 전국 fallback하지 마.
```
