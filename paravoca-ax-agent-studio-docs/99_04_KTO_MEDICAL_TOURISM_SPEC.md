# 99-04. 한국관광공사 의료관광정보 API 명세

작성 기준일: 2026-05-07

이 문서는 `API명세서` 폴더의 원본을 PARAVOCA 구현 기준으로 정규화한 내부 API 명세입니다. 원본의 endpoint 이름과 응답 필드명은 그대로 보존하고, 서비스마다 달랐던 출력 형식을 공통 Markdown 구조로 맞췄습니다.

## 원본과 범위

| 항목 | 값 |
|---|---|
| 원본 입력 파일 | `API명세서/한국관광공사_의료관광정보` |
| 공식 페이지 | https://www.data.go.kr/data/15143913/openapi.do |
| PARAVOCA source_family | `kto_medical` |
| 데이터 성격 | `theme/high_risk` |
| 활용 목적 | 의료관광 자원, 서비스 언어, 의료관광 상세 속성을 외국인 대상 상품의 고위험 검수 근거로 사용합니다. |

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
| 2 | `areaBasedList` | `/areaBasedList` | 지역기반 관광정보 조회 | 1000 | 상단 상세기능 |
| 3 | `locationBasedList` | `/locationBasedList` | 위치기반 관광정보 조회 | 1000 | 상단 상세기능 |
| 4 | `searchKeyword` | `/searchKeyword` | 키워드 검색 조회 | 1000 | 상단 상세기능 |
| 5 | `mdclTursmSyncList` | `/mdclTursmSyncList` | 의료관광정보 동기화 목록 조회 | 1000 | 상단 상세기능 |
| 6 | `detailCommon` | `/detailCommon` | 공통정보 조회 | 1000 | 상단 상세기능 |
| 7 | `detailIntro` | `/detailIntro` | 소개정보 조회 | 1000 | 상단 상세기능 |
| 8 | `detailMdclTursm` | `/detailMdclTursm` | 의료관광정보 조회 | 1000 | 상단 상세기능 |
| 9 | `lclsSystmCode` | `/lclsSystmCode` | lclsSystmCode 응답 schema |  | response schema만 있음 |
| 10 | `detailInfo` | `/detailInfo` | detailInfo 응답 schema |  | response schema만 있음 |
| 11 | `detailImage` | `/detailImage` | detailImage 응답 schema |  | response schema만 있음 |

## 구현 주의

- 의료 효과, 안전성, 가격, 예약 가능 여부를 확정 표현하지 않습니다. 의료 광고성 표현은 운영자 검토 대상으로 분리합니다.
- 일부 response schema는 원본 상단 상세기능 목록에 없지만 하단 schema에 존재합니다. 해당 operation은 endpoint명을 schema명 기준으로 추정했으므로 구현 전 공식 Swagger에서 노출 여부를 확인해야 합니다.

## Operation 상세

