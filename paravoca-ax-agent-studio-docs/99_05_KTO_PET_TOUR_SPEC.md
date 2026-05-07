# 99-05. 한국관광공사 반려동물 동반여행 서비스 API 명세

작성 기준일: 2026-05-07

이 문서는 `API명세서` 폴더의 원본을 PARAVOCA 구현 기준으로 정규화한 내부 API 명세입니다. 원본의 endpoint 이름과 응답 필드명은 그대로 보존하고, 서비스마다 달랐던 출력 형식을 공통 Markdown 구조로 맞췄습니다.

## 원본과 범위

| 항목 | 값 |
|---|---|
| 원본 입력 파일 | `API명세서/한국관광공사_반려동물_동반여행_서비스` |
| 공식 페이지 | https://www.data.go.kr/data/15135102/openapi.do |
| PARAVOCA source_family | `kto_pet` |
| 데이터 성격 | `theme` |
| 활용 목적 | 반려동물 동반 가능 장소, 동반 조건, 필요사항, 시설 정보를 상품 조건과 QA 근거로 사용합니다. |

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
| 1 | `detailImage2` | `/detailImage2` | 이미지정보조회 | 1000 | 상단 상세기능 |
| 2 | `categoryCode2` | `/categoryCode2` | 서비스분류코드조회 | 1000 | 상단 상세기능 |
| 3 | `areaBasedList2` | `/areaBasedList2` | 지역기반 관광정보조회 | 1000 | 상단 상세기능 |
| 4 | `searchKeyword2` | `/searchKeyword2` | 키워드 조회 | 1000 | 상단 상세기능 |
| 5 | `detailCommon2` | `/detailCommon2` | 공통 정보 조회 | 1000 | 상단 상세기능 |
| 6 | `detailIntro2` | `/detailIntro2` | 소개 정보 조회 | 1000 | 상단 상세기능 |
| 7 | `detailInfo2` | `/detailInfo2` | 반복 정보 조회 | 1000 | 상단 상세기능 |
| 8 | `detailPetTour2` | `/detailPetTour2` | 반려동물 동반여행 조회 | 1000 | 상단 상세기능 |
| 9 | `petTourSyncList2` | `/petTourSyncList2` | 반려동물 동반여행 정보 동기화 목록 조회 | 1000 | 상단 상세기능 |
| 10 | `areaCode2` | `/areaCode2` | 지역코드 조회 | 1000 | 상단 상세기능 |
| 11 | `locationBasedList2` | `/locationBasedList2` | 위치기반 관광정보 조회 | 1000 | 상단 상세기능 |
| 12 | `ldongCode2` | `/ldongCode2` | 법정동 코드 조회 | 1000 | 상단 상세기능 |
| 13 | `lclsSystmCode2` | `/lclsSystmCode2` | 분류체계 코드 조회 | 1000 | 상단 상세기능 |

## 구현 주의

- 동반 가능 여부는 시설 정책 변경 가능성이 있으므로 조건부로 표시하고 게시 전 재확인 대상으로 남깁니다.

## Operation 상세

### 1. `detailImage2` 이미지정보조회

| 항목 | 값 |
|---|---|
| Endpoint | `/detailImage2` |
| 설명 | 반려동물 동반여행지의 각 관광타입(관광지, 숙박 등)에 해당하는 이미지URL 목록을 조회하는 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `detailImage2_response` |

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
| `cpyrhtDivCd` | `string` | 저작권 유형 - Type1:제1유형(출처표시-권장), Type3:제3유형(제1유형+변경금지) |
| `contentid` | `string` | 기본정보 : 콘텐츠ID |
| `imgname` | `string` | 이미지명 |
| `originimgurl` | `string` | 원본 이미지 |
| `serialnum` | `string` | 이미지 일련번호 |
| `smallimageurl` | `string` | 썸네일 이미지 |

### 2. `categoryCode2` 서비스분류코드조회

| 항목 | 값 |
|---|---|
| Endpoint | `/categoryCode2` |
| 설명 | 반려동물 동반여행지의 각 관광타입(관광지, 숙박 등)에 해당하는 서비스 분류코드를 대,중,소분류로 조회하는 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `categoryCode2_response` |

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
| `name` | `string` | 코드:대,중,소분류 코드명 |
| `rnum` | `string` | 일련번호 |
| `code` | `string` | 코드:대,중,소분류 코드 |

