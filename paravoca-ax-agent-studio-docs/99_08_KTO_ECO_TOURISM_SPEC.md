# 99-08. 한국관광공사 생태 관광 정보_GW API 명세

작성 기준일: 2026-05-07

이 문서는 `API명세서` 폴더의 원본을 PARAVOCA 구현 기준으로 정규화한 내부 API 명세입니다. 원본의 endpoint 이름과 응답 필드명은 그대로 보존하고, 서비스마다 달랐던 출력 형식을 공통 Markdown 구조로 맞췄습니다.

## 원본과 범위

| 항목 | 값 |
|---|---|
| 원본 입력 파일 | `API명세서/한국관광공사_생태 관광 정보_GW` |
| 공식 페이지 | https://www.data.go.kr/data/15101908/openapi.do |
| PARAVOCA source_family | `kto_eco` |
| 데이터 성격 | `theme` |
| 활용 목적 | 생태, 자연, 친환경, 공정관광 성격의 지역 관광 자원을 상품 후보와 ESG 문맥 근거로 사용합니다. |

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
| 1 | `areaBasedList1` | `/areaBasedList1` | 지역기반 생태관광정보 조회 | 1000 | 상단 상세기능 |
| 2 | `areaBasedSyncList1` | `/areaBasedSyncList1` | 생태관광정보 동기화 관광정보 조회 | 1000 | 상단 상세기능 |
| 3 | `areaCode1` | `/areaCode1` | 지역코드조회 | 1000 | 상단 상세기능 |

## 구현 주의

- 친환경 효과를 수치로 단정하지 않고, 보호구역/계절 제한/탐방 예절은 추가 확인 대상으로 둡니다.

## Operation 상세

### 1. `areaBasedList1` 지역기반 생태관광정보 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/areaBasedList1` |
| 설명 | 지역 및 시군구를 기반으로 생태관광정보 목록을 조회하는 기능입니다. 파라미터에 따라 제목순, 수정일순(최신순), 등록일순, 정렬검색을 제공합니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `areaBasedList_header`, `areaBasedList_body`, `areaBasedList_items`, `areaBasedList_item` |

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
| `tel` | `string` | 전화번호 |
| `telname` | `string` | 전화번호명 |
| `title` | `string` | 제목 |
| `addr` | `string` | 주소 |
| `areacode` | `string` | 지역코드 |
| `mainimage` | `string` | 대표이미지(원본) |
| `modifiedtime` | `string` | 수정일 |
| `cpyrhtDivCd` | `string` | 저작권 유형 (Type1:제1유형(출처표시-권장), Type3:제3유형(제1유형+변경금지) |
| `createdtime` | `string` | 등록일 |
| `contentid` | `string` | 콘텐츠ID |
| `sigungucode` | `string` | 시군구코드 |
| `subtitle` | `string` | 소제목 |
| `summary` | `string` | 개요 |

### 2. `areaBasedSyncList1` 생태관광정보 동기화 관광정보 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/areaBasedSyncList1` |
| 설명 | 생태관광정보 내용을 동기화으로 목록을 조회하는 기능 |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `areaBasedSyncList_header`, `areaBasedSyncList_body`, `areaBasedSyncList_items`, `areaBasedSyncList_item` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultMsg` | `string` | API 호출 결과의 상태 |
| `resultCode` | `string` | API 호출 결과의 상태 코드 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `totalCount` | `number` | 전체 데이터의 총 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `cpyrhtDivCd` | `string` | 저작권 유형 (Type1:제1유형(출처표시-권장), Type3:제3유형(제1유형+변경금지) |
| `areacode` | `string` | 지역코드 |
| `addr` | `string` | 주소 |
| `contentid` | `string` | 콘텐츠ID |
| `createdtime` | `string` | 등록일 |
| `mainimage` | `string` | 대표이미지(원본) |
| `modifiedtime` | `string` | 수정일 |
| `showflag` | `string` | 표출여부 |
| `sigungucode` | `string` | 시군구코드 |
| `subtitle` | `string` | 소제목 |
| `summary` | `string` | 개요 |
| `title` | `string` | 제목 |
| `telname` | `string` | 전화번호명 |
| `tel` | `string` | 전화번호 |

### 3. `areaCode1` 지역코드조회

| 항목 | 값 |
|---|---|
| Endpoint | `/areaCode1` |
| 설명 | 지역코드, 시군구코드 목록을 조회하는 기능입니다. 지역기반 생태관광정보를 통해 지역별로 목록을 보여줄 경우, 지역코드를 이용하여 지역명을 매칭하기 위한 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `areaCode_header`, `areaCode_body`, `areaCode_items`, `areaCode_item` |

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
| `code` | `string` | 코드 : 지역코드또는시군구코드 |
| `name` | `string` | 코드명 : 지역명또는시군구명 |
| `rnum` | `string` | 일련번호 |
