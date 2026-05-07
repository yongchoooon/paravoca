# 99-06. 한국관광공사 두루누비 정보 서비스_GW API 명세

작성 기준일: 2026-05-07

이 문서는 `API명세서` 폴더의 원본을 PARAVOCA 구현 기준으로 정규화한 내부 API 명세입니다. 원본의 endpoint 이름과 응답 필드명은 그대로 보존하고, 서비스마다 달랐던 출력 형식을 공통 Markdown 구조로 맞췄습니다.

## 원본과 범위

| 항목 | 값 |
|---|---|
| 원본 입력 파일 | `API명세서/한국관광공사_두루누비 정보 서비스_GW` |
| 공식 페이지 | https://www.data.go.kr/data/15101974/openapi.do |
| PARAVOCA source_family | `kto_durunubi` |
| 데이터 성격 | `route` |
| 활용 목적 | 걷기길/자전거길 코스, 길 설명, 난이도, 거리, GPX 경로를 route형 상품 근거로 사용합니다. |

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
| 1 | `courseList` | `/courseList` | 코스 목록 정보 조회 | 1000 | 상단 상세기능 |
| 2 | `routeList` | `/routeList` | 길 목록 정보 조회 | 1000 | 상단 상세기능 |

## 구현 주의

- 코스 경로와 현장 운영 동선은 다를 수 있으므로 날씨, 안전, 집결/해산 지점은 운영자가 최종 확인합니다.

## Operation 상세

### 1. `courseList` 코스 목록 정보 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/courseList` |
| 설명 | 코스 목록 정보를 조회하는 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `courseList_response` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultCode` | `string` | API 호출 결과의 상태 코드 |
| `resultMsg` | `string` | API 호출 결과의 상태 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `totalCount` | `number` | 전체 데이터의 총 수 |
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `createdtime` | `string` | createdtime |
| `travelerinfo` | `string` | travelerinfo |
| `crsTourInfo` | `string` | crsTourInfo |
| `crsSummary` | `string` | crsSummary |
| `routeIdx` | `string` | routeIdx |
| `crsIdx` | `string` | crsIdx |
| `crsKorNm` | `string` | crsKorNm |
| `crsDstnc` | `string` | crsDstnc |
| `crsTotlRqrmHour` | `string` | crsTotlRqrmHour |
| `modifiedtime` | `string` | modifiedtime |
| `sigun` | `string` | sigun |
| `brdDiv` | `string` | brdDiv |
| `gpxpath` | `string` | gpxpath |
| `crsLevel` | `string` | crsLevel |
| `crsCycle` | `string` | crsCycle |
| `crsContents` | `string` | crsContents |

### 2. `routeList` 길 목록 정보 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/routeList` |
| 설명 | 길 목록 정보를 조회하는 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `routeList_response` |

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
| `createdtime` | `string` | 등록일 |
| `modifiedtime` | `string` | 수정일 |
| `routeIdx` | `string` | 길 고유번호 |
| `themeNm` | `string` | 길 명 |
| `linemsg` | `string` | 한줄소개 |
| `themedescs` | `string` | 상세 설명 |
| `brdDiv` | `string` | 걷기/자전거 구분 |
