# 99-11. 한국관광공사 관광지 집중률 방문자 추이 예측 정보 API 명세

작성 기준일: 2026-05-07

이 문서는 `API명세서` 폴더의 원본을 PARAVOCA 구현 기준으로 정규화한 내부 API 명세입니다. 원본의 endpoint 이름과 응답 필드명은 그대로 보존하고, 서비스마다 달랐던 출력 형식을 공통 Markdown 구조로 맞췄습니다.

## 원본과 범위

| 항목 | 값 |
|---|---|
| 원본 입력 파일 | `API명세서/한국관광공사_관광지 집중률 방문자 추이 예측 정보` |
| 공식 페이지 | https://www.data.go.kr/data/15128555/openapi.do |
| PARAVOCA source_family | `kto_crowding_forecast` |
| 데이터 성격 | `signal` |
| 활용 목적 | 관광지별 향후 30일 집중률을 혼잡 리스크와 운영 난이도 판단의 보조 신호로 사용합니다. |

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
| 1 | `tatsCnctrRatedList` | `/tatsCnctrRatedList` | 관광지 집중률 정보 목록조회 | 1000 | 상단 상세기능 |

## 구현 주의

- 집중률은 예측/보조 지표이며 실제 현장 혼잡을 보장하지 않습니다. 운영 일정 확정 전 최신 정보를 재확인합니다.

## Operation 상세

### 1. `tatsCnctrRatedList` 관광지 집중률 정보 목록조회

| 항목 | 값 |
|---|---|
| Endpoint | `/tatsCnctrRatedList` |
| 설명 | 관광지별 향후 30일 관광객 집중률 정보를 목록을 조회하는 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `tatsCnctrRatedList_response` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultMsg` | `string` | API 호출 결과의 상태 |
| `resultCode` | `string` | API 호출 결과의 상태 코드 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `totalCount` | `number` | 전체 데이터의 총 수 |
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `cnctrRate` | `string` | 집중률 |
| `baseYmd` | `string` | 기준연월일 |
| `areaCd` | `string` | 지역코드 |
| `areaNm` | `string` | 지역명 |
| `signguCd` | `string` | 시군구코드 |
| `signguNm` | `string` | 시군구명 |
| `tAtsNm` | `string` | 관광지명 |
