# 99-12. 한국관광공사 관광지별 연관 관광지 정보 API 명세

작성 기준일: 2026-05-07

이 문서는 `API명세서` 폴더의 원본을 PARAVOCA 구현 기준으로 정규화한 내부 API 명세입니다. 원본의 endpoint 이름과 응답 필드명은 그대로 보존하고, 서비스마다 달랐던 출력 형식을 공통 Markdown 구조로 맞췄습니다.

## 원본과 범위

| 항목 | 값 |
|---|---|
| 원본 입력 파일 | `API명세서/한국관광공사_관광지별 연관 관광지 정보` |
| 공식 페이지 | https://www.data.go.kr/data/15128560/openapi.do |
| PARAVOCA source_family | `kto_related_places` |
| 데이터 성격 | `signal` |
| 활용 목적 | 관광지와 연관 관광지의 지역/분류/순위를 코스 확장 후보와 주변 대체지 추천 근거로 사용합니다. |

원본에는 서비스별 상세기능 목록과 response schema가 중심으로 들어 있습니다. 요청 파라미터 표가 없는 operation은 endpoint와 응답 schema만 확정 정보로 기록하고, 실제 구현 직전 공식 Swagger/활용신청 페이지에서 필수 요청 파라미터를 재확인해야 합니다.

## 공통 호출 규칙

- 공공데이터포털 REST GET 서비스로 취급합니다.
- 인증키, 응답 타입, paging 파라미터 이름은 서비스별 공식 Swagger에서 최종 확인합니다.
- JSON 응답의 `items.item`은 단일 object 또는 list로 올 수 있으므로 provider에서 항상 list로 정규화합니다.
- `resultCode != "0000"`이면 tool call 실패로 기록합니다.
- 빈 결과는 API 실패가 아닐 수 있지만, 지역/키워드/기간 필터가 빠져 전국 fallback이 되는 것은 실패로 봅니다.

## Operation 목록

| 번호 | Operation | Endpoint | 설명 | 일일 트래픽 | 출처 |
|---:|---|---|---|---:|---|
| 1 | `areaBasedList1` | `/areaBasedList1` | 지역기반 관광지별 연관 관광지 정보 목록 조회 | 1000 | 상단 상세기능 |
| 2 | `searchKeyword1` | `/searchKeyword1` | 키워드 검색 관광지별 연관 관광지 정보 목록 조회 | 1000 | 상단 상세기능 |

## 구현 주의

- 연관성은 이동/방문 패턴 기반 참고 신호로만 사용하고, 실제 동선 가능성은 좌표/교통/운영 조건으로 다시 검증합니다.

## Operation 상세

### 1. `areaBasedList1` 지역기반 관광지별 연관 관광지 정보 목록 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/areaBasedList1` |
| 설명 | 시군구를 기반으로 관광지별 연관 관광지 정보 목록을 조회하는 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `areaBasedList1_response` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultCode` | `string` | API 호출 결과의 상태 코드 |
| `resultMsg` | `string` | API 호출 결과의 상태 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |
| `totalCount` | `number` | 전체 데이터의 총 수 |
| `numOfRows` | `number` | 한 페이지의 결과 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `rlteCtgryMclsNm` | `string` | 연관관광지 중분류명 |
| `rlteCtgrySclsNm` | `string` | 연관관광지 소분류명 |
| `rlteRank` | `string` | 연관 순위 |
| `baseYm` | `string` | 기준연월 |
| `tAtsNm` | `string` | 관광지명 |
| `areaCd` | `string` | 관광지 지역코드 |
| `areaNm` | `string` | 관광지 지역명 |
| `signguCd` | `string` | 관광지 시군구코드 |
| `signguNm` | `string` | 관광지 시군구명 |
| `rlteTatsNm` | `string` | 연관관광지명 |
| `rlteRegnCd` | `string` | 연관관광지 지역코드 |
| `rlteRegnNm` | `string` | 연관관광지 지역명 |
| `rlteSignguCd` | `string` | 연관관광지 시군구코드 |
| `rlteSignguNm` | `string` | 연관관광지 시군구명 |
| `rlteCtgryLclsNm` | `string` | 연관관광지 대분류명 |
| `tAtsCd` | `string` | 관광지코드 |
| `rlteTatsCd` | `string` | 연관관광지코드 |

### 2. `searchKeyword1` 키워드 검색 관광지별 연관 관광지 정보 목록 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/searchKeyword1` |
| 설명 | 키워드 검색 관광지별 연관 관광지 정보 관광지 키워드 검색을 하여 관광지별 연관 관광지 정보 목록을 조회하는 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `searchKeyword1_response` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultCode` | `string` | API 호출 결과의 상태 코드 |
| `resultMsg` | `string` | API 호출 결과의 상태 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |
| `totalCount` | `number` | 전체 데이터의 총 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `rlteCtgryMclsNm` | `string` | 연관관광지 중분류명 |
| `rlteCtgrySclsNm` | `string` | 연관관광지 소분류명 |
| `rlteRank` | `string` | 연관 순위 |
| `baseYm` | `string` | 기준연월 |
| `tAtsNm` | `string` | 관광지명 |
| `areaCd` | `string` | 관광지 지역코드 |
| `areaNm` | `string` | 관광지 지역명 |
| `signguCd` | `string` | 관광지 시군구코드 |
| `signguNm` | `string` | 관광지 시군구명 |
| `rlteTatsNm` | `string` | 연관관광지명 |
| `rlteRegnCd` | `string` | 연관관광지 지역코드 |
| `rlteRegnNm` | `string` | 연관관광지 지역명 |
| `rlteSignguCd` | `string` | 연관관광지 시군구코드 |
| `rlteSignguNm` | `string` | 연관관광지 시군구명 |
| `rlteCtgryLclsNm` | `string` | 연관관광지 대분류명 |
| `tAtsCd` | `string` | 관광지코드 |
| `rlteTatsCd` | `string` | 연관관광지코드 |
