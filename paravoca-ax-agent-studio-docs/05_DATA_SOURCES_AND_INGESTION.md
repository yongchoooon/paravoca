# 데이터 소스와 수집/정제 설계

## 데이터 전략 요약

MVP는 유료 데이터 없이 공공 데이터를 직접 호출해 구현합니다. TourAPI는 실제 한국관광공사 API만 사용합니다.

주요 데이터 소스:

1. 한국관광공사 국문 관광정보 서비스_GW
2. 한국관광공사 지역별 관광 자원 수요 API
3. 자체 수집/정제 DB
4. 운영자가 업로드한 CSV/JSON
5. 평가용 golden dataset

향후 확장 데이터 소스:

6. 웹 검색/검색 grounding 결과
7. 사용자가 workflow 실행 시 제공하는 상세 운영 정보

TourAPI는 관광지/행사/숙박의 공식 기본 정보를 제공하지만, 실제 상품화에는 운영 시간, 예약 가능 여부, 현장 동선, 집결지, 가격 조건, 최신 공지, 리뷰성 맥락, 공식 홈페이지 안내처럼 더 구체적인 정보가 필요할 수 있습니다. 따라서 MVP 이후에는 Data Agent가 TourAPI만으로 부족한 항목을 `data_gaps`로 표시하고, 웹 검색 또는 사용자 추가 입력으로 근거를 보강하는 흐름을 추가합니다.

한국관광공사 OpenAPI 묶음을 활용한 세부 보강 계획은 다음 하위 문서에 분리합니다.

- [05_01_KTO_OPENAPI_DATA_ENRICHMENT_PLAN.md](./05_01_KTO_OPENAPI_DATA_ENRICHMENT_PLAN.md): 관광사진, 웰니스, 의료, 반려동물, 두루누비, 오디오 가이드, 생태 관광, 관광빅데이터, 집중률 예측, 연관 관광지 데이터의 활용 계획
- [05_02_DATA_ENRICHMENT_AGENT_WORKFLOW.md](./05_02_DATA_ENRICHMENT_AGENT_WORKFLOW.md): 데이터 공백을 판단하고 필요한 API 호출을 선택하는 Agent, 저장 구조, UI, 구현 단계

## 한국관광공사 국문 관광정보 서비스

공공데이터포털 기준으로 국문 관광정보 서비스는 다음 특징을 갖습니다.

- 제공기관: 한국관광공사
- API 유형: REST
- 데이터 포맷: JSON + XML
- 비용: 무료
- 업데이트 주기: 실시간
- 개발계정 트래픽: 1,000
- 운영계정 트래픽: 활용사례 등록 시 증가 신청 가능
- 데이터 범위: 지역코드, 위치기반 관광정보, 키워드검색, 행사정보, 숙박정보, 이미지정보 등 15종 약 26만 건
- 수정일: 2026-02-26로 확인됨

공식 페이지:

- https://www.data.go.kr/data/15101578/openapi.do

## TourAPI 주요 기능 매핑

실제 operation 이름은 서비스 버전에 따라 `KorService1`, `KorService2` 등으로 바뀔 수 있습니다. 구현 시 공공데이터포털의 현재 Swagger/가이드를 기준으로 최종 endpoint를 확인해야 합니다.

MVP에서 필요한 기능:

| 기능 | 목적 | 내부 tool name |
|---|---|---|
| legacy 지역코드 조회 | 기존 `areaCode` 호환/응답 해석 | `tourapi_area_code` |
| 법정동 코드 조회 | TourAPI v4.4 시도/시군구 catalog sync와 지역 해석 | `tourapi_ldong_code` |
| 신분류체계 조회 | TourAPI v4.4 대/중/소분류 catalog sync와 테마 metadata | `tourapi_lcls_system_code` |
| 서비스분류코드 조회 | 관광지/문화시설/레포츠/숙박 등 분류 | `tourapi_category_code` |
| 지역기반 관광정보 | 특정 지역의 관광지 후보 조회 | `tourapi_area_based_list` |
| 위치기반 관광정보 | 좌표 중심 주변 관광지 조회 | `tourapi_location_based_list` |
| 키워드 검색 | "야경", "전통시장", "요트" 등 검색 | `tourapi_search_keyword` |
| 행사정보 | 기간 내 축제/행사 조회 | `tourapi_search_festival` |
| 숙박정보 | 주변 숙박 후보 조회 | `tourapi_search_stay` |
| 공통정보 | 상세 주소/개요/홈페이지 등 조회 | `tourapi_detail_common` |
| 소개정보 | content type별 상세 소개 | `tourapi_detail_intro` |
| 반복정보 | 이용시간/주차/요금 등 반복 세부 정보 | `tourapi_detail_info` |
| 이미지정보 | 대표/상세 이미지 조회 | `tourapi_detail_image` |