### 3. `areaBasedList2` 지역기반 관광정보조회

| 항목 | 값 |
|---|---|
| Endpoint | `/areaBasedList2` |
| 설명 | 반려동물 동반여행지의 지역 및 시군구를 기반으로 관광정보 목록을 조회하는 기능입니다. 파라미터에 따라 제목순, 수정일순(최신순), 등록일순 정렬검색을 제공합니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `areaBasedList2_response` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultMsg` | `string` | API 호출 결과의 상태 코드 |
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
| `cpyrhtDivCd` | `string` | 대표이미지 저작권 유형 - Type1:제1유형(출처표시-권장), Type3:제3유형(제1유형+변경금지) |
| `contentid` | `string` | 콘텐츠ID |
| `contenttypeid` | `string` | 관광타입(12:관광지, 14:문화시설, 15:축제공연행사, 28:레포츠, 32:숙박, 38:쇼핑, 39:음식점) ID |
| `title` | `string` | 제목 |
| `createdtime` | `string` | 콘텐츠 등록일 |
| `modifiedtime` | `string` | 콘텐츠 수정일 |
| `tel` | `string` | 전화번호 |
| `cat1` | `string` | 대분류 코드 |
| `cat2` | `string` | 중분류 코드 |
| `cat3` | `string` | 소분류 코드 |
| `zipcode` | `string` | 우편번호 |
| `addr1` | `string` | 주소 |
| `addr2` | `string` | 상세주소 |
| `areacode` | `string` | 지역코드 |
| `sigungucode` | `string` | 시군구코드 |
| `mapx` | `string` | GPS X좌표(WGS84 경도 좌표) |
| `mapy` | `string` | GPS Y좌표(WGS84 위도 좌표) |
| `mlevel` | `string` | Map Level 응답 |
| `firstimage` | `string` | 원본 대표이미지 URL |
| `firstimage2` | `string` | 썸네일 대표이미지 URL |
| `lDongRegnCd` | `string` | 법정동 시도 코드 |
| `lDongSignguCd` | `string` | 법정동 시군구 코드 |
| `lclsSystm1` | `string` | 분류체계 1Depth |
| `lclsSystm2` | `string` | 분류체계 2Depth |
| `lclsSystm3` | `string` | 분류체계 3Depth |

### 4. `searchKeyword2` 키워드 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/searchKeyword2` |
| 설명 | 반려동물 동반여행지를 키워드로 검색하여 관광타입별 또는 전체 목록을 조회하는 기능입니다. 파라미터에 따라 제목순, 수정일순(최신순), 등록일순 정렬 검색을 제공합니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `searchKeyword2_response` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultCode` | `string` | API 호출 결과의 상태 코드 |
| `resultMsg` | `string` | API 호출 결과의 상태 코드 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `totalCount` | `number` | 전체 데이터의 총 수 |
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `firstimage2` | `string` | 썸네일 대표이미지 URL |
| `cpyrhtDivCd` | `string` | 대표이미지 저작권 유형 - Type1:제1유형(출처표시-권장), Type3:제3유형(제1유형+변경금지) |
| `contentid` | `string` | 콘텐츠ID |
| `contenttypeid` | `string` | 관광타입(12:관광지, 14:문화시설, 15:축제공연행사, 28:레포츠, 32:숙박, 38:쇼핑, 39:음식점) ID |
| `title` | `string` | 제목 |
| `createdtime` | `string` | 콘텐츠 등록일 |
| `modifiedtime` | `string` | 콘텐츠 수정일 |
| `tel` | `string` | 전화번호 |
| `cat1` | `string` | 대분류 코드 |
| `cat2` | `string` | 중분류 코드 |
| `cat3` | `string` | 소분류 코드 |
| `addr1` | `string` | 주소 |
| `addr2` | `string` | 상세주소 |
| `areacode` | `string` | 지역코드 |
| `sigungucode` | `string` | 시군구코드 |
| `mapx` | `string` | GPS X좌표(WGS84 경도 좌표) |
| `mapy` | `string` | GPS Y좌표(WGS84 위도 좌표) |
| `mlevel` | `string` | Map Level 응답 |
| `firstimage` | `string` | 원본 대표이미지 URL |
| `lDongRegnCd` | `string` | 법정동 시도 코드 |
| `lDongSignguCd` | `string` | 법정동 시군구 코드 |
| `lclsSystm1` | `string` | 분류체계 1Depth |
| `lclsSystm2` | `string` | 분류체계 2Depth |
| `lclsSystm3` | `string` | 분류체계 3Depth |
| `zipcode` | `string` | 우편번호 |

### 5. `detailCommon2` 공통 정보 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/detailCommon2` |
| 설명 | 반려동물 동반여행지의 타입별 공통 정보(제목, 연락처, 주소, 좌표, 개요정보 등)를 조회하는 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `detailCommon2_response` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultMsg` | `string` | API 호출 결과의 상태 코드 |
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
| `mlevel` | `string` | Map Level 응답 |
| `overview` | `string` | 콘텐츠 개요 조회 |
| `contentid` | `string` | 콘텐츠ID |
| `contenttypeid` | `string` | 관광타입(12:관광지, 14:문화시설, 15:축제공연행사, 28:레포츠, 32:숙박, 38:쇼핑, 39:음식점) ID |
| `title` | `string` | 콘텐츠 제목 |
| `createdtime` | `string` | 콘텐츠 최초 등록일 |
| `homepage` | `string` | 홈페이지 주소 |
| `modifiedtime` | `string` | 콘텐츠 수정일 |
| `tel` | `string` | 전화번호 |
| `telname` | `string` | 전화번호명 |
| `firstimage` | `string` | 대표이미지(원본) |
| `firstimage2` | `string` | 대표이미지(썸네일) |
| `cpyrhtDivCd` | `string` | 대표이미지 저작권 유형 - Type1:제1유형(출처표시), Type3:제3유형(제1유형+변경금지) |
| `areacode` | `string` | 지역코드 |
| `sigungucode` | `string` | 시군구코드 |
| `cat1` | `string` | 대분류 코드 |
| `cat2` | `string` | 중분류 코드 |
| `cat3` | `string` | 소분류 코드 |
| `addr1` | `string` | 주소(예, 서울 중구 다동)를 응답 |
| `addr2` | `string` | 상세주소 |
| `zipcode` | `string` | 우편번호 |
| `mapx` | `string` | GPS X좌표(WGS84 경도 좌표) 응답 |
| `mapy` | `string` | GPS Y좌표(WGS84 위도 좌표) 응답 |
| `lclsSystm1` | `string` | 분류체계 1Depth |
| `lclsSystm2` | `string` | 분류체계 2Depth |
| `lclsSystm3` | `string` | 분류체계 3Depth |
| `lDongRegnCd` | `string` | 법정동 시도 코드 |
| `lDongSignguCd` | `string` | 법정동 시군구 코드 |

### 6. `detailIntro2` 소개 정보 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/detailIntro2` |
| 설명 | 반려동물 동반여행지의 관광타입별 소개 정보(휴무일, 개장 시간, 주차 시설 등)를 조회하는 기능입니다. 각 타입마다 응답 항목이 다르게 제공됩니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `detailIntro2_response` |

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
| `expagerangeleports` | `string` | 레포츠(28):체험 가능연령 |
| `infocentershopping` | `string` | 쇼핑(38):문의 및 안내 |
| `chkcreditcardculture` | `string` | 문화시설(14):신용카드 가능 여부 |
| `discountinfo` | `string` | 문화시설(14):할인정보 |
| `infocenterculture` | `string` | 문화시설(14):문의 및 안내 |
| `parkingculture` | `string` | 문화시설(14):주차시설 |
| `parkingfee` | `string` | 문화시설(14):주차요금 |
| `restdateculture` | `string` | 문화시설(14):쉬는날 |
| `playtime` | `string` | 행사공연축제(15):공연시간 |
| `program` | `string` | 행사공연축제(15):행사 프로그램 |
| `spendtimefestival` | `string` | 행사공연축제(15):관람 소요시간 |
| `sponsor1` | `string` | 행사공연축제(15):주최자 정보 |
| `sponsor1tel` | `string` | 행사공연축제(15):주최자 연락처 |
| `sponsor2` | `string` | 행사공연축제(15):주관사 정보 |
| `sponsor2tel` | `string` | 행사공연축제(15):주관사 연락처 |
| `subevent` | `string` | 행사공연축제(15):부대행사 |
| `usetimefestival` | `string` | 행사공연축제(15):이용요금 |
| `accomcountleports` | `string` | 레포츠(28):수용인원 |
| `chkcreditcardleports` | `string` | 레포츠(28):신용카드 가능 여부 |
| `infocenterleports` | `string` | 레포츠(28):문의 및 안내 |
| `openperiod` | `string` | 레포츠(28):개장기간 |
| `parkingfeeleports` | `string` | 레포츠(28):주차요금 |
| `parkingleports` | `string` | 레포츠(28):주차시설 |
| `reservation` | `string` | 레포츠(28):예약안내 |
| `restdateleports` | `string` | 레포츠(28):쉬는날 |
| `scaleleports` | `string` | 레포츠(28):규모 |
| `usefeeleports` | `string` | 레포츠(28):입장료 |
| `usefee` | `string` | 문화시설(14):이용요금 |
| `usetimeculture` | `string` | 문화시설(14):이용시간 |
| `scale` | `string` | 문화시설(14):규모 |
| `spendtime` | `string` | 문화시설(14):관람 소요시간 |
| `agelimit` | `string` | 행사공연축제(15):관람 가능연령 |
| `bookingplace` | `string` | 행사공연축제(15):예매처 |
| `discountinfofestival` | `string` | 행사공연축제(15):할인정보 |
| `eventenddate` | `string` | 행사공연축제(15):행사 종료일 |
| `eventhomepage` | `string` | 행사공연축제(15):행사 홈페이지 |
| `eventplace` | `string` | 행사공연축제(15):행사 장소 |
| `eventstartdate` | `string` | 행사공연축제(15):행사 시작일 |
| `festivalgrade` | `string` | 행사공연축제(15):축제등급 |
| `placeinfo` | `string` | 행사공연축제(15):행사장 위치안내 |
| `contenttypeid` | `string` | 기본정보 : 관광타입(12:관광지, 14:문화시설, 15:축제공연행사, 28:레포츠, 32:숙박, 38:쇼핑, 39:음식점) ID |
| `accomcount` | `string` | 관광지(12):수용인원 |
| `chkcreditcard` | `string` | 관광지(12):신용카드 가능 여부 |
| `expagerange` | `string` | 관광지(12):체험가능 연령 |
| `expguide` | `string` | 관광지(12):체험안내 |
| `heritage1` | `string` | 관광지(12):세계 문화유산 유무 |
| `heritage2` | `string` | 관광지(12):세계 자연유산 유무 |
| `heritage3` | `string` | 관광지(12):세계 기록유산 유무 |
| `infocenter` | `string` | 관광지(12):문의 및 안내 |
| `opendate` | `string` | 관광지(12):개장일 |
| `parking` | `string` | 관광지(12):주차시설 |
| `restdate` | `string` | 관광지(12):쉬는날 |
| `useseason` | `string` | 관광지(12):이용시기 |
| `usetime` | `string` | 관광지(12):이용시간 |
| `accomcountculture` | `string` | 문화시설(14):수용인원 |
| `fitness` | `string` | 숙박(32):휘트니스 센터 여부 |
| `lcnsno` | `string` | 음식점(39):인허가번호 |
| `contentid` | `string` | 기본정보 : 콘텐츠ID |
| `parkingshopping` | `string` | 쇼핑(38):주차시설 |
| `restdateshopping` | `string` | 쇼핑(38):쉬는날 |
| `restroom` | `string` | 쇼핑(38):화장실 설명 |
| `publicbath` | `string` | 숙박(32):공용 샤워실 여부 |
| `publicpc` | `string` | 숙박(32):공용 PC실 여부 |
| `sauna` | `string` | 숙박(32):사우나실 여부 |
| `saleitem` | `string` | 쇼핑(38):판매 품목 |
| `saleitemcost` | `string` | 쇼핑(38):판매 품목별 가격 |
| `scaleshopping` | `string` | 쇼핑(38):규모 |
| `shopguide` | `string` | 쇼핑(38):매장안내 |
| `chkcreditcardfood` | `string` | 음식점(39):신용카드 가능 여부 |
| `discountinfofood` | `string` | 음식점(39):할인정보 |
| `firstmenu` | `string` | 음식점(39):대표 메뉴 |
| `infocenterfood` | `string` | 음식점(39):문의 및 안내 |
| `kidsfacility` | `string` | 음식점(39):어린이 놀이방 |
| `opendatefood` | `string` | 음식점(39):개업일 |
| `opentimefood` | `string` | 음식점(39):영업시간 |
| `packing` | `string` | 음식점(39):포장 가능 여부 |
| `parkingfood` | `string` | 음식점(39):주차시설 |
| `reservationfood` | `string` | 음식점(39):예약안내 |
| `restdatefood` | `string` | 음식점(39):쉬는날 |
| `scalefood` | `string` | 음식점(39):규모 |
| `seat` | `string` | 음식점(39):좌석수 |
| `smoking` | `string` | 음식점(39):금연/흡연 여부 |
| `treatmenu` | `string` | 음식점(39):취급 메뉴 |
| `chkcreditcardshopping` | `string` | 쇼핑(38):신용카드 가능 여부 |
| `culturecenter` | `string` | 쇼핑(38):문화센터 바로가기 |
| `reservationlodging` | `string` | 숙박(32):예약안내 |
| `reservationurl` | `string` | 숙박(32):예약안내 홈페이지 |
| `roomtype` | `string` | 숙박(32):객실유형 |
| `scalelodging` | `string` | 숙박(32):규모 |
| `subfacility` | `string` | 숙박(32):부대시설 (기타) |
| `barbecue` | `string` | 숙박(32):바비큐장 여부 |
| `beauty` | `string` | 숙박(32):뷰티시설 정보 |
| `opendateshopping` | `string` | 쇼핑(38):개장일 |
| `opentime` | `string` | 쇼핑(38):영업시간 |
| `usetimeleports` | `string` | 레포츠(28):이용시간 |
| `accomcountlodging` | `string` | 숙박(32):수용 가능인원 |
| `benikia` | `string` | 숙박(32):베니키아 여부 |
| `checkintime` | `string` | 숙박(32):입실 시간 |
| `checkouttime` | `string` | 숙박(32):퇴실 시간 |
| `chkcooking` | `string` | 숙박(32):객실내 취사 여부 |
| `foodplace` | `string` | 숙박(32):식음료장 |
| `goodstay` | `string` | 숙박(32):굿스테이 여부 |
| `hanok` | `string` | 숙박(32):한옥 여부 |
| `infocenterlodging` | `string` | 숙박(32):문의 및 안내 |
| `parkinglodging` | `string` | 숙박(32):주차시설 |
| `pickup` | `string` | 숙박(32):픽업 서비스 |
| `roomcount` | `string` | 숙박(32):객실수 |
| `beverage` | `string` | 숙박(32):식음료장 여부 |
| `bicycle` | `string` | 숙박(32):자전거 대여 여부 |
| `campfire` | `string` | 숙박(32):캠프파이어 여부 |
| `karaoke` | `string` | 숙박(32):노래방 여부 |
| `seminar` | `string` | 숙박(32):세미나실 여부 |
| `sports` | `string` | 숙박(32):스포츠 시설 여부 |
| `refundregulation` | `string` | 숙박(32):환불규정 |
| `fairday` | `string` | 쇼핑(38):장서는 날 |
| `chkbabycarriage` | `string` | 관광지(12) : 유모차대여정보 |
| `chkbabycarriageleports` | `string` | 레포츠(28) : 유모차대여정보 |
| `chkbabycarriageshopping` | `string` | 쇼핑(38) : 유모차대여정보 |
| `chkbabycarriageculture` | `string` | 문화시설(14) : 유모차대여정보 |
| `chkpetculture` | `string` | 문화시설(14) : 애완동물동반가능정보 |
| `chkpet` | `string` | 관광지(12) : 애완동물동반가능정보 |
| `chkpetleports` | `string` | 레포츠(28) : 애완동물동반가능정보 |
| `chkpetshopping` | `string` | 쇼핑(38) : 애완동물동반가능정보 |

