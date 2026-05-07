# 99-03. 한국관광공사 웰니스관광정보 API 명세

작성 기준일: 2026-05-07

이 문서는 `API명세서` 폴더의 원본을 PARAVOCA 구현 기준으로 정규화한 내부 API 명세입니다. 원본의 endpoint 이름과 응답 필드명은 그대로 보존하고, 서비스마다 달랐던 출력 형식을 공통 Markdown 구조로 맞췄습니다.

## 원본과 범위

| 항목 | 값 |
|---|---|
| 원본 입력 파일 | `API명세서/한국관광공사_웰니스관광정보` |
| 공식 페이지 | https://www.data.go.kr/data/15144030/openapi.do |
| PARAVOCA source_family | `kto_wellness` |
| 데이터 성격 | `theme` |
| 활용 목적 | 힐링, 명상, 스파, 한방, 자연치유 등 웰니스 테마 상품 후보와 상세 근거를 보강합니다. |

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
| 4 | `searchKeyword` | `/searchKeyword` | 키워드검색 조회 | 1000 | 상단 상세기능 |
| 5 | `wellnessTursmSyncList` | `/wellnessTursmSyncList` | 웰니스 관광정보 동기화 목록 조회 | 1000 | 상단 상세기능 |
| 6 | `detailCommon` | `/detailCommon` | 공통정보 조회 | 1000 | 상단 상세기능 |
| 7 | `detailIntro` | `/detailIntro` | 소개정보 조회 | 1000 | 상단 상세기능 |
| 8 | `detailInfo` | `/detailInfo` | 반복정보 조회 | 1000 | 상단 상세기능 |
| 9 | `detailImage` | `/detailImage` | 이미지정보 조회 | 1000 | 상단 상세기능 |

## 구현 주의

- 건강 개선, 치료, 효능 보장 표현은 생성하지 않고, 웰니스 속성은 상품 기획 보조 근거로만 사용합니다.

## Operation 상세

### 1. `ldongCode` 법정동 코드 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/ldongCode` |
| 설명 | 법정동 코드 목록을 지역, 시군구, 읍면동 코드 목록을 조회하는 기능입니다. 지역기반 관광정보 및 키워드 검색 등을 통해 지역 별로 목록을 보여줄 경우, 법정동 코드를 이용하여 법정동명을 매칭하기 위한 기능입니다. |
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
| `rnum` | `string` | 일련번호 |
| `name` | `string` | 법정동 : 시도명, 시군구명 (lDongListYn : N일때 표출) |
| `code` | `string` | 법정동 : 시도코드, 시군구코드 (lDongListYn : N일때 표출) |
| `lDongRegnCd` | `string` | 법정동 시도코드 (lDongListYn : Y일때 표출) |
| `lDongRegnNm` | `string` | 법정동 시도명 (lDongListYn : Y일때 표출) |
| `lDongSignguCd` | `string` | 법정동 시군구코드 (lDongListYn : Y일때 표출) |
| `lDongSignguNm` | `string` | 법정동 시군구명 (lDongListYn : Y일때 표출) |

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
| `wellnessThemaCd` | `string` | 웰니스 테마 코드 (EX050100: 온천/사우나/스파, EX050200: 찜질방, EX050300: 한방 체험, EX050400: 힐링 명상, EX050500: 뷰티 스파, EX050600: 기타 웰니스, EX050700: 자연 치유) |
| `langDivCd` | `string` | 언어 구분 코드(KOR: 한국어, ENG: 영어, JPN: 일어, CHS: 중국어(간체), CHT: 중국어(번체), GER: 독일어, FRE: 프랑스어, SPN: 스페인어, RUS: 러시아어) |
| `baseAddr` | `string` | 주소(예, 서울 중구 다동)를 응답 |
| `detailAddr` | `string` | 상세주소 |
| `zipCd` | `string` | 우편번호 |
| `contentId` | `string` | 콘텐츠ID |
| `contentTypeId` | `string` | 관광타입 ID(관광타입 = 관광지, 한국어: 12, 다국어: 76) |
| `regDt` | `string` | 콘텐츠 최초 등록일 |
| `orgImage` | `string` | 원본 대표이미지(약 500*333 size) URL 응답 |
| `thumbImage` | `string` | 썸네일 대표이미지(약 150*100 size) URL 응답 |
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
| `wellnessThemaCd` | `string` | 웰니스 테마 코드 (EX050100: 온천/사우나/스파, EX050200: 찜질방, EX050300: 한방 체험, EX050400: 힐링 명상, EX050500: 뷰티 스파, EX050600: 기타 웰니스, EX050700: 자연 치유) |
| `langDivCd` | `string` | 언어 구분 코드 (KOR: 한국어, ENG: 영어, JPN: 일어, CHS: 중국어(간체), CHT: 중국어(번체), GER: 독일어, FRE: 프랑스어, SPN: 스페인어, RUS: 러시아어) |
| `baseAddr` | `string` | 주소(예, 서울 중구 다동)를 응답 |
| `detailAddr` | `string` | 상세주소 |
| `zipCd` | `string` | 우편번호 |
| `contentId` | `string` | 콘텐츠ID |
| `contentTypeId` | `string` | 관광타입 ID(관광타입 = 관광지, 한국어: 12, 다국어: 76) |
| `regDt` | `string` | 콘텐츠 최초 등록일 |
| `orgImage` | `string` | 원본 대표이미지(약 500*333 size) URL 응답 |
| `thumbImage` | `string` | 썸네일 대표이미지(약 150*100 size) URL 응답 |
| `cpyrhtDivCd` | `string` | 대표이미지 저작권 유형 - Type1: 제1유형(출처표시-권장), Type3: 제3유형(제1유형+변경금지) |
| `mapX` | `string` | GPS X좌표(WGS84 경도 좌표) 응답 |
| `mapY` | `string` | GPS Y좌표(WGS84 위도 좌표) 응답 |
| `mlevel` | `string` | Map Level 응답 |
| `dist` | `string` | 거리(단위: m) |
| `mdfcnDt` | `string` | 콘텐츠 수정일 |
| `tel` | `string` | 전화번호 |
| `title` | `string` | 콘텐츠 제목 |
| `lDongRegnCd` | `string` | 법정동 시도코드 |
| `lDongSignguCd` | `string` | 법정동 시군구코드 |