### 1. `ldongCode` 법정동 코드 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/ldongCode` |
| 설명 | 법정동 코드 목록을 지역,시군구, 읍면동 코드 목록을 조회하는 기능 지역기반 관광정보 및 키워드 검색 등을 통해 지역 별로 목록을 보여줄 경우, 법정동 코드를 이용하여 법정동명을 매칭하기 위한 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `ldongCode_response` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultCode` | `string` | API 호출 결과의 상태 코드 |
| `resultMsg` | `string` | API 호출 결과의 상태 메시지 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |
| `totalCount` | `number` | 전체 데이터의 총 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `lDongSignguNm` | `string` | 법정동 시군구명 (lDongListYn : Y일때 표출) |
| `rnum` | `string` | 일련번호 |
| `name` | `string` | 법정동 : 시도명, 시군구명 (lDongListYn : N일때 표출) |
| `code` | `string` | 법정동 : 시도코드, 시군구코드 (lDongListYn : N일때 표출) |
| `lDongRegnCd` | `string` | 법정동 시도코드 (lDongListYn : Y일때 표출) |
| `lDongRegnNm` | `string` | 법정동 시도명 (lDongListYn : Y일때 표출) |
| `lDongSignguCd` | `string` | 법정동 시군구코드 (lDongListYn : Y일때 표출) |

### 2. `areaBasedList` 지역기반 관광정보 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/areaBasedList` |
| 설명 | 지역 및 시군구를 기반으로 관광정보 목록을 조회하는 기능입니다. 파라미터에 따라 제목순, 수정일순(최신순), 등록일순, 인기순 정렬 검색을 제공합니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `areaBasedList_response` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultMsg` | `string` | API 호출 결과의 상태 메시지 |
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
| `langDivCd` | `string` | 언어 구분 코드(영문: ENG, 일문: JPN, 중간: CHS, 노어: RUS) |
| `baseAddr` | `string` | 주소(예, 서울 중구 다동)를 응답 |
| `detailAddr` | `string` | 상세주소 |
| `zipCd` | `string` | 우편번호 |
| `contentId` | `string` | 콘텐츠ID |
| `regDt` | `string` | 콘텐츠 최초 등록일 |
| `orgImage` | `string` | 원본 대표 이미지(현재 이미지 없음, 추후 추가 예정) |
| `thumbImage` | `string` | 썸네일 대표 이미지(현재 이미지 없음, 추후 추가 예정) |
| `cpyrhtDivCd` | `string` | 대표이미지 저작권 유형 - Type1: 제1유형(출처표시-권장), Type3: 제3유형(제1유형+변경금지) |
| `mapX` | `string` | GPS X좌표(WGS84 경도 좌표) 응답 |
| `mapY` | `string` | GPS Y좌표(WGS84 위도 좌표) 응답 |
| `mlevel` | `string` | Map Level 응답 |
| `mdfcnDt` | `string` | 콘텐츠 수정일 |
| `tel` | `string` | 전화번호 |
| `title` | `string` | 콘텐츠 제목 |
| `lDongRegnCd` | `string` | 법정동 시도코드 |
| `lDongSignguCd` | `string` | 법정동 시군구코드 |

### 3. `locationBasedList` 위치기반 관광정보 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/locationBasedList` |
| 설명 | 내 주변 좌표를 기반으로 관광정보 목록을 조회하는 기능입니다. 파라미터에 따라 제목순, 수정일순(최신순), 등록일순, 인기순, 거리순 정렬 검색을 제공합니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `locationBasedList_response` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultCode` | `string` | API 호출 결과의 상태 코드 |
| `resultMsg` | `string` | API 호출 결과의 상태 메시지 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `totalCount` | `number` | 전체 데이터의 총 수 |
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `lDongSignguCd` | `string` | 법정동 시군구코드 |
| `dist` | `string` | 거리(단위: m) |
| `langDivCd` | `string` | 언어 구분 코드(영문: ENG, 일문: JPN, 중간: CHS, 노어: RUS) |
| `baseAddr` | `string` | 주소(예, 서울 중구 다동)를 응답 |
| `detailAddr` | `string` | 상세주소 |
| `zipCd` | `string` | 우편번호 |
| `contentId` | `string` | 콘텐츠ID |
| `regDt` | `string` | 콘텐츠 최초 등록일 |
| `orgImage` | `string` | 원본 대표 이미지(현재 이미지 없음, 추후 추가 예정) |
| `thumbImage` | `string` | 썸네일 대표 이미지(현재 이미지 없음, 추후 추가 예정) |
| `cpyrhtDivCd` | `string` | 대표이미지 저작권 유형 - Type1: 제1유형(출처표시-권장), Type3: 제3유형(제1유형+변경금지) |
| `mapX` | `string` | GPS X좌표(WGS84 경도 좌표) 응답 |
| `mapY` | `string` | GPS Y좌표(WGS84 위도 좌표) 응답 |
| `mlevel` | `string` | Map Level 응답 |
| `mdfcnDt` | `string` | 콘텐츠 수정일 |
| `tel` | `string` | 전화번호 |
| `title` | `string` | 콘텐츠 제목 |
| `lDongRegnCd` | `string` | 법정동 시도코드 |

### 4. `searchKeyword` 키워드 검색 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/searchKeyword` |
| 설명 | 키워드로 검색을 하여 관광타입 별 또는 전체 목록을 조회하는 기능입니다. 파라미터에 따라 제목순, 수정일순(최신순), 등록일순, 인기순 정렬 검색을 제공합니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `searchKeyword_response` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultMsg` | `string` | API 호출 결과의 상태 메시지 |
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
| `langDivCd` | `string` | 언어 구분 코드(영문: ENG, 일문: JPN, 중간: CHS, 노어: RUS) |
| `baseAddr` | `string` | 주소(예, 서울 중구 다동)를 응답 |
| `detailAddr` | `string` | 상세주소 |
| `zipCd` | `string` | 우편번호 |
| `contentId` | `string` | 콘텐츠ID |
| `regDt` | `string` | 콘텐츠 최초 등록일 |
| `orgImage` | `string` | 원본 대표 이미지(현재 이미지 없음, 추후 추가 예정) |
| `thumbImage` | `string` | 썸네일 대표 이미지(현재 이미지 없음, 추후 추가 예정) |
| `cpyrhtDivCd` | `string` | 대표이미지 저작권 유형 - Type1: 제1유형(출처표시-권장), Type3: 제3유형(제1유형+변경금지) |
| `mapX` | `string` | GPS X좌표(WGS84 경도 좌표) 응답 |
| `mapY` | `string` | GPS Y좌표(WGS84 위도 좌표) 응답 |
| `mlevel` | `string` | Map Level 응답 |
| `mdfcnDt` | `string` | 콘텐츠 수정일 |
| `tel` | `string` | 전화번호 |
| `title` | `string` | 콘텐츠 제목 |
| `lDongRegnCd` | `string` | 법정동 시도코드 |
| `lDongSignguCd` | `string` | 법정동 시군구코드 |

### 5. `mdclTursmSyncList` 의료관광정보 동기화 목록 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/mdclTursmSyncList` |
| 설명 | 표출 유무에 따라 지역 및 시군구를 기반으로 관광정보 목록을 조회하는 기능입니다. 파라미터에 따라 제목순, 수정일순(최신순), 등록일순, 인기순 정렬 검색을 제공합니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `mdclTursmSyncList_response` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultCode` | `string` | API 호출 결과의 상태 코드 |
| `resultMsg` | `string` | API 호출 결과의 상태 메시지 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `totalCount` | `number` | 전체 결과 수 |
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 페이지 번호 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `lDongSignguCd` | `string` | 법정동 시군구코드 |
| `oldContentId` | `string` | 이전 콘텐츠 ID (DB 저장 동기화 시 이전 KEY값으로 조회 용도) |
| `showflag` | `string` | 콘텐츠 표출여부(1=표출, 0=비표출) |
| `langDivCd` | `string` | 언어 구분 코드(영문: ENG, 일문: JPN, 중간: CHS, 노어: RUS) |
| `baseAddr` | `string` | 주소(예, 서울 중구 다동)를 응답 |
| `detailAddr` | `string` | 상세주소 |
| `zipCd` | `string` | 우편번호 |
| `contentId` | `string` | 콘텐츠ID |
| `regDt` | `string` | 콘텐츠 최초 등록일 |
| `orgImage` | `string` | 원본 대표 이미지(현재 이미지 없음, 추후 추가 예정) |
| `thumbImage` | `string` | 썸네일 대표 이미지(현재 이미지 없음, 추후 추가 예정) |
| `cpyrhtDivCd` | `string` | 대표이미지 저작권 유형 - Type1: 제1유형(출처표시-권장), Type3: 제3유형(제1유형+변경금지) |
| `mapX` | `string` | GPS X좌표(WGS84 경도 좌표) 응답 |
| `mapY` | `string` | GPS Y좌표(WGS84 위도 좌표) 응답 |
| `mlevel` | `string` | Map Level 응답 |
| `mdfcnDt` | `string` | 콘텐츠 수정일 |
| `tel` | `string` | 전화번호 |
| `title` | `string` | 콘텐츠 제목 |
| `lDongRegnCd` | `string` | 법정동 시도코드 |

### 6. `detailCommon` 공통정보 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/detailCommon` |
| 설명 | 상세정보 1 - 공통정보(제목, 연락처, 주소, 좌표, 개요정보 등)를 조회하는 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `detailCommon_response` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultCode` | `string` | API 호출 결과의 상태 코드 |
| `resultMsg` | `string` | API 호출 결과의 상태 메시지 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `totalCount` | `number` | 전체 데이터의 총 수 |
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `overview` | `string` | 콘텐츠 개요 조회 |
| `homepage` | `string` | 홈페이지 주소 |
| `contentId` | `string` | 콘텐츠ID |
| `baseAddr` | `string` | 주소(예, 서울 중구 다동)를 응답 |
| `detailAddr` | `string` | 상세주소 |
| `zipCd` | `string` | 우편번호 |
| `regDt` | `string` | 콘텐츠 최초 등록일 |
| `mdfcnDt` | `string` | 콘텐츠 수정일 |
| `orgImage` | `string` | 원본 대표 이미지(현재 이미지 없음, 추후 추가 예정) |
| `thumbImage` | `string` | 썸네일 대표 이미지(현재 이미지 없음, 추후 추가 예정) |
| `cpyrhtDivCd` | `string` | 대표이미지 저작권 유형 - Type1:제1유형(출처표시-권장), Type3:제3유형(제1유형+변경금지) |
| `mapX` | `string` | GPS X좌표(WGS84 경도 좌표) 응답 |
| `mapY` | `string` | GPS Y좌표(WGS84 위도 좌표) 응답 |
| `mlevel` | `string` | Map Level 응답 |
| `tel` | `string` | 전화번호 |
| `telname` | `string` | 전화번호명 |
| `title` | `string` | 콘텐츠 제목 |
| `lDongRegnCd` | `string` | 법정동 시도코드 |
| `lDongSignguCd` | `string` | 법정동 시군구코드 |

### 7. `detailIntro` 소개정보 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/detailIntro` |
| 설명 | 상세정보 2 - 소개정보(휴무일, 개장 시간, 주차 시설 등)를 조회하는 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `detailIntro_response` |

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
| `usetime` | `string` | 이용시간 |
| `contentId` | `string` | 콘텐츠ID |
| `accomcount` | `string` | 수용 인원 |
| `expagerange` | `string` | 체험 가능 연령 |
| `expguide` | `string` | 체험 안내 |
| `heritage1` | `string` | 세계 문화유산 유무 |
| `infocenter` | `string` | 문의 및 안내 |
| `opendate` | `string` | 개장일 |
| `parking` | `string` | 주차 시설 |
| `restdate` | `string` | 쉬는 날 |
| `useseason` | `string` | 이용시기 |