### 7. `detailInfo2` 반복 정보 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/detailInfo2` |
| 설명 | 반려동물 동반여행지의 관광타입별 반복 정보를 조회하는 기능입니다. “숙박”은 객실 정보를 제공합니다. “숙박”를 제외한 나머지 타입은 다양한 정보를 반복적인 형태로 제공합니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `detailInfo2_response` |

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
| `roomTable` | `string` | 숙박(32):테이블 |
| `roomcable` | `string` | 숙박(32):케이블설치 |
| `roombathfacility` | `string` | 숙박(32):목욕시설 |
| `contentid` | `string` | 기본정보 : 콘텐츠ID |
| `contenttypeid` | `string` | 기본정보 : 관광타입(12:관광지, 14:문화시설, 15:축제공연행사,28:레포츠, 32:숙박, 38:쇼핑, 39:음식점) ID |
| `roomtitle` | `string` | 숙박(32):객실명칭 |
| `roomsize1` | `string` | 숙박(32):객실크기(평) |
| `roomcount` | `string` | 숙박(32):객실수 |
| `roombasecount` | `string` | 숙박(32):기준인원 |
| `roommaxcount` | `string` | 숙박(32):최대인원 |
| `roomoffseasonminfee1` | `string` | 숙박(32):비수기주중최소 |
| `roomoffseasonminfee2` | `string` | 숙박(32):비수기주말최소 |
| `roompeakseasonminfee1` | `string` | 숙박(32):성수기주중최소 |
| `roompeakseasonminfee2` | `string` | 숙박(32):성수기주말최소 |
| `roomintro` | `string` | 숙박(32):객실소개 |
| `roombath` | `string` | 숙박(32):욕조 |
| `roomhometheater` | `string` | 숙박(32):홈시어터 |
| `roomaircondition` | `string` | 숙박(32):에어컨 |
| `roomtv` | `string` | 숙박(32):TV |
| `roompc` | `string` | 숙박(32):PC |
| `roominternet` | `string` | 숙박(32):인터넷 |
| `roomrefrigerator` | `string` | 숙박(32):냉장고 |
| `roomtoiletries` | `string` | 숙박(32):세면도구 |
| `roomsofa` | `string` | 숙박(32):소파 |
| `roomcook` | `string` | 숙박(32):취사용품 |
| `roomhairdryer` | `string` | 숙박(32):드라이기 |
| `roomsize2` | `string` | 숙박(32):객실크기(평방미터) |
| `roomimg1` | `string` | 숙박(32):객실사진1 |
| `roomimg1cpyrhtdiv` | `string` | 숙박(32):객실사진1 저작권유형 - Type1:제1유형(출처표시-권장), Type3:제3유형(제1유형+변경금지) |
| `roomimg1alt` | `string` | 숙박(32):객실사진1 설명 |
| `roomimg2` | `string` | 숙박(32):객실사진2 |
| `roomimg2cpyrhtdiv` | `string` | 숙박(32):객실사진2 저작권유형 - Type1:제1유형(출처표시-권장), Type3:제3유형(제1유형+변경금지) |
| `roomimg2alt` | `string` | 숙박(32):객실사진2 설명 |
| `roomimg3` | `string` | 숙박(32):객실사진3 |
| `roomimg3alt` | `string` | 숙박(32):객실사진3 설명 |
| `roomimg3cpyrhtdiv` | `string` | 숙박(32):객실사진3 저작권유형 - Type1:제1유형(출처표시-권장), Type3:제3유형(제1유형+변경금지) |
| `roomimg4` | `string` | 숙박(32):객실사진4 |
| `roomimg4alt` | `string` | 숙박(32):객실사진4 설명 |
| `roomimg4cpyrhtdiv` | `string` | 숙박(32):객실사진4 저작권유형 - Type1:제1유형(출처표시-권장), Type3:제3유형(제1유형+변경금지) |
| `roomimg5` | `string` | 숙박(32):객실사진5 |
| `roomimg5alt` | `string` | 숙박(32):객실사진5 설명 |
| `roomimg5cpyrhtdiv` | `string` | 숙박(32):객실사진5 저작권유형 - Type1:제1유형(출처표시-권장), Type3:제3유형(제1유형+변경금지) |
| `fldgubun` | `string` | 숙박/여행코스 제외 관광타입:일련번호 |
| `infoname` | `string` | 숙박/여행코스 제외 관광타입:제목 ( 매뉴얼 문서 반복정보 숙박/여행코스 제외 항목 참고 ) |
| `infotext` | `string` | 숙박/여행코스 제외 관광타입:내용 ( 매뉴얼 문서 반복정보 숙박/여행코스 제외 항목 참고 ) |
| `serialnum` | `string` | 숙박/여행코스 제외 관광타입:반복 일련번호 |
| `roominfono` | `string` | 숙박(32):객실정보번호 |

