# 데이터 소스와 수집/정제 설계

## 데이터 전략 요약

MVP는 유료 데이터 없이 공공 데이터와 fixture/mock 데이터로 구현합니다.

주요 데이터 소스:

1. 한국관광공사 국문 관광정보 서비스_GW
2. 한국관광공사 지역별 관광 자원 수요 API
3. 자체 수집/정제 DB
4. 운영자가 업로드한 CSV/JSON
5. 평가용 golden dataset

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
| 지역코드 조회 | 부산/서울 같은 지역명을 API 코드로 변환 | `tourapi_area_code` |
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

MVP에서는 seed JSON으로 시작합니다.

```text
backend/app/fixtures/
  tourism_items_busan.json
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
    "event_end_date": null
  }
}
```

## 수집 방식

### On-demand fetch

사용자가 workflow를 실행할 때 필요한 데이터를 즉시 조회합니다.

장점:

- 항상 최신 데이터에 가깝습니다.
- 초기 DB 구축이 필요 없습니다.

단점:

- API rate limit에 영향을 받습니다.
- workflow latency가 길어질 수 있습니다.

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
- keyword fallback top_k 20

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

## 이미지 사용 주의

TourAPI 이미지 데이터는 공공누리 유형 등 라이선스 정보를 확인해야 합니다. 공공데이터포털 설명에는 사진 자료의 사용 제한 관련 주의가 포함되어 있으므로, 시스템은 이미지 URL을 상품 썸네일 후보로 제안하되 다음 문구를 남겨야 합니다.

```text
이미지 사용 전 공공누리 유형과 원 출처의 이용 조건을 확인하세요.
피사체 명예훼손, 인격권 침해, 기업 CI/BI 용도 사용 등 제한 사항에 유의해야 합니다.
```

## Mock provider 설계

실제 API 키 없이도 개발 가능해야 합니다.

```text
backend/app/fixtures/tourapi/
  area_code.json
  busan_area_based_list.json
  busan_search_festival_2026_05.json
  busan_search_stay.json
  busan_detail_common.json
  busan_detail_images.json
```

환경변수:

```env
TOURISM_PROVIDER=mock
TOURAPI_SERVICE_KEY=
```

값:

- `mock`: fixture만 사용
- `tourapi`: 실제 API만 사용
- `cached`: DB/cache 우선, miss 시 실제 API

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

- cache 우선 조회
- 같은 workflow run 안에서 동일 request 중복 호출 방지
- 429 response retry/backoff
- mock provider로 eval 실행 가능
- 운영계정 트래픽 증설은 실제 서비스 전 활용사례 등록 후 신청

## 데이터 소스별 신뢰도

| source | trust_level | 사용 방식 |
|---|---:|---|
| TourAPI official | 0.90 | 관광지/행사/숙박 기본 정보 |
| 관광 수요 API | 0.85 | 수요 지표/랭킹 보조 |
| 자체 운영 DB | 0.80 | 운영 정책/기존 상품 |
| 사용자 입력 | 0.70 | 요구사항, 제약조건 |
| LLM 생성 | 0.40 | 반드시 source와 QA 필요 |

생성 결과에서 `LLM 생성`만 근거로 하는 주장은 `assumption` 또는 `needs_review`가 됩니다.