### 8. `detailMdclTursm` 의료관광정보 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/detailMdclTursm` |
| 설명 | 상세정보 3 - 상세 의료관광 정보를 조회하는 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `detailMdclTursm_response` |

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
| `trtmntGdsKndInfo` | `string` | 취급 상품 종류 정보 |
| `contentId` | `string` | 콘텐츠ID |
| `mdclTursmDivInfo` | `string` | 의료관광 구분 정보 |
| `svcLangInfo` | `string` | 서비스 언어 정보 |
| `hmpgInfo` | `string` | 홈페이지 정보 |
| `prSnsInfo` | `string` | 홍보 SNS 정보 |
| `histrCn` | `string` | 연혁 내용 |
| `onlineRsvtPsblYn` | `string` | 온라인 예약 가능 여부 (Y: 가능, N: 불가능) |
| `gdsCnselCn` | `string` | 상품 상담 내용 |
| `insttDevInfo` | `string` | 기관 구분 정보 |
| `mainMdlcSubjInfo` | `string` | 주요 의료 과목 정보 |
| `specProcMdlcInfo` | `string` | 특화 시술 의료 정보 |
| `coorResidYn` | `string` | 코디네이터 상주 여부 (Y: 상주, N: 비상주) |
| `specFcltyInfo` | `string` | 특화 시설 정보 |
| `corprHsptlInfo` | `string` | 협력 병원 정보 |