### 8. `detailPetTour2` 반려동물 동반여행 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/detailPetTour2` |
| 설명 | 반려동물 동반여행 정보 목록을 제공합니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `detailPetTour2_response` |

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
| `acmpyNeedMtr` | `string` | 동반시 필요사항 |
| `contentid` | `string` | 콘텐츠ID |
| `relaAcdntRiskMtr` | `string` | 관련 사고 대비사항 |
| `acmpyTypeCd` | `string` | 동반유형코드(동반구분) |
| `relaPosesFclty` | `string` | 관련 구비 시설 |
| `relaFrnshPrdlst` | `string` | 관련 비치 품목 |
| `etcAcmpyInfo` | `string` | 기타 동반 정보 |
| `relaPurcPrdlst` | `string` | 관련 구매 품목 |
| `acmpyPsblCpam` | `string` | 동반가능동물 |
| `relaRntlPrdlst` | `string` | 관련 렌탈 품목 |

### 9. `petTourSyncList2` 반려동물 동반여행 정보 동기화 목록 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/petTourSyncList2` |
| 설명 | 반려동물 동반여행 정보 동기화 목록 정보를 제공합니다. (콘텐츠 표출 여부 제공) |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `petTourSyncList2_response` |

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
| `showflag` | `string` | 컨텐츠표출여부(1=표출,0=비표출) |
| `contentid` | `string` | 콘텐츠ID |
| `contenttypeid` | `string` | 관광타입(12:관광지, 14:문화시설, 15:축제공연행사, 28:레포츠, 32:숙박, 38:쇼핑, 39:음식점) ID |
| `title` | `string` | 제목 |
| `createdtime` | `string` | 콘텐츠 등록일 |
| `modifiedtime` | `string` | 콘텐츠 수정일 |
| `tel` | `string` | 전화번호 |
| `cat1` | `string` | 대분류 코드 |
| `cat2` | `string` | 중분류 코드 |
| `cat3` | `string` | 소분류 코드 |
| `zipcode` | `string` | 우편번호 |
| `addr1` | `string` | 주소 |
| `addr2` | `string` | 상세주소 |
| `areacode` | `string` | 지역코드 |
| `sigungucode` | `string` | 시군구코드 |
| `mapx` | `string` | GPS X좌표(WGS84 경도 좌표) |
| `mapy` | `string` | GPS Y좌표(WGS84 위도 좌표) |
| `mlevel` | `string` | Map Level 응답 |
| `firstimage` | `string` | 원본 대표이미지 URL |
| `firstimage2` | `string` | 썸네일 대표이미지 URL |
| `cpyrhtDivCd` | `string` | 대표이미지 저작권 유형 - Type1:제1유형(출처표시-권장), Type3:제3유형(제1유형+변경금지) |
| `lDongRegnCd` | `string` | 법정동 시도 코드 |
| `lDongSignguCd` | `string` | 법정동 시군구 코드 |
| `lclsSystm1` | `string` | 분류체계 1Depth |
| `lclsSystm2` | `string` | 분류체계 2Depth |
| `lclsSystm3` | `string` | 분류체계 3Depth |