현재 구현 상태:

- Phase 9.6부터 workflow Data 단계는 GeoResolverAgent가 만든 `geo_scope`를 사용하고, primary 지역 필터는 `lDongRegnCd`/`lDongSignguCd`입니다.
- Phase 10부터 기본 수집은 `BaselineDataAgent`가 담당하고, 상세/이미지 보강은 `DataGapProfilerAgent`와 `ApiCapabilityRouterAgent`가 필요하다고 판단한 항목만 `EnrichmentExecutor`에서 실행합니다.
- `ldongCode2?lDongListYn=Y`와 `lclsSystmCode2`는 `python -m app.tools.sync_tourapi_catalogs`로 DB catalog에 동기화합니다.
- `areaCode2`는 backward compatibility와 legacy 응답 해석용으로 유지합니다.
- `areaBasedList2`, `searchKeyword2`, `searchFestival2`, `searchStay2`는 workflow Data 단계와 `/api/data/tourism/search`에서 사용하며, v4.4 `ldong/lcls` 파라미터를 우선 전달합니다.
- `detailCommon2`, `detailIntro2`, `detailInfo2`, `detailImage2`는 Phase 10에서 선택적 workflow 보강과 `/api/data/tourism/details/enrich`에 연결되어 있습니다.
- `categoryCode2`, `locationBasedList2`는 provider method와 capability catalog에 추가되어 있으나, route planning이나 ranking workflow에는 아직 직접 연결하지 않았습니다.
- Baseline raw 후보는 `TOURAPI_CANDIDATE_SHORTLIST_LIMIT` 기준으로 shortlist를 만든 뒤 Agent 입력과 상세 보강 대상으로 사용합니다.
- `ENRICHMENT_MAX_CALL_BUDGET`은 core KorService2 상세 보강을 6개로 자르는 용도가 아니라 future/non-core API 호출 예산 관리에 사용합니다. KorService2 상세 보강은 shortlist 안에서 실행 가능한 `contentId` 대상을 처리합니다. 수동 상세 보강 API의 기본 limit은 `TOURAPI_DETAIL_ENRICHMENT_LIMIT`를 유지합니다.

## 관광 수요 데이터

공공데이터포털의 `한국관광공사_지역별 관광 자원 수요` API는 관광 데이터랩의 관광수요지수에서 제공하는 관광 자원 수요 정보를 제공합니다. 설명 기준으로 신용카드, 이동통신, 내비게이션 등의 관광 빅데이터를 활용한 지표를 포함합니다.

공식 페이지:

- https://www.data.go.kr/data/15152138/openapi.do

MVP 활용:

- 지역별 관광 서비스 수요 조회
- 지역별 문화 자원 수요 조회
- 지역/기간별 수요 강도 score로 상품 후보 ranking에 반영

주의:

- 데이터 기간/갱신 주기/세부 필드는 실제 API 명세 확인 후 구현해야 합니다.
- 수요 지표는 상품 가격이나 매출을 직접 보장하는 데이터가 아닙니다.
- 생성 결과에서는 "수요가 높을 가능성" 정도로 표현하고, 확정적 매출 예측을 금지합니다.

## 자체 DB 데이터

운영자가 직접 관리할 수 있는 데이터입니다.

예시:

- 기존 판매 상품
- 취소/환불 정책
- 금지 표현 리스트
- 지역별 운영 난이도
- 협력사/공급사 메모
- 플랫폼 톤앤매너
- FAQ template
- 국가/언어별 고객 선호

MVP에서는 운영 정책/평가 데이터처럼 외부 API가 아닌 내부 기준 데이터만 seed JSON으로 시작할 수 있습니다. 관광 데이터는 TourAPI 실 API에서 수집합니다.

```text
backend/app/data/seed/
  existing_products.json
  compliance_rules.json
  faq_templates.json
  eval_dataset.jsonl
```

## 데이터 정규화 모델

### TourismItem