### 9. `lclsSystmCode` lclsSystmCode 응답 schema

| 항목 | 값 |
|---|---|
| Endpoint | `/lclsSystmCode` |
| 설명 | 원본 상단 operation 목록에는 없지만 response schema가 포함되어 있어 구현 후보로 보존합니다. |
| 일일 트래픽 |  |
| 매칭한 schema block | `lclsSystmCode_response` |
| 원본 주의 | 상단 operation 목록에는 없고 response schema만 있습니다. |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultCode` | `string` | API 호출 결과의 상태 코드 |
| `resultMsg` | `string` | API 호출 결과의 상태 메시지 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |
| `totalCount` | `number` | 전체 데이터의 총 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `lclsSystm3Nm` | `string` | 분류체계 소분류명(lclsSystmListYn : Y 일때 표출) |
| `rnum` | `string` | 일련번호 |
| `code` | `string` | 코드: 1Depth, 2Depth, 3Depth 코드(lclsSystmListYn : N 일때 표출) |
| `name` | `string` | 코드: 1Depth, 2Depth, 3Depth 코드명(lclsSystmListYn : N 일때 표출) |
| `lclsSystm1Cd` | `string` | 분류체계 대분류코드(lclsSystmListYn : Y 일때 표출) |
| `lclsSystm1Nm` | `string` | 분류체계 대분류명(lclsSystmListYn : Y 일때 표출) |
| `lclsSystm2Cd` | `string` | 분류체계 중분류코드(lclsSystmListYn : Y 일때 표출) |
| `lclsSystm2Nm` | `string` | 분류체계 중분류명(lclsSystmListYn : Y 일때 표출) |
| `lclsSystm3Cd` | `string` | 분류체계 소분류코드(lclsSystmListYn : Y 일때 표출) |

### 10. `detailInfo` detailInfo 응답 schema

| 항목 | 값 |
|---|---|
| Endpoint | `/detailInfo` |
| 설명 | 원본 상단 operation 목록에는 없지만 response schema가 포함되어 있어 구현 후보로 보존합니다. |
| 일일 트래픽 |  |
| 매칭한 schema block | `detailInfo_response` |
| 원본 주의 | 상단 operation 목록에는 없고 response schema만 있습니다. |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultCode` | `string` | API 호출 결과의 상태 코드 |
| `resultMsg` | `string` | API 호출 결과의 상태 코드 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |
| `totalCount` | `number` | 전체 데이터의 총 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `contentId` | `string` | 콘텐츠ID |
| `contentTypeId` | `string` | 기본정보 : 관광타입(76: 관광지, 78: 문화시설, 85: 축제공연행사, 75: 레포츠, 80: 숙박, 79: 쇼핑, 82: 음식점, 77: 교통) ID |
| `fldgubun` | `string` | 일련번호 |
| `infoname` | `string` | 제목 |
| `infotext` | `string` | 내용 |
| `serialnum` | `string` | 반복 일련번호 |

### 11. `detailImage` detailImage 응답 schema

| 항목 | 값 |
|---|---|
| Endpoint | `/detailImage` |
| 설명 | 원본 상단 operation 목록에는 없지만 response schema가 포함되어 있어 구현 후보로 보존합니다. |
| 일일 트래픽 |  |
| 매칭한 schema block | `detailImage_response` |
| 원본 주의 | 상단 operation 목록에는 없고 response schema만 있습니다. |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultCode` | `string` | API 호출 결과의 상태 코드 |
| `resultMsg` | `string` | API 호출 결과의 상태 코드 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |
| `totalCount` | `number` | 전체 데이터의 총 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `contentId` | `string` | 콘텐츠ID |
| `imagename` | `string` | 이미지명 |
| `orgImage` | `string` | 원본 대표이미지(약 500*333 size) URL 응답 |
| `serialnum` | `string` | 이미지 일련번호 |
| `thumbImage` | `string` | 썸네일 대표이미지(약 150*100 size) URL 응답 |
| `cpyrhtDivCd` | `string` | 대표이미지 저작권 유형 - Type1: 제1유형(출처표시-권장), Type3: 제3유형(제1유형+변경금지) |