### 4. `searchKeyword` 키워드검색 조회

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
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |
| `totalCount` | `number` | 전체 데이터의 총 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `wellnessThemaCd` | `string` | 웰니스 테마 코드 (EX050100: 온천/사우나/스파, EX050200: 찜질방, EX050300: 한방 체험, EX050400: 힐링 명상, EX050500: 뷰티 스파, EX050600: 기타 웰니스, EX050700: 자연 치유) |
| `langDivCd` | `string` | 언어 구분 코드 (KOR: 한국어, ENG: 영어, JPN: 일어, CHS: 중국어(간체), CHT: 중국어(번체), GER: 독일어, FRE: 프랑스어, SPN: 스페인어, RUS: 러시아어) |
| `baseAddr` | `string` | 주소(예, 서울 중구 다동)를 응답 |
| `detailAddr` | `string` | 상세주소 |
| `zipCd` | `string` | 우편번호 |
| `contentId` | `string` | 콘텐츠ID |
| `contentTypeId` | `string` | 관광타입 ID(관광타입 = 관광지, 한국어: 12, 다국어: 76) |
| `regDt` | `string` | 콘텐츠 최초 등록일 |
| `orgImage` | `string` | 원본 대표이미지(약 500*333 size) URL 응답 |
| `thumbImage` | `string` | 썸네일 대표이미지(약 150*100 size) URL 응답 |
| `cpyrhtDivCd` | `string` | 대표이미지 저작권 유형 - Type1: 제1유형(출처표시-권장), Type3: 제3유형(제1유형+변경금지) |
| `mapX` | `string` | GPS X좌표(WGS84 경도 좌표) 응답 |
| `mapY` | `string` | GPS Y좌표(WGS84 위도 좌표) 응답 |
| `mlevel` | `string` | Map Level 응답 |
| `mdfcnDt` | `string` | 콘텐츠 수정일 |
| `tel` | `string` | 전화번호 |
| `title` | `string` | 콘텐츠 제목 |
| `lDongRegnCd` | `string` | 법정동 시도코드 |
| `lDongSignguCd` | `string` | 법정동 시군구코드 |