```json
{
  "id": "tourapi:content:12345",
  "source": "tourapi",
  "content_id": "12345",
  "content_type_id": "12",
  "title": "광안리해수욕장",
  "region_code": "6",
  "sigungu_code": "12",
  "address": "부산 ...",
  "map_x": 129.118,
  "map_y": 35.153,
  "tel": "...",
  "overview": "...",
  "homepage": "...",
  "image_url": "...",
  "license_type": "공공누리",
  "raw": {}
}
```

### TourismEvent

```json
{
  "id": "tourapi:event:67890",
  "source": "tourapi",
  "content_id": "67890",
  "title": "부산 바다축제",
  "region_code": "6",
  "event_start_date": "2026-05-10",
  "event_end_date": "2026-05-14",
  "address": "...",
  "overview": "...",
  "homepage": "...",
  "image_url": "...",
  "raw": {}
}
```

### SourceDocument

RAG와 출처 표시를 위한 normalized document입니다.

```json
{
  "id": "doc_...",
  "source": "tourapi",
  "source_id": "tourapi:content:12345",
  "title": "광안리해수욕장",
  "content": "주소: ... 개요: ... 이용시간: ...",
  "metadata": {
    "region_code": "6",
    "content_type": "attraction",
    "content_id": "12345",
    "license_type": "공공누리",
    "event_start_date": null,
    "event_end_date": null,
    "detail_common_available": true,
    "detail_intro_available": true,
    "detail_info_count": 3,
    "detail_image_count": 5,
    "visual_asset_count": 5,
    "image_candidates": []
  }
}
```

### WebEvidenceDocument

P2 이후 웹 검색/검색 grounding 결과를 RAG 근거로 저장하기 위한 문서입니다. 구현 우선순위는 MVP 이후이며, 기본 원칙은 웹 검색 결과를 LLM에 바로 넣기보다 출처 metadata와 함께 `source_documents`에 저장하고 tool call log를 남기는 것입니다.

```json
{
  "id": "doc:web:...",
  "source": "web",
  "source_id": "https://example.com/official-notice",
  "title": "공식 공지 또는 상세 안내 제목",
  "content": "검색 snippet, 페이지 요약, 확인된 핵심 정보",
  "metadata": {
    "url": "https://example.com/official-notice",
    "provider": "google_search_grounding",
    "query": "부산 요트 투어 운영 시간 2026",
    "retrieved_at": "2026-05-06T00:00:00+09:00",
    "published_at": null,
    "source_type": "official_site",
    "trust_level": 0.75,
    "license_note": "본문 재사용 조건 확인 필요"
  }
}
```

웹 근거 수집 대상:

- 공식 홈페이지/공지의 운영 시간, 휴무, 예약 정책
- 행사 주최 측의 최신 일정 변경 공지
- 집결지, 교통, 이동 동선, 현장 유의사항
- 가격/포함사항/취소 정책처럼 TourAPI에 없는 운영 정보
- 사용자가 제공한 공급사 메모, 내부 상품 조건, 현장 운영 제약

주의:

- 웹 검색 결과는 원문 출처 URL과 조회 시각을 반드시 보존합니다.
- 웹 문서 본문을 장문 복제하지 않고, 상품 검증에 필요한 짧은 근거 요약과 링크 중심으로 저장합니다.
- 비공식 블로그/커뮤니티 정보는 `needs_review`로 분리하고 확정 근거로 사용하지 않습니다.
- 가격, 예약 가능 여부, 운영 시간은 검색 시점 이후 바뀔 수 있으므로 최종 게시 전 운영자 확인 대상으로 남깁니다.

## 수집 방식

### On-demand fetch

사용자가 workflow를 실행할 때 필요한 데이터를 즉시 조회합니다.

장점:

- 항상 최신 데이터에 가깝습니다.
- 초기 DB 구축이 필요 없습니다.

단점:

- API rate limit에 영향을 받습니다.
- workflow latency가 길어질 수 있습니다.

현재 구현:

- workflow run 생성 시 Data 단계가 지역/키워드/행사/숙박 데이터를 조회합니다.
- 조회된 TourAPI item은 `tourism_items`에 저장합니다.
- Phase 9부터 Data 단계는 일부 item에 대해 content_id 기반 상세 보강을 실행합니다.
- 보강된 정보는 `tourism_items.raw.detail_common`, `detail_intro`, `detail_info`, `detail_images`에 저장하고, `source_documents`와 Chroma index를 갱신합니다.
- `detailImage2` 결과는 `tourism_visual_assets.usage_status=candidate`로 저장하며 바로 게시 가능 이미지로 보지 않습니다.
- `/api/data/tourism/search`는 기본적으로 기존 검색만 수행하고, `enrich_details=true`일 때 상세 보강까지 함께 수행합니다.

### Cached fetch

DB에 저장된 데이터를 먼저 조회하고, 없거나 오래된 경우 API를 호출합니다.

권장 TTL:

- 지역코드: 30일 이상
- 분류코드: 30일 이상
- 관광지 상세: 7일
- 행사정보: 1일
- 이미지정보: 7일
- 수요 지표: 데이터 갱신 주기에 맞춤

### Scheduled sync

P1에서 추가합니다.

예:

- 매일 03:00 행사정보 갱신
- 매주 월요일 주요 지역 관광지 상세 갱신
- 매월 지역 수요 지표 갱신

## 정제 규칙

### 텍스트 정제

- HTML tag 제거
- entity decode
- 과도한 whitespace 정리
- 빈 값/null 통일
- 너무 짧은 overview는 RAG chunk에서 제외
- 출처 URL 또는 content_id 보존

### 날짜 정규화

TourAPI에서 날짜가 `YYYYMMDD` 형태로 오면 `YYYY-MM-DD`로 변환합니다.

```python
def normalize_yyyymmdd(value: str | None) -> date | None:
    if not value or len(value) != 8:
        return None
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
```

### 지역 정규화

사용자 입력:

- 부산
- 부산광역시
- Busan

정규화:

```json
{
  "region_name": "부산",
  "region_code": "6",
  "country": "KR"
}
```

정확한 지역코드는 API response 기준 seed table을 만듭니다.

## Vector indexing

### Chunking

관광 아이템 1개를 너무 잘게 쪼개지 않습니다. TourAPI 항목은 대부분 짧기 때문에 item 단위 document로 시작합니다.

긴 상세 설명이 있을 경우:

- overview chunk
- usage/info chunk
- image/license chunk
- event/date chunk

현재 Phase 10 구현에서는 item 단위 source document를 유지하되, document content에 상세 소개와 이용정보를 함께 넣습니다. source document metadata에는 `ldong/lcls`, `source_family`, `trust_level`, `retrieved_at`, detail/image coverage 필드를 저장하고, 상세 소개/반복 정보가 충분히 길어지는 경우 chunk 분리는 후속 retrieval 품질 개선에서 조정합니다.

### Embedding text template

```text
제목: {title}
유형: {content_type}
지역: {region_name} {sigungu_name}
주소: {address}
기간: {event_start_date}~{event_end_date}
개요: {overview}
이용정보: {detail_info}
키워드: {keywords}
```

### Metadata filter

필수 metadata:

- `source`
- `region_code`
- `sigungu_code`
- `content_type`
- `content_id`
- `event_start_date`
- `event_end_date`
- `language`

Qdrant 사용 시 payload index 권장:

- `region_code`
- `content_type`
- `event_start_date`
- `event_end_date`
- `source`

## 검색 전략

### 1차 필터

- region_code 일치
- 요청 기간과 event date overlap
- target에 맞는 content_type preference

### 2차 hybrid query

검색 query 예:

```text
부산 외국인 야간 관광 전통시장 축제 액티비티
```

검색 결과:

- semantic top_k 20
- metadata filtered top_k 20
- metadata filtered top_k 20

### reranking

초기 MVP는 deterministic score로 충분합니다.

```text
score = vector_score
      + event_overlap_bonus
      + target_match_bonus
      + image_available_bonus
      + demand_score_bonus
      - missing_detail_penalty
```

### P2 웹 보강 검색

TourAPI/RAG 검색만으로 다음 항목이 부족하면 Data Agent가 웹 보강 검색 후보를 만듭니다.

- `missing_operating_hours`
- `missing_price_or_inclusion`
- `missing_booking_policy`
- `missing_meeting_point`
- `weak_event_date_evidence`
- `weak_official_source`

검색 실행 정책:

- 기본값은 비활성화하고 `web_search_enabled=true` 또는 운영자 승인 시에만 실행합니다.
- workflow run당 `max_queries`, query당 `result_limit`, timeout, cache TTL을 둡니다.
- 검색 결과는 `web_search` 또는 `google_search_grounding` tool call로 기록합니다.
- 같은 query와 region/period 조합은 cache를 우선 사용합니다.
- 검색 결과는 `source=web` 문서로 색인한 뒤 `vector_search`와 같은 retrieval 경로를 통해 downstream Agent에 전달합니다.

## 이미지 사용 주의

TourAPI 이미지 데이터는 공공누리 유형 등 라이선스 정보를 확인해야 합니다. 공공데이터포털 설명에는 사진 자료의 사용 제한 관련 주의가 포함되어 있으므로, 시스템은 이미지 URL을 상품 썸네일 후보로 제안하되 다음 문구를 남겨야 합니다.

```text
이미지 사용 전 공공누리 유형과 원 출처의 이용 조건을 확인하세요.
피사체 명예훼손, 인격권 침해, 기업 CI/BI 용도 사용 등 제한 사항에 유의해야 합니다.
```

## TourAPI provider 정책

TourAPI provider는 실제 API 호출만 수행합니다.

- `TOURAPI_SERVICE_KEY`가 없으면 provider 초기화/호출 단계에서 실패합니다.
- API 4xx/5xx/timeout은 실패로 기록합니다.
- TourAPI response의 top-level 또는 header result code가 성공이 아니면 실패로 기록합니다.
- 실패한 호출은 `tool_calls.status=failed`, `tool_calls.error`, workflow run error, FastAPI 로그로 확인합니다.
- RAG 검색은 현재 run에서 수집된 `source=tourapi` 문서만 근거로 사용합니다.

Phase 9 상세 보강 정책:

- `detailCommon2`는 content_id 기반 공통 상세를 확인하는 데 사용합니다.
- `detailIntro2`는 content type별 소개 정보를 확인하는 데 사용합니다.
- `detailInfo2`는 이용 시간, 주차, 휴무, 문의, 요금성 안내 같은 반복 정보를 확인하는 데 사용합니다.
- `detailImage2`는 이미지 후보 수집에만 사용하며, 사용 가능 여부는 별도 검토 대상으로 둡니다.
- 가격, 예약 가능 여부, 운영 여부는 TourAPI 상세 응답만으로 확정하지 않습니다.

MVP 이후 웹 보강 검색이 켜진 경우에는 `source=tourapi` 문서와 `source=web` 문서를 함께 검색할 수 있습니다. 이때 상품 생성/QA에서는 source별 신뢰도를 구분하고, 웹 근거만 있는 주장은 `needs_review` 또는 운영자 확인 대상으로 표시합니다.

## 데이터 품질 체크

수집 후 다음 체크를 수행합니다.

- title empty 여부
- region_code 존재 여부
- coordinate 유효성
- event_start_date <= event_end_date
- overview 길이
- image_url scheme
- duplicate content_id
- source/license metadata 존재 여부

품질 결과는 `data_quality_flags`에 저장합니다.

예:

```json
[
  {"type": "missing_image", "severity": "low"},
  {"type": "missing_event_end_date", "severity": "medium"}
]
```

## API 키와 트래픽 관리

TourAPI 개발계정 트래픽은 제한이 있으므로 다음을 구현합니다.

- 같은 workflow run 안에서 동일 request 중복 호출 방지
- 429 response retry/backoff
- 운영계정 트래픽 증설은 실제 서비스 전 활용사례 등록 후 신청

## 데이터 소스별 신뢰도

| source | trust_level | 사용 방식 |
|---|---:|---|
| TourAPI official | 0.90 | 관광지/행사/숙박 기본 정보 |
| 관광 수요 API | 0.85 | 수요 지표/랭킹 보조 |
| 자체 운영 DB | 0.80 | 운영 정책/기존 상품 |
| 공식 웹사이트/공지 | 0.75 | 최신 운영 시간, 예약/행사 변경 정보 |
| 검색 grounding 결과 | 0.70 | TourAPI에 없는 최신 세부 정보 보강 |
| 사용자 입력 | 0.70 | 요구사항, 제약조건 |
| 비공식 웹문서 | 0.50 | 트렌드/맥락 참고, 확정 근거로 사용 금지 |
| LLM 생성 | 0.40 | 반드시 source와 QA 필요 |

생성 결과에서 `LLM 생성`만 근거로 하는 주장은 `assumption` 또는 `needs_review`가 됩니다.