### 10. `areaCode2` 지역코드 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/areaCode2` |
| 설명 | 반려동물 동반여행지의 지역코드, 시군구코드 목록을 조회하는 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `areaCode2_response` |

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
| `name` | `string` | 코드:지역명 또는 시군구명 |
| `rnum` | `string` | 일련번호 |
| `code` | `string` | 코드:지역코드 또는 시군구코드 |

### 11. `locationBasedList2` 위치기반 관광정보 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/locationBasedList2` |
| 설명 | 반려동물 동반 여행지의 주변 좌표를 기반으로 관광정보 목록을 조회하는 기능입니다. 파라미터에 따라 제목순, 수정일순(최신순), 등록일순, 거리순 정렬 검색을 제공합니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `locationBasedList2_response` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultMsg` | `string` | API 호출 결과의 상태 코드 |
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
| `lclsSystm3` | `string` | 분류체계 3Depth |
| `cpyrhtDivCd` | `string` | 대표이미지 저작권 유형 - Type1:제1유형(출처표시-권장), Type3:제3유형(제1유형+변경금지) |
| `contentid` | `string` | 콘텐츠ID |
| `contenttypeid` | `string` | 관광타입(12:관광지, 14:문화시설, 15:축제공연행사, 28:레포츠, 32:숙박, 38:쇼핑, 39:음식점) ID |
| `title` | `string` | 제목 |
| `createdtime` | `string` | 콘텐츠 등록일 |
| `modifiedtime` | `string` | 콘텐츠 수정일 |
| `tel` | `string` | 전화번호 |
| `cat1` | `string` | 대분류 코드 |
| `cat2` | `string` | 중분류 코드 |
| `cat3` | `string` | 소분류 코드 |
| `addr1` | `string` | 주소 |
| `addr2` | `string` | 상세주소 |
| `areacode` | `string` | 지역코드 |
| `sigungucode` | `string` | 시군구코드 |
| `mapx` | `string` | GPS X좌표(WGS84 경도 좌표) |
| `mapy` | `string` | GPS Y좌표(WGS84 위도 좌표) |
| `mlevel` | `string` | Map Level 응답 |
| `dist` | `string` | 거리반경(단위:m), Max값 20000m=20Km |
| `firstimage` | `string` | 원본 대표이미지 URL |
| `firstimage2` | `string` | 썸네일 대표이미지 URL |
| `lDongRegnCd` | `string` | 법정동 시도 코드 |
| `lDongSignguCd` | `string` | 법정동 시군구 코드 |
| `lclsSystm1` | `string` | 분류체계 1Depth |
| `lclsSystm2` | `string` | 분류체계 2Depth |
| `zipcode` | `string` | 우편번호 |

### 12. `ldongCode2` 법정동 코드 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/ldongCode2` |
| 설명 | 법정동 코드 목록을 시도, 시군구 코드 별 조회하는 기능 |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `ldongCode2_response` |

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