### 5. `wellnessTursmSyncList` 웰니스 관광정보 동기화 목록 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/wellnessTursmSyncList` |
| 설명 | 표출 유무에 따라 지역 및 시군구를 기반으로 웰니스 관광정보 목록을 조회하는 기능입니다. 파라미터에 따라 제목순, 수정일순(최신순), 등록일순, 인기순 정렬 검색을 제공합니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `wellnessTursmSyncList_response` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultMsg` | `string` | API 호출 결과의 상태 코드 |
| `resultCode` | `string` | API 호출 결과의 상태 메시지 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `totalCount` | `number` | 전체 결과 수 |
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 페이지 번호 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `oldContentId` | `string` | 이전 콘텐츠 ID (DB 저장 동기화 시 이전 KEY값으로 조회 용도) |
| `showflag` | `string` | 콘텐츠 표출여부(1=표출, 0=비표출) |
| `langDivCd` | `string` | 언어 구분 코드 (KOR: 한국어, ENG: 영어, JPN: 일어, CHS: 중국어(간체), CHT: 중국어(번체), GER: 독일어, FRE: 프랑스어, SPN: 스페인어, RUS: 러시아어) |
| `baseAddr` | `string` | 주소(예, 서울 중구 다동)를 응답 |
| `detailAddr` | `string` | 상세주소 |
| `zipCd` | `string` | 우편번호 |
| `contentId` | `string` | 콘텐츠ID |
| `contentTypeId` | `string` | 관광타입 ID(관광타입 = 관광지, 한국어: 12, 다국어: 76) |
| `regDt` | `string` | 콘텐츠 최초 등록일 |
| `orgImage` | `string` | 원본 대표이미지(약 500*333 size) URL 응답 |
| `thumbImage` | `string` | 썸네일 대표이미지(약 150*100 size) URL 응답 |
| `cpyrhtDivCd` | `string` | 대표이미지 저작권 유형 - Type1: 제1유형(출처표시-권장), Type3: 제3유형(제1유형+변경금지) |
| `mapX` | `string` | GPS X좌표(WGS84 경도 좌표) 응답 |
| `mapY` | `string` | GPS Y좌표(WGS84 위도 좌표) 응답 |
| `mlevel` | `string` | Map Level 응답 |
| `mdfcnDt` | `string` | 콘텐츠 수정일 |
| `tel` | `string` | 전화번호 |
| `title` | `string` | 콘텐츠 제목 |
| `lDongRegnCd` | `string` | 법정동 시도코드 |
| `lDongSignguCd` | `string` | 법정동 시군구코드 |
| `wellnessThemaCd` | `string` | 웰니스 테마 코드 (EX050100: 온천/사우나/스파, EX050200: 찜질방, EX050300: 한방 체험, EX050400: 힐링 명상, EX050500: 뷰티 스파, EX050600: 기타 웰니스, EX050700: 자연 치유) |

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
| `homepage` | `string` | 홈페이지 주소 |
| `contentId` | `string` | 콘텐츠ID |
| `contentTypeId` | `string` | 관광타입 ID(관광타입 = 관광지, 한국어: 12, 다국어: 76) |
| `baseAddr` | `string` | 주소(예, 서울 중구 다동)를 응답 |
| `detailAddr` | `string` | 상세주소 |
| `zipCd` | `string` | 우편번호 |
| `regDt` | `string` | 콘텐츠 최초 등록일 |
| `mdfcnDt` | `string` | 콘텐츠 수정일 |
| `orgImage` | `string` | 원본 대표이미지(약 500*333 size) URL 응답 |
| `thumbImage` | `string` | 썸네일 대표이미지(약 150*100 size) URL 응답 |
| `cpyrhtDivCd` | `string` | 대표이미지 저작권 유형 - Type1: 제1유형(출처표시-권장), Type3: 제3유형(제1유형+변경금지) |
| `mapX` | `string` | GPS X좌표(WGS84 경도 좌표) 응답 |
| `mapY` | `string` | GPS Y좌표(WGS84 위도 좌표) 응답 |
| `mlevel` | `string` | Map Level 응답 |
| `tel` | `string` | 전화번호 |
| `telname` | `string` | 전화번호명 |
| `title` | `string` | 콘텐츠 제목 |
| `lDongRegnCd` | `string` | 법정동 시도 코드 |
| `lDongSignguCd` | `string` | 법정동 시군구 코드 |
| `wellnessThemaCd` | `string` | 웰니스 테마 코드 (EX050100: 온천/사우나/스파, EX050200: 찜질방, EX050300: 한방 체험, EX050400: 힐링 명상, EX050500: 뷰티 스파, EX050600: 기타 웰니스, EX050700: 자연 치유) |
| `overview` | `string` | 콘텐츠 개요 조회 |

### 7. `detailIntro` 소개정보 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/detailIntro` |
| 설명 | 상세정보 2 - 콘텐츠 별 소개정보(휴무일, 개장 시간, 주차 시설 등)를 조회하는 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `detailIntro_response` |

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
| `agelimit` | `string` | 축제공연행사(15, 85): 관람 가능 연령 |
| `parkingfeeleports` | `string` | 레포츠(28, 75): 주차 요금 |
| `contentId` | `string` | 기본정보 : 콘텐츠ID |
| `contentTypeId` | `string` | 기본정보 : 한국어 관광타입(12: 관광지, 14: 문화시설, 15: 축제공연행사, 28: 레포츠, 32: 숙박, 38: 쇼핑, 39: 음식점, 25: 여행코스) ID,다국어 관광타입(76: 관광지, 78: 문화시설, 85: 축제공연행사, 75: 레포츠, 80: 숙박, 79: 쇼핑, 82: 음식점, 77: 교통) ID |
| `accomcount` | `string` | 관광지(12, 76): 수용 인원 |
| `chkcreditcard` | `string` | 관광지(12, 76): 신용카드 가능 여부 |
| `expagerange` | `string` | 관광지(12, 76): 체험가능 연령 |
| `expguide` | `string` | 관광지(12, 76): 체험 안내 |
| `heritage1` | `string` | 관광지(12, 76): 세계 문화유산 유무 |
| `heritage2` | `string` | 관광지(12, 76): 세계 자연유산 유무 |
| `heritage3` | `string` | 관광지(12, 76): 세계 기록유산 유무 |
| `infocenter` | `string` | 관광지(12, 76): 문의 및 안내 |
| `opendate` | `string` | 관광지(12, 76): 개장일 |
| `parking` | `string` | 관광지(12, 76): 주차 시설 |
| `restdate` | `string` | 관광지(12, 76): 쉬는 날 |
| `useseason` | `string` | 관광지(12, 76): 이용 시기 |
| `usetime` | `string` | 관광지(12, 76): 이용 시간 |
| `accomcountculture` | `string` | 문화시설(14, 78): 수용 인원 |
| `chkcreditcardculture` | `string` | 문화시설(14, 78): 신용카드 가능 여부 |
| `discountinfo` | `string` | 문화시설(14, 78): 할인 정보 |
| `infocenterculture` | `string` | 문화시설(14, 78): 문의 및 안내 |
| `parkingculture` | `string` | 문화시설(14, 78): 주차 시설 |
| `parkingfee` | `string` | 문화시설(14, 78): 주차 요금 |
| `restdateculture` | `string` | 문화시설(14, 78): 쉬는 날 |
| `usefee` | `string` | 문화시설(14, 78): 이용 요금 |
| `usetimeculture` | `string` | 문화시설(14, 78): 이용 시간 |
| `scale` | `string` | 문화시설(14, 78): 규모 |
| `spendtime` | `string` | 문화시설(14, 78): 관람 소요시간 |
| `bookingplace` | `string` | 축제공연행사(15, 85): 예매처 |
| `discountinfofestival` | `string` | 축제공연행사(15, 85): 할인 정보 |
| `eventenddate` | `string` | 축제공연행사(15, 85): 행사 종료일 |
| `eventhomepage` | `string` | 축제공연행사(15, 85): 행사 홈페이지 |
| `eventplace` | `string` | 축제공연행사(15, 85): 행사 장소 |
| `eventstartdate` | `string` | 축제공연행사(15, 85): 행사 시작일 |
| `festivalgrade` | `string` | 축제공연행사(15, 85): 축제 등급 |
| `placeinfo` | `string` | 축제공연행사(15, 85): 행사장 위치 안내 |
| `playtime` | `string` | 축제공연행사(15, 85): 공연 시간 |
| `program` | `string` | 축제공연행사(15, 85): 행사 프로그램 |
| `spendtimefestival` | `string` | 축제공연행사(15, 85): 관람 소요시간 |
| `sponsor1` | `string` | 축제공연행사(15, 85): 주최자 정보 |
| `sponsor1tel` | `string` | 축제공연행사(15, 85): 주최자 연락처 |
| `sponsor2` | `string` | 축제공연행사(15, 85): 주관사 정보 |
| `sponsor2tel` | `string` | 축제공연행사(15, 85): 주관사 연락처 |
| `subevent` | `string` | 축제공연행사(15, 85): 부대 행사 |
| `usetimefestival` | `string` | 축제공연행사(15, 85): 이용 요금 |
| `accomcountleports` | `string` | 레포츠(28, 75): 수용 인원 |
| `chkcreditcardleports` | `string` | 레포츠(28, 75): 신용카드 가능 여부 |
| `expagerangeleports` | `string` | 레포츠(28, 75): 체험 가능 연령 |
| `infocenterleports` | `string` | 레포츠(28, 75): 문의 및 안내 |
| `openperiod` | `string` | 레포츠(28, 75): 개장 기간 |
| `operationtimetraffic` | `string` | 교통(77): 운영 시간 |
| `mainroute` | `string` | 교통(77): 주요 노선 |
| `chkcreditcardtraffic` | `string` | 교통(77): 신용카드 가능 여부 |
| `shipinfo` | `string` | 교통(77): 여객선 정보 |
| `conven` | `string` | 교통(77): 편의 시설 |
| `parkingtraffic` | `string` | 교통(77): 주자 시설 |
| `disablefacility` | `string` | 교통(77): 장애인 편의 시설 |
| `restroomtraffic` | `string` | 교통(77): 화장실 |
| `reservationurl` | `string` | 숙박(32, 80): 예약 안내 홈페이지 |
| `roomtype` | `string` | 숙박(32, 80): 객실 유형 |
| `scalelodging` | `string` | 숙박(32, 80): 규모 |
| `subfacility` | `string` | 숙박(32, 80): 부대시설 (기타) |
| `barbecue` | `string` | 숙박(32, 80): 바베큐장 여부 |
| `beauty` | `string` | 숙박(32, 80): 뷰티 시설 정보 |
| `beverage` | `string` | 숙박(32, 80): 식음료장 여부 |
| `bicycle` | `string` | 숙박(32, 80): 자전거 대여 여부 |
| `campfire` | `string` | 숙박(32, 80): 캠프파이어 여부 |
| `fitness` | `string` | 숙박(32, 80): 휘트니스 센터 여부 |
| `karaoke` | `string` | 숙박(32, 80): 노래방 여부 |
| `publicbath` | `string` | 숙박(32, 80): 공용 샤워실 여부 |
| `publicpc` | `string` | 숙박(32, 80): 공용 PC실 여부 |
| `sauna` | `string` | 숙박(32, 80): 사우나실 여부 |
| `seminar` | `string` | 숙박(32, 80): 세미나실 여부 |
| `sports` | `string` | 숙박(32, 80): 스포츠 시설 여부 |
| `refundregulation` | `string` | 숙박(32, 80): 환불규정 |
| `chkcreditcardshopping` | `string` | 쇼핑(38, 79): 신용카드 가능 여부 |
| `culturecenter` | `string` | 쇼핑(38, 79): 문화센터 바로가기 |
| `fairday` | `string` | 쇼핑(38, 79): 장 서는 날 |
| `infocentershopping` | `string` | 쇼핑(38, 79): 문의 및 안내 |
| `opendateshopping` | `string` | 쇼핑(38, 79): 개장일 |
| `opentime` | `string` | 쇼핑(38, 79): 영업 시간 |
| `parkingshopping` | `string` | 쇼핑(38, 79): 주차 시설 |
| `restdateshopping` | `string` | 쇼핑(38, 79): 쉬는 날 |
| `restroom` | `string` | 쇼핑(38, 79): 화장실 설명 |
| `saleitem` | `string` | 쇼핑(38, 79): 판매 품목 |
| `saleitemcost` | `string` | 쇼핑(38, 79): 판매 품목별 가격 |
| `scaleshopping` | `string` | 쇼핑(38, 79): 규모 |
| `shopguide` | `string` | 쇼핑(38, 79): 매장 안내 |
| `chkcreditcardfood` | `string` | 음식점(39, 82): 신용카드 가능 여부 |
| `discountinfofood` | `string` | 음식점(39, 82): 할인 정보 |
| `firstmenu` | `string` | 음식점(39, 82): 대표 메뉴 |
| `infocenterfood` | `string` | 음식점(39, 82): 문의 및 안내 |
| `kidsfacility` | `string` | 음식점(39, 82): 어린이 놀이방 |
| `opendatefood` | `string` | 음식점(39, 82): 개업일 |
| `opentimefood` | `string` | 음식점(39, 82): 영업 시간 |
| `packing` | `string` | 음식점(39, 82): 포장 가능 여부 |
| `parkingfood` | `string` | 음식점(39, 82): 주차 시설 |
| `reservationfood` | `string` | 음식점(39, 82): 예약 안내 |
| `restdatefood` | `string` | 음식점(39, 82): 쉬는 날 |
| `scalefood` | `string` | 음식점(39, 82): 규모 |
| `seat` | `string` | 음식점(39, 82): 좌석 수 |
| `smoking` | `string` | 음식점(39, 82): 금연/흡연 여부 |
| `treatmenu` | `string` | 음식점(39, 82): 취급 메뉴 |
| `lcnsno` | `string` | 음식점(39, 82): 인허가번호 |
| `distance` | `string` | 여행코스(25): 코스 총 거리 |
| `infocentertourcourse` | `string` | 여행코스(25): 문의 및 안내 |
| `schedule` | `string` | 여행코스(25): 코스 일정 |
| `taketime` | `string` | 여행코스(25): 코스 총 소요시간 |
| `theme` | `string` | 여행코스(25): 코스 테마 |
| `infocentertraffic` | `string` | 교통(77): 문의 및 안내 |
| `foreignerinfocenter` | `string` | 교통(77): 외국인 문의 및 안내 |
| `parkingleports` | `string` | 레포츠(28, 75): 주차 시설 |
| `reservation` | `string` | 레포츠(28, 75): 예약 안내 |
| `restdateleports` | `string` | 레포츠(28, 75): 쉬는 날 |
| `scaleleports` | `string` | 레포츠(28, 75): 규모 |
| `usefeeleports` | `string` | 레포츠(28, 75): 입장료 |
| `usetimeleports` | `string` | 레포츠(28, 75): 이용 시간 |
| `accomcountlodging` | `string` | 숙박(32, 80): 수용 가능 인원 |
| `checkintime` | `string` | 숙박(32, 80): 입실 시간 |
| `checkouttime` | `string` | 숙박(32, 80): 퇴실 시간 |
| `chkcooking` | `string` | 숙박(32, 80): 객실 내 취사 여부 |
| `foodplace` | `string` | 숙박(32, 80): 식음료장 |
| `infocenterlodging` | `string` | 숙박(32, 80): 문의 및 안내 |
| `parkinglodging` | `string` | 숙박(32, 80): 주차 시설 |
| `pickup` | `string` | 숙박(32, 80): 픽업 서비스 |
| `roomcount` | `string` | 숙박(32, 80): 객실 수 |
| `reservationlodging` | `string` | 숙박(32, 80): 예약 안내 |

