# 99-02. 한국관광공사 관광공모전 사진 수상작 정보 API 명세

작성 기준일: 2026-05-07

이 문서는 `API명세서` 폴더의 원본을 PARAVOCA 구현 기준으로 정규화한 내부 API 명세입니다. 원본의 endpoint 이름과 응답 필드명은 그대로 보존하고, 서비스마다 달랐던 출력 형식을 공통 Markdown 구조로 맞췄습니다.

## 원본과 범위

| 항목 | 값 |
|---|---|
| 원본 입력 파일 | `API명세서/한국관광공사_관광공모전(사진) 수상작 정보` |
| 공식 페이지 | https://www.data.go.kr/data/15145706/openapi.do |
| PARAVOCA source_family | `kto_photo_contest` |
| 데이터 성격 | `visual` |
| 활용 목적 | 포토코리아 관광공모전 사진 부문 수상작을 지역/키워드 기반 이미지 후보와 포스터 참고 근거로 사용합니다. |

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
| 1 | `ldongCode` | `/ldongCode` | 법정동 코드 조회 | 1000 | 상단 상세기능 |
| 2 | `phokoAwrdList` | `/phokoAwrdList` | 관광공모전(사진) 수상작 정보 목록 조회 | 1000 | 상단 상세기능 |
| 3 | `phokoAwrdSyncList` | `/phokoAwrdSyncList` | 관광공모전(사진) 수상작 정보 동기화 목록 조회 | 1000 | 상단 상세기능 |

## 구현 주의

- 이미지 게시 가능 여부와 AI 생성 참고 용도를 분리하고, 저작권 유형과 출처 표시 조건을 UI/QA에서 확인합니다.

## Operation 상세

### 1. `ldongCode` 법정동 코드 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/ldongCode` |
| 설명 | 법정동 코드정보를 조회하는 기능입니다. 지역기반 수상작 정보를 지역 별로 목록을 보여줄 경우, 법정동 코드를 이용하여 법정동명을 매칭하기 위한 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `ldongCode_response` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultMsg` | `string` | API 호출 결과의 상태 메시지 |
| `resultCode` | `string` | API 호출 결과의 상태 코드 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |
| `totalCount` | `number` | 전체 데이터의 총 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `rnum` | `string` | 일련번호 |
| `lDongRegnCd` | `string` | 법정동 시도 코드 |
| `lDongRegnNm` | `string` | 법정동 시도명 |

### 2. `phokoAwrdList` 관광공모전(사진) 수상작 정보 목록 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/phokoAwrdList` |
| 설명 | 키워드 또는 법정동 코드로 검색하여 관광공모전 사진 부문 수상작 목록을 조회하는 기능입니다. 정렬 구분 파라미터를 통해 제목순, 수정일순(최신순), 생성일순 정렬검색을 제공합니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `phokoAwrdList_response` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultMsg` | `string` | API 호출 결과의 상태 메시지 |
| `resultCode` | `string` | API 호출 결과의 상태 코드 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |
| `totalCount` | `number` | 전체 데이터의 총 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `regDt` | `string` | 콘텐츠 최초 등록일 |
| `mdfcnDt` | `string` | 콘텐츠 수정일 |
| `contentId` | `string` | 콘텐츠 ID |
| `koTitle` | `string` | 콘텐츠명(국문) |
| `enTitle` | `string` | 콘텐츠명(영문) |
| `lDongRegnCd` | `string` | 법정동 시도 코드 |
| `koFilmst` | `string` | 촬영 장소(국문) |
| `enFilmst` | `string` | 촬영 장소(영문) |
| `filmDay` | `string` | 촬영 연월 |
| `koCmanNm` | `string` | 촬영자(국문) |
| `enCmanNm` | `string` | 촬영자(영문) |
| `koWnprzDiz` | `string` | 수상작(국문) |
| `enWnprzDiz` | `string` | 수상작(영문) |
| `koKeyWord` | `string` | 키워드(국문) |
| `enKeyWord` | `string` | 키워드(영문) |
| `orgImage` | `string` | 원본 대표 이미지 URL 응답 |
| `thumbImage` | `string` | 썸네일 대표 이미지 URL 응답 |
| `cpyrhtDivCd` | `string` | 이미지 저작권 유형 - Type1: 제1유형(출처표시-권장) |

### 3. `phokoAwrdSyncList` 관광공모전(사진) 수상작 정보 동기화 목록 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/phokoAwrdSyncList` |
| 설명 | 관광공모전 사진 부문 수상작 동기화 목록을 조회하는 기능입니다. 정렬구분 파라미터에 따라 제목순, 수정일순(최신순), 생성일순 정렬검색을 제공합니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `phokoAwrdSyncList_response` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultMsg` | `string` | API 호출 결과의 상태 메시지 |
| `resultCode` | `string` | API 호출 결과의 상태 코드 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |
| `totalCount` | `number` | 전체 데이터의 총 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `mdfcnDt` | `string` | 콘텐츠 수정일 |
| `showflag` | `string` | 콘텐츠표출여부 (1=표출, 0=비표출) |
| `contentId` | `string` | 콘텐츠 ID |
| `koTitle` | `string` | 콘텐츠명(국문) |
| `enTitle` | `string` | 콘텐츠명(영문) |
| `lDongRegnCd` | `string` | 법정동 시도 코드 |
| `koFilmst` | `string` | 촬영 장소(국문) |
| `enFilmst` | `string` | 촬영 장소(영문) |
| `filmDay` | `string` | 촬영 연월 |
| `koCmanNm` | `string` | 촬영자(국문) |
| `enCmanNm` | `string` | 촬영자(영문) |
| `koWnprzDiz` | `string` | 수상작(국문) |
| `enWnprzDiz` | `string` | 수상작(영문) |
| `koKeyWord` | `string` | 키워드(국문) |
| `enKeyWord` | `string` | 키워드(영문) |
| `orgImage` | `string` | 원본 대표 이미지 URL 응답 |
| `thumbImage` | `string` | 썸네일 대표 이미지 URL 응답 |
| `cpyrhtDivCd` | `string` | 이미지 저작권 유형 - Type1: 제1유형(출처표시-권장) |
| `regDt` | `string` | 콘텐츠 최초 등록일 |