### 13. `lclsSystmCode2` 분류체계 코드 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/lclsSystmCode2` |
| 설명 | 분류체계 코드 목록을 1Depth, 2Depth, 3Depth 코드 별 조회하는 기능 |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `lclsSystmCode2_response` |

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
| `code` | `string` | 코드: 1Depth, 2Depth, 3Depth 코드(lclsSystmListYn : N 일때 표출) |
| `name` | `string` | 코드: 1Depth, 2Depth, 3Depth 코드명(lclsSystmListYn : N 일때 표출) |
| `lclsSystm1Cd` | `string` | 분류체계 대분류 코드(lclsSystmListYn : Y 일때 표출) |
| `lclsSystm1Nm` | `string` | 분류체계 대분류명(lclsSystmListYn : Y 일때 표출) |
| `lclsSystm2Cd` | `string` | 분류체계 중분류 코드(lclsSystmListYn : Y 일때 표출) |
| `lclsSystm2Nm` | `string` | 분류체계 중분류명(lclsSystmListYn : Y 일때 표출) |
| `lclsSystm3Cd` | `string` | 분류체계 소분류 코드(lclsSystmListYn : Y 일때 표출) |
| `lclsSystm3Nm` | `string` | 분류체계 소분류명(lclsSystmListYn : Y 일때 표출) |