### 8. `detailInfo` 반복정보 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/detailInfo` |
| 설명 | 상세정보 3 - 콘텐츠 별 항목 별 반복정보를 조회하는 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `detailInfo_response` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultMsg` | `string` | API 호출 결과의 상태 코드 |
| `resultCode` | `string` | API 호출 결과의 상태 메시지 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `totalCount` | `number` | 전체 데이터의 총 수 |
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `roomcable` | `string` | 숙박(32): 케이블 설치 |
| `roomaircondition` | `string` | 숙박(32): 에어컨 |
| `roompc` | `string` | 숙박(32): PC |
| `roomimg5alt` | `string` | 숙박(32): 객실 사진5 설명 |
| `contentId` | `string` | 기본정보 : 콘텐츠ID |
| `contentTypeId` | `string` | 기본정보 : 한국어 관광타입(12: 관광지, 14: 문화시설, 15: 축제공연행사, 28: 레포츠, 32: 숙박, 38: 쇼핑, 39: 음식점, 25: 여행코스) ID,다국어 관광타입(76: 관광지, 78: 문화시설, 85: 축제공연행사, 75: 레포츠, 80: 숙박, 79: 쇼핑, 82: 음식점, 77: 교통) ID |
| `fldgubun` | `string` | 일련번호 |
| `infoname` | `string` | 제목(타입 별 세부 항목은 매뉴얼 문서 참고) |
| `infotext` | `string` | 내용 |
| `serialnum` | `string` | 반복 일련번호 |
| `subcontentid` | `string` | 여행코스(25): 하위 콘텐츠ID |
| `subdetailalt` | `string` | 여행코스(25): 코스 이미지 설명 |
| `subdetailimg` | `string` | 여행코스(25): 코스 이미지 |
| `subdetailoverview` | `string` | 여행코스(25): 코스 개요 |
| `subname` | `string` | 여행코스(25): 코스명 |
| `subnum` | `string` | 여행코스(25): 반복 일련번호 |
| `roomcode` | `string` | 숙박(32): 객실 코드 |
| `roomtitle` | `string` | 숙박(32): 객실 명칭 |
| `roomcount` | `string` | 숙박(32): 객실 수 |
| `roombasecount` | `string` | 숙박(32): 기준 인원 |
| `roommaxcount` | `string` | 숙박(32): 최대 인원 |
| `roomoffseasonminfee1` | `string` | 숙박(32): 비수기 주중 최소 |
| `roomoffseasonminfee2` | `string` | 숙박(32): 비수기 주말 최소 |
| `roompeakseasonminfee1` | `string` | 숙박(32): 성수기 주중 최소 |
| `roompeakseasonminfee2` | `string` | 숙박(32): 성수기 주말 최소 |
| `roomintro` | `string` | 숙박(32): 객실 소개 |
| `roombathfacility` | `string` | 숙박(32): 목욕 시설 |
| `roombath` | `string` | 숙박(32): 욕조 |
| `roomhometheater` | `string` | 숙박(32): 홈시어터 |
| `roomtv` | `string` | 숙박(32): TV |
| `roominternet` | `string` | 숙박(32): 인터넷 |
| `roomrefrigerator` | `string` | 숙박(32): 냉장고 |
| `roomtoiletries` | `string` | 숙박(32): 세면도구 |
| `roomsofa` | `string` | 숙박(32): 소파 |
| `roomcook` | `string` | 숙박(32): 취사용품 |
| `roomTable` | `string` | 숙박(32): 테이블 |
| `roomhairdryer` | `string` | 숙박(32): 드라이기 |
| `roomsize2` | `string` | 숙박(32): 객실 크기(평방미터) |
| `roomimg1` | `string` | 숙박(32): 객실 사진1 |
| `roomimg1alt` | `string` | 숙박(32): 객실 사진1 설명 |
| `roomimg2` | `string` | 숙박(32): 객실 사진2 |
| `roomimg2alt` | `string` | 숙박(32): 객실 사진2 설명 |
| `roomimg3` | `string` | 숙박(32): 객실 사진3 |
| `roomimg3alt` | `string` | 숙박(32): 객실 사진3 설명 |
| `roomimg4` | `string` | 숙박(32): 객실 사진4 |
| `roomimg4alt` | `string` | 숙박(32): 객실 사진4 설명 |
| `roomimg5` | `string` | 숙박(32): 객실 사진5 |

### 9. `detailImage` 이미지정보 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/detailImage` |
| 설명 | 상세정보 4 - 각 콘텐츠에 해당하는 이미지 URL 목록을 조회하는 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `detailImage_response` |

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
| `thumbImage` | `string` | 썸네일 대표이미지(약 150*100 size) URL 응답 |
| `cpyrhtDivCd` | `string` | 대표이미지 저작권 유형 - Type1: 제1유형(출처표시-권장), Type3: 제3유형(제1유형+변경금지) |
| `contentId` | `string` | 콘텐츠ID |
| `imgname` | `string` | 이미지명 |
| `orgImage` | `string` | 원본 대표이미지(약 500*333 size) URL 응답 |
| `serialnum` | `string` | 이미지 일련번호 |
