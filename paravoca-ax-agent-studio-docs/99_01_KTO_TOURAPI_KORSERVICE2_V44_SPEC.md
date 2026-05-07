# 99-01. TourAPI KorService2 v4.4 API 명세

작성 기준일: 2026-05-07

이 문서는 기존 `05_03_TOURAPI_KORSERVICE2_V44_SPEC.md`를 99번 API 명세 체계에 맞춰 복사한 정규화본입니다. 앞으로 API 명세의 canonical 번호는 `99_00` 인덱스와 `99_01`-`99_12` 문서를 기준으로 봅니다.

이 문서는 한국관광공사 개방데이터 활용매뉴얼 국문 v4.4와 신분류체계정보 관광타입정보 연계 정의서를 PARAVOCA 구현 기준으로 재정리한 내부 명세입니다. 원문을 그대로 복사한 문서가 아니라, backend provider, GeoResolverAgent, RAG metadata, QA 검수에서 바로 사용할 수 있도록 endpoint, 요청 파라미터, 응답 필드, 구현 주의사항을 정규화했습니다.

원본 확인 파일:

- `/Users/yongchoooon/Downloads/개방데이터_활용매뉴얼(국문)/한국관광공사_개방데이터_활용매뉴얼(국문)_v4.4.docx`
- `/Users/yongchoooon/Downloads/개방데이터_활용매뉴얼(국문)/신분류체계정보 관광타입정보 연계 정의서.xlsx`

추가 검증 입력:

- 2026-05-07 사용자가 제공한 KorService2 response schema excerpt

검증 결과 정정 요약:

- 기존 문서의 Operation 목록에서 빠져 있던 `areaCode2`, `categoryCode2`를 복구했습니다.
- `areaBasedSyncList2` 응답 필드에 `oldContentid`가 빠져 있어 추가했습니다.
- `detailPetTour2` 응답 필드에 사용자가 제공한 response schema에 없는 `petTursmInfo`가 들어 있어 제거했습니다.
- 사용자가 제공한 schema는 PARAVOCA가 현재 구현했거나 Phase 9.6에서 쓰려는 KorService2 operation을 모두 포함합니다.
- 다만 PARAVOCA 확장 계획에 있는 KorService2 외 KTO API들은 이 schema에 포함되어 있지 않으므로 별도 명세 확인이 필요합니다.

## 핵심 결론

v4.4 기준 KorService2의 지역 필터는 기존 `areaCode`/`sigunguCode`보다 `lDongRegnCd`/`lDongSignguCd` 법정동 코드 중심으로 봐야 합니다. 일부 응답에는 여전히 `areacode`/`sigungucode`가 내려오지만, v4.4 문서의 목록/검색 operation 요청 명세는 법정동 코드와 신분류체계를 기준으로 정리되어 있습니다.

현재 PARAVOCA의 기존 `areaCode2` 기반 지역 처리와 `region_code` metadata는 Phase 9.6에서 `ldong_regn_cd`, `ldong_signgu_cd`, `lcls_systm_1/2/3` 중심으로 전환해야 합니다.

실제 확인 예시:

| 조회 | 요청 | 결과 |
|---|---|---|
| 대전 행사 | `searchFestival2?eventStartDate=20260501&eventEndDate=20260531&areaCode=3` | 0건 |
| 대전 행사 | `searchFestival2?eventStartDate=20260501&eventEndDate=20260531&lDongRegnCd=30` | `유성온천문화축제` 반환 |

## 공통 호출 규칙

서비스 개요:

| 항목 | 값 |
|---|---|
| 서비스 ID | `KorService2` |
| 서비스명 | 국문 관광정보 서비스 |
| 인터페이스 | REST GET |
| 응답 형식 | XML 기본, JSON 선택 |
| 전송 | HTTP/HTTPS |
| 인증 | 공공데이터포털 service key |
| 문서상 서비스 버전 | 4.0 |
| 데이터 갱신 주기 | 일 1회 |

Base URL:

```text
https://apis.data.go.kr/B551011/KorService2
```

응답 기본값은 XML이며 JSON을 받으려면 `_type=json`을 전달합니다.

공통 요청 파라미터:

| 파라미터 | 필수 | 설명 |
|---|---:|---|
| `serviceKey` | Y | 공공데이터포털 인증키 |
| `MobileOS` | Y | `IOS`, `AND`, `WEB`, `ETC` 중 하나 |
| `MobileApp` | Y | 서비스명 또는 앱명. 통계 산출용이므로 항상 전달 |
| `_type` | N | JSON 응답 필요 시 `json` |
| `numOfRows` | N | 페이지당 결과 수 |
| `pageNo` | N | 페이지 번호 |

공통 응답 envelope:

```json
{
  "response": {
    "header": {
      "resultCode": "0000",
      "resultMsg": "OK"
    },
    "body": {
      "items": {
        "item": []
      },
      "numOfRows": 10,
      "pageNo": 1,
      "totalCount": 0
    }
  }
}
```

구현 규칙:

- `resultCode != "0000"`이면 tool call 실패로 기록하고 예외 처리합니다.
- `items.item`은 단일 object 또는 list로 올 수 있으므로 항상 list로 정규화합니다.
- 빈 결과는 API 실패가 아닐 수 있습니다. 단, 사용자가 지역을 명시했는데 지역 필터가 빠진 전국 검색으로 fallback하면 안 됩니다.
- `MobileOS`, `MobileApp`, `_type=json`은 provider 공통 파라미터로 주입합니다.

## Operation 목록

| 번호 | Operation | 국문명 | 성격 | 현재 PARAVOCA 상태 |
|---:|---|---|---|---|
| 1 | `areaCode2` | 지역코드 조회 | legacy 코드 조회 | 구현되어 있으나 v4.4 전환 후 fallback/catalog 참고용 |
| 2 | `ldongCode2` | 법정동 코드 조회 | 코드 조회 | Phase 9.6 P0 |
| 3 | `lclsSystmCode2` | 분류체계 코드 조회 | 코드 조회 | Phase 9.6 P0 |
| 4 | `categoryCode2` | 서비스분류코드 조회 | legacy 코드 조회 | provider method 있음, workflow 미활용 |
| 5 | `areaBasedList2` | 지역기반 관광정보 조회 | 목록 | 구현되어 있으나 `areaCode` 중심이라 v4.4 전환 필요 |
| 6 | `locationBasedList2` | 위치기반 관광정보 조회 | 목록 | provider method 있음, workflow 미활용 |
| 7 | `searchKeyword2` | 키워드 검색 조회 | 목록 | 구현되어 있으나 `areaCode` 중심이라 v4.4 전환 필요 |
| 8 | `searchFestival2` | 행사정보 조회 | 목록 | 구현되어 있으나 `areaCode` 중심이라 v4.4 전환 필요 |
| 9 | `searchStay2` | 숙박정보 조회 | 목록 | 구현되어 있으나 `areaCode` 중심이라 v4.4 전환 필요 |
| 10 | `detailCommon2` | 공통정보 조회 | 상세 1 | Phase 9에서 구현 |
| 11 | `detailIntro2` | 소개정보 조회 | 상세 2 | Phase 9에서 구현 |
| 12 | `detailInfo2` | 반복정보 조회 | 상세 3 | Phase 9에서 구현 |
| 13 | `detailImage2` | 이미지정보 조회 | 상세 4 | Phase 9에서 구현 |
| 14 | `areaBasedSyncList2` | 국문 관광정보 동기화 목록 조회 | 동기화 목록 | 미구현 |
| 15 | `detailPetTour2` | 반려동물 동반여행 정보 조회 | 상세 | 미구현 |

## ContentTypeId 코드표

| ContentTypeId | 타입 |
|---:|---|
| `12` | 관광지 |
| `14` | 문화시설 |
| `15` | 행사/공연/축제 |
| `25` | 여행코스 |
| `28` | 레포츠 |
| `32` | 숙박 |
| `38` | 쇼핑 |
| `39` | 음식점 |

## Sort `arrange` 코드

목록 operation에서 사용하는 정렬 코드입니다.

| 코드 | 의미 | 비고 |
|---|---|---|
| `A` | 제목순 | 목록 공통 |
| `C` | 수정일순, 최신순 | 목록 공통 |
| `D` | 생성일순 | 목록 공통 |
| `E` | 거리순 | `locationBasedList2` |
| `O` | 대표 이미지 필수 + 제목순 | 이미지 있는 항목만 |
| `Q` | 대표 이미지 필수 + 수정일순 | 이미지 있는 항목만 |
| `R` | 대표 이미지 필수 + 생성일순 | 이미지 있는 항목만 |
| `S` | 대표 이미지 필수 + 거리순 | `locationBasedList2` |

## 1. Legacy 지역 코드 `areaCode2`

Endpoint:

```text
GET /areaCode2
```

용도:

- 기존 시도/시군구 코드 체계를 조회합니다.
- 현재 PARAVOCA provider와 workflow가 지역명 resolution에 사용하고 있습니다.
- v4.4 전환 후에는 primary 지역 필터를 `ldongCode2`의 법정동 코드로 옮기고, `areaCode2`는 backward compatibility와 legacy 응답 해석용으로만 둡니다.

요청 파라미터:

| 파라미터 | 필수 | 설명 |
|---|---:|---|
| 공통 파라미터 | 일부 | `serviceKey`, `MobileOS`, `MobileApp`, `_type`, `numOfRows`, `pageNo` |
| `areaCode` | N | 시도 코드. 없으면 시도 목록, 있으면 해당 시도의 시군구 목록 |

응답 필드:

| 필드 | 설명 |
|---|---|
| `code` | 지역코드 또는 시군구코드 |
| `name` | 지역명 또는 시군구명 |
| `rnum` | 일련번호 |

PARAVOCA 구현:

- 현재 `TourApiProvider.area_code()`가 이 operation을 호출합니다.
- Phase 9.6 이후에는 `region_code`를 `areaCode2` 결과로만 새로 확정하지 않고, `ldongCode2` 결과를 우선합니다.

## 2. 법정동 코드 `ldongCode2`

Endpoint:

```text
GET /ldongCode2
```

용도:

- 시도 코드와 시군구 코드를 조회합니다.
- Phase 9.6의 GeoResolverAgent에서 지역 후보 catalog의 기준 데이터로 사용합니다.
- 목록/검색 API의 `lDongRegnCd`, `lDongSignguCd` 필터로 연결됩니다.

요청 파라미터:

| 파라미터 | 필수 | 설명 |
|---|---:|---|
| 공통 파라미터 | 일부 | `serviceKey`, `MobileOS`, `MobileApp`, `_type`, `numOfRows`, `pageNo` |
| `lDongRegnCd` | N | 시도 코드. 없으면 시도 목록, 있으면 해당 시도의 시군구 목록 |
| `lDongListYn` | N | `N`: 코드 조회 형식, `Y`: 전체 법정동 목록 형식 |

응답 필드:

| 필드 | 설명 |
|---|---|
| `code` | `lDongListYn=N`일 때 시도 또는 시군구 코드 |
| `name` | `lDongListYn=N`일 때 시도명 또는 시군구명 |
| `rnum` | 일련번호 |
| `lDongRegnCd` | `lDongListYn=Y`일 때 법정동 시도 코드 |
| `lDongRegnNm` | `lDongListYn=Y`일 때 법정동 시도명 |
| `lDongSignguCd` | `lDongListYn=Y`일 때 법정동 시군구 코드 |
| `lDongSignguNm` | `lDongListYn=Y`일 때 법정동 시군구명 |

실제 확인한 주요 코드:

| 지역 | `lDongRegnCd` | `lDongSignguCd` |
|---|---:|---:|
| 서울특별시 | `11` | 시군구별 별도 |
| 부산광역시 | `26` | 시군구별 별도 |
| 대구광역시 | `27` | 시군구별 별도 |
| 인천광역시 | `28` | 시군구별 별도 |
| 광주광역시 | `29` | 시군구별 별도 |
| 대전광역시 | `30` | 시군구별 별도 |
| 울산광역시 | `31` | 시군구별 별도 |
| 경기도 | `41` | 시군구별 별도 |
| 충청북도 | `43` | 시군구별 별도 |
| 충청남도 | `44` | 시군구별 별도 |
| 전라남도 | `46` | 시군구별 별도 |
| 경상북도 | `47` | 시군구별 별도 |
| 경상남도 | `48` | 시군구별 별도 |
| 제주특별자치도 | `50` | 시군구별 별도 |
| 강원특별자치도 | `51` | 시군구별 별도 |
| 전북특별자치도 | `52` | 시군구별 별도 |
| 세종특별자치시 | `36110` | 단일 코드 성격 |

Phase 9.6 alias seed 예시:

| 사용자 표현 | 해석 |
|---|---|
| 영종도 | 인천광역시 중구, `28`/`110`, keyword `영종도` |
| 가덕도 | 부산광역시 강서구, `26`/`440`, keyword `가덕도` |
| 울릉도 | 경상북도 울릉군, `47`/`940` |
| 영양 | 경상북도 영양군, `47`/`760` |
| 양산 | 경상남도 양산시, `48`/`330` |

## 3. 분류체계 코드 `lclsSystmCode2`

Endpoint:

```text
GET /lclsSystmCode2
```

용도:

- 신분류체계 1Depth/2Depth/3Depth 코드를 조회합니다.
- 목록/검색 API의 `lclsSystm1`, `lclsSystm2`, `lclsSystm3` 필터로 연결됩니다.
- 사용자 자연어의 테마, 예: 야경, 축제, 시장, 요트, 캠핑, 체험, 웰니스 등을 실제 TourAPI 분류로 매핑하는 기준입니다.

요청 파라미터:

| 파라미터 | 필수 | 설명 |
|---|---:|---|
| 공통 파라미터 | 일부 | `serviceKey`, `MobileOS`, `MobileApp`, `_type`, `numOfRows`, `pageNo` |
| `lclsSystm1` | N | 대분류 코드 |
| `lclsSystm2` | N | 중분류 코드. `lclsSystm1` 필요 |
| `lclsSystm3` | N | 소분류 코드. `lclsSystm1`, `lclsSystm2` 필요 |
| `lclsSystmListYn` | N | `N`: 단계별 코드 조회, `Y`: 전체 목록 조회 |

응답 필드:

| 필드 | 설명 |
|---|---|
| `code`, `name`, `rnum` | `lclsSystmListYn=N`일 때 단계별 코드/이름 |
| `lclsSystm1Cd`, `lclsSystm1Nm` | 대분류 코드/명 |
| `lclsSystm2Cd`, `lclsSystm2Nm` | 중분류 코드/명 |
| `lclsSystm3Cd`, `lclsSystm3Nm` | 소분류 코드/명 |

확인 결과:

- 원문 예시는 전체 목록 `totalCount=243`으로 표시됩니다.
- 실제 API 조회에서는 245건이 반환될 수 있습니다.
- 제공된 xlsx 정의서는 240개 mapping을 포함합니다.
- 운영 기준은 live API sync를 우선하고, xlsx는 seed/fallback 또는 검증 자료로 사용합니다.

중요 분류 예시:

| 사용자 의도 | 신분류체계 | ContentTypeId |
|---|---|---|
| 축제 | `EV01` 이하 | `15` |
| 공연 | `EV02` 이하 | `15` |
| 행사 | `EV03` 이하 | `15` |
| 전통체험 | `EX010100` | `12` |
| 공예체험 | `EX02` 이하 | `12` |
| 농산어촌 체험 | `EX03` 이하 | `12` |
| 웰니스 | `EX05` 이하 | `12` |
| 산업관광 | `EX06` 이하 | `12` |
| 수상레저, 요트 | `LS02`, `LS020300` 등 | `28` |
| 항공레저 | `LS03` 이하 | `28` |
| 섬 | `NA020500` | `12` |
| 해변, 해수욕장 | `NA020900` | `12` |
| 시장 | `SH06` 이하 | `38` |
| 음식점 | `FD` 이하 | `39` |

## 4. Legacy 서비스분류코드 `categoryCode2`

Endpoint:

```text
GET /categoryCode2
```

용도:

- 기존 `cat1`/`cat2`/`cat3` 분류 코드를 조회합니다.
- 현재 provider method와 capability catalog에는 있지만 workflow route/ranking에는 직접 연결되어 있지 않습니다.
- v4.4 전환 후에는 primary 테마 분류를 `lclsSystmCode2`의 신분류체계로 옮기고, 기존 응답의 `cat1`/`cat2`/`cat3` 해석용으로 보존합니다.

요청 파라미터:

| 파라미터 | 필수 | 설명 |
|---|---:|---|
| 공통 파라미터 | 일부 | `serviceKey`, `MobileOS`, `MobileApp`, `_type`, `numOfRows`, `pageNo` |
| `cat1` | N | 대분류 코드 |
| `cat2` | N | 중분류 코드. `cat1` 필요 |
| `cat3` | N | 소분류 코드. `cat1`, `cat2` 필요 |

응답 필드:

| 필드 | 설명 |
|---|---|
| `code` | 대분류/중분류/소분류 코드 |
| `name` | 대분류/중분류/소분류 코드명 |
| `rnum` | 일련번호 |

## 목록 Operation 공통 응답 필드

`areaBasedList2`, `locationBasedList2`, `searchKeyword2`, `searchFestival2`, `searchStay2`, `areaBasedSyncList2`는 대체로 아래 필드를 공유합니다.

| 필드 | 설명 |
|---|---|
| `addr1`, `addr2` | 주소, 상세주소 |
| `zipcode` | 우편번호 |
| `contentid` | 콘텐츠 ID |
| `contenttypeid` | 관광타입 ID |
| `createdtime`, `modifiedtime` | 등록일, 수정일 |
| `firstimage`, `firstimage2` | 대표 이미지 원본/썸네일 |
| `cpyrhtDivCd` | 이미지 저작권 유형. 주로 `Type1`, `Type3` |
| `mapx`, `mapy`, `mlevel` | WGS84 좌표와 지도 레벨 |
| `tel` | 전화번호 |
| `title` | 콘텐츠 제목 |
| `lDongRegnCd`, `lDongSignguCd` | 법정동 시도/시군구 코드 |
| `lclsSystm1`, `lclsSystm2`, `lclsSystm3` | 신분류체계 대/중/소 코드 |
| `areacode`, `sigungucode` | 미사용 항목. 법정동 시도/시군구 코드로 대체 예정 |
| `cat1`, `cat2`, `cat3` | 미사용 항목. 신분류체계 1/2/3Depth로 대체 예정 |

구현 주의:

- 기존 응답의 `areacode`, `sigungucode`, `cat1`, `cat2`, `cat3`는 저장은 하되 Phase 9.6 이후 primary filter key로 쓰지 않습니다.
- Chroma metadata는 `ldong_regn_cd`, `ldong_signgu_cd`, `lcls_systm_1/2/3`를 우선합니다.

## 5. `areaBasedList2` 지역기반 관광정보 조회

Endpoint:

```text
GET /areaBasedList2
```

용도:

- 특정 시도/시군구 또는 신분류체계 기준으로 관광정보 목록을 조회합니다.
- GeoResolverAgent가 만든 지역 scope의 기본 후보 수집에 사용합니다.

요청 파라미터:

| 파라미터 | 필수 | 설명 |
|---|---:|---|
| 공통 파라미터 | 일부 | 공통 호출 규칙 참고 |
| `arrange` | N | 정렬 코드 |
| `contentTypeId` | N | 관광타입 |
| `modifiedtime` | N | 콘텐츠 수정일, `YYYYMMDD` |
| `lDongRegnCd` | N | 법정동 시도 코드 |
| `lDongSignguCd` | N | 법정동 시군구 코드. `lDongRegnCd` 필요 |
| `lclsSystm1` | N | 분류 대분류 |
| `lclsSystm2` | N | 분류 중분류. `lclsSystm1` 필요 |
| `lclsSystm3` | N | 분류 소분류. `lclsSystm1`, `lclsSystm2` 필요 |

응답 필드:

- 목록 공통 응답 필드.

PARAVOCA 구현:

- 단일 지역 상품의 관광지, 문화시설, 레포츠, 쇼핑, 음식점 후보 조회에 사용합니다.
- `contentTypeId`를 여러 번 나누어 호출하는 방식이 안전합니다.
- 지역이 명시되었는데 `lDongRegnCd`가 없으면 호출하지 않습니다.

## 6. `locationBasedList2` 위치기반 관광정보 조회

Endpoint:

```text
GET /locationBasedList2
```

용도:

- 특정 좌표 주변 관광정보를 조회합니다.
- route형 상품에서 시작점/도착점 주변 후보를 보강하거나, 특정 evidence의 주변 식당/쇼핑/관광지를 찾을 때 사용합니다.

요청 파라미터:

| 파라미터 | 필수 | 설명 |
|---|---:|---|
| 공통 파라미터 | 일부 | 공통 호출 규칙 참고 |
| `arrange` | N | 정렬 코드. 거리순은 `E`, 이미지 필수 거리순은 `S` |
| `contentTypeId` | N | 관광타입 |
| `mapX` | Y | WGS84 경도 |
| `mapY` | Y | WGS84 위도 |
| `radius` | Y | 반경 m. 최대 20,000m |
| `modifiedtime` | N | 콘텐츠 수정일 |
| `lDongRegnCd` | N | 법정동 시도 코드 |
| `lDongSignguCd` | N | 법정동 시군구 코드 |
| `lclsSystm1/2/3` | N | 신분류체계 필터 |

응답 필드:

- 목록 공통 응답 필드.
- `dist`: 중심 좌표로부터 거리, 단위 m.

PARAVOCA 구현:

- Data Enrichment Agent에서 특정 장소 주변 식사/쇼핑/보조 관광지를 보강할 때 우선 활용합니다.
- `mapX/mapY`가 없는 자연어 지역만으로는 호출하지 않습니다.

## 7. `searchKeyword2` 키워드 검색 조회

Endpoint:

```text
GET /searchKeyword2
```

용도:

- 키워드와 지역/분류 필터를 조합해 관광정보를 검색합니다.
- 자연어 prompt의 핵심 장소명, 섬 이름, 테마 단어를 보존할 때 필요합니다.

요청 파라미터:

| 파라미터 | 필수 | 설명 |
|---|---:|---|
| 공통 파라미터 | 일부 | 공통 호출 규칙 참고 |
| `arrange` | N | 정렬 코드 |
| `keyword` | Y | 검색 키워드. 국문은 URL 인코딩 필요 |
| `lDongRegnCd` | N | 법정동 시도 코드 |
| `lDongSignguCd` | N | 법정동 시군구 코드 |
| `lclsSystm1/2/3` | N | 신분류체계 필터 |

응답 필드:

- 목록 공통 응답 필드.

PARAVOCA 구현:

- `영종도`, `가덕도`처럼 법정동 행정명과 다른 지명은 alias로 법정동을 좁힌 뒤 keyword를 유지해서 검색합니다.
- `keyword`가 너무 긴 문장 전체가 되면 결과 품질이 떨어지므로 GeoResolverAgent와 Planner가 장소 키워드, 테마 키워드, 제외 키워드를 분리해야 합니다.

## 8. `searchFestival2` 행사정보 조회

Endpoint:

```text
GET /searchFestival2
```

용도:

- 행사/공연/축제 정보를 날짜 기준으로 조회합니다.
- `contentTypeId=15`에 해당하는 데이터입니다.

요청 파라미터:

| 파라미터 | 필수 | 설명 |
|---|---:|---|
| 공통 파라미터 | 일부 | 공통 호출 규칙 참고 |
| `arrange` | N | 정렬 코드 |
| `eventStartDate` | Y | 행사 시작일, `YYYYMMDD` |
| `eventEndDate` | N | 행사 종료일, `YYYYMMDD` |
| `modifiedtime` | N | 콘텐츠 수정일 |
| `lDongRegnCd` | N | 법정동 시도 코드 |
| `lDongSignguCd` | N | 법정동 시군구 코드 |
| `lclsSystm1/2/3` | N | 축제/공연/행사 분류 필터. 예: `EV`, `EV01`, `EV010500` |

응답 필드:

| 필드 | 설명 |
|---|---|
| 목록 공통 필드 | 주소, 이미지, 좌표, 분류 등 |
| `eventstartdate`, `eventenddate` | 행사 시작/종료일 |
| `progresstype` | 진행상태정보 |
| `festivaltype` | 축제유형명 |

PARAVOCA 구현:

- 기간이 명확한 workflow에서는 반드시 이 operation을 사용합니다.
- v4.4 기준 대전 행사처럼 `areaCode`로는 누락되고 `lDongRegnCd`로는 반환되는 케이스가 있으므로, Phase 9.6 이후에는 `lDongRegnCd`를 우선해야 합니다.

## 9. `searchStay2` 숙박정보 조회

Endpoint:

```text
GET /searchStay2
```

용도:

- 숙박 후보 목록을 조회합니다.
- `contentTypeId=32`에 해당하는 데이터입니다.

요청 파라미터:

| 파라미터 | 필수 | 설명 |
|---|---:|---|
| 공통 파라미터 | 일부 | 공통 호출 규칙 참고 |
| `arrange` | N | 정렬 코드 |
| `modifiedtime` | N | 콘텐츠 수정일 |
| `lDongRegnCd` | N | 법정동 시도 코드 |
| `lDongSignguCd` | N | 법정동 시군구 코드 |
| `lclsSystm1/2/3` | N | 숙박 분류 필터. 예: `AC`, `AC03`, `AC030100` |

응답 필드:

- 목록 공통 응답 필드.

PARAVOCA 구현:

- 당일 상품에는 기본 호출을 줄이고, 숙박 포함 요청 또는 1박 이상 route형 요청일 때 우선 호출합니다.
- `detailIntro2`와 `detailInfo2`를 붙여 check-in/out, 객실, 예약 관련 근거를 보강해야 합니다.

## 10. `detailCommon2` 공통정보 조회

Endpoint:

```text
GET /detailCommon2
```

용도:

- 콘텐츠 ID의 공통 상세 정보를 조회합니다.
- Phase 9에서 이미 evidence 강화에 사용하고 있습니다.

요청 파라미터:

| 파라미터 | 필수 | 설명 |
|---|---:|---|
| 공통 파라미터 | 일부 | 공통 호출 규칙 참고 |
| `contentId` | Y | 콘텐츠 ID |

응답 필드:

| 필드 | 설명 |
|---|---|
| `contentid`, `contenttypeid` | 콘텐츠 ID, 관광타입 |
| `title` | 제목 |
| `createdtime`, `modifiedtime` | 등록일, 수정일 |
| `tel`, `telname` | 전화번호, 전화번호명 |
| `homepage` | 홈페이지 |
| `firstimage`, `firstimage2`, `cpyrhtDivCd` | 대표 이미지 및 저작권 유형 |
| `addr1`, `addr2`, `zipcode` | 주소 |
| `mapx`, `mapy`, `mlevel` | 좌표 |
| `overview` | 개요 |
| `lDongRegnCd`, `lDongSignguCd` | 법정동 코드 |
| `lclsSystm1/2/3` | 신분류체계 |
| `areacode`, `sigungucode` | 미사용 항목. 법정동 시도/시군구 코드로 대체 예정 |
| `cat1`, `cat2`, `cat3` | 미사용 항목. 신분류체계 1/2/3Depth로 대체 예정 |

PARAVOCA 구현:

- `overview`, `homepage`, 좌표, 이미지, 법정동/분류 metadata의 authoritative source로 사용합니다.
- 목록 결과의 `areacode`와 상세 결과의 `lDongRegnCd`가 다르면 `lDongRegnCd`를 primary로 저장하고 discrepancy flag를 남깁니다.

## 11. `detailIntro2` 소개정보 조회

Endpoint:

```text
GET /detailIntro2
```

용도:

- 콘텐츠 타입별 운영 정보, 이용 조건, 주차, 문의, 시간, 요금 등을 조회합니다.
- QA와 상품 운영 가능성 판단의 핵심 evidence입니다.

요청 파라미터:

| 파라미터 | 필수 | 설명 |
|---|---:|---|
| 공통 파라미터 | 일부 | 공통 호출 규칙 참고 |
| `contentId` | Y | 콘텐츠 ID |
| `contentTypeId` | Y | 관광타입 ID |

공통 응답 필드:

| 필드 | 설명 |
|---|---|
| `contentid`, `contenttypeid` | 콘텐츠 ID, 관광타입 |

타입별 응답 필드:

| ContentTypeId | 타입 | 주요 필드 |
|---:|---|---|
| `12` | 관광지 | `accomcount`, `chkbabycarriage`, `chkcreditcard`, `chkpet`, `expagerange`, `expguide`, `heritage1`, `heritage2`, `heritage3`, `infocenter`, `opendate`, `parking`, `restdate`, `useseason`, `usetime` |
| `14` | 문화시설 | `accomcountculture`, `chkbabycarriageculture`, `chkcreditcardculture`, `chkpetculture`, `discountinfo`, `infocenterculture`, `parkingculture`, `parkingfee`, `restdateculture`, `usefee`, `usetimeculture`, `scale`, `spendtime` |
| `15` | 행사/공연/축제 | `agelimit`, `bookingplace`, `discountinfofestival`, `eventenddate`, `eventhomepage`, `eventplace`, `eventstartdate`, `festivalgrade`, `placeinfo`, `playtime`, `program`, `spendtimefestival`, `sponsor1`, `sponsor1tel`, `sponsor2`, `sponsor2tel`, `subevent`, `usetimefestival` |
| `25` | 여행코스 | `distance`, `infocentertourcourse`, `schedule`, `taketime`, `theme` |
| `28` | 레포츠 | `accomcountleports`, `chkbabycarriageleports`, `chkcreditcardleports`, `chkpetleports`, `expagerangeleports`, `infocenterleports`, `openperiod`, `parkingfeeleports`, `parkingleports`, `reservation`, `restdateleports`, `scaleleports`, `usefeeleports`, `usetimeleports` |
| `32` | 숙박 | `accomcountlodging`, `checkintime`, `checkouttime`, `chkcooking`, `foodplace`, `infocenterlodging`, `parkinglodging`, `pickup`, `roomcount`, `reservationlodging`, `reservationurl`, `roomtype`, `scalelodging`, `subfacility`, `barbecue`, `beauty`, `beverage`, `bicycle`, `campfire`, `fitness`, `karaoke`, `publicbath`, `publicpc`, `sauna`, `seminar`, `sports`, `refundregulation` |
| `38` | 쇼핑 | `chkbabycarriageshopping`, `chkcreditcardshopping`, `chkpetshopping`, `culturecenter`, `fairday`, `infocentershopping`, `opendateshopping`, `opentime`, `parkingshopping`, `restdateshopping`, `restroom`, `saleitem`, `saleitemcost`, `scaleshopping`, `shopguide` |
| `39` | 음식점 | `chkcreditcardfood`, `discountinfofood`, `firstmenu`, `infocenterfood`, `kidsfacility`, `opendatefood`, `opentimefood`, `packing`, `parkingfood`, `reservationfood`, `restdatefood`, `scalefood`, `seat`, `smoking`, `treatmenu`, `lcnsno` |

PARAVOCA 구현:

- Product/Marketing은 이 필드에 없는 가격, 운영시간, 가능 조건을 단정하면 안 됩니다.
- QA는 `usefee`, `usetime*`, `restdate*`, `reservation*`, `eventstartdate`, `eventenddate`, `chkpet*` 등을 근거 기반 검수 필드로 봅니다.

## 12. `detailInfo2` 반복정보 조회

Endpoint:

```text
GET /detailInfo2
```

용도:

- 콘텐츠 타입별 추가 상세 반복 정보를 조회합니다.
- 숙박은 객실 정보, 여행코스는 하위 코스 정보, 그 외 타입은 `infoname`/`infotext` 중심 반복 정보를 제공합니다.

요청 파라미터:

| 파라미터 | 필수 | 설명 |
|---|---:|---|
| 공통 파라미터 | 일부 | 공통 호출 규칙 참고 |
| `contentId` | Y | 콘텐츠 ID |
| `contentTypeId` | Y | 관광타입 ID |

응답 필드:

| 범위 | 필드 |
|---|---|
| 공통 | `contentid`, `contenttypeid` |
| 숙박/여행코스 제외 | `fldgubun`, `infoname`, `infotext`, `serialnum` |
| 여행코스 `25` | `subcontentid`, `subdetailalt`, `subdetailimg`, `subdetailoverview`, `subname`, `subnum` |
| 숙박 `32` | `roomcode`, `roomtitle`, `roomsize1`, `roomcount`, `roombasecount`, `roommaxcount`, `roomoffseasonminfee1`, `roomoffseasonminfee2`, `roompeakseasonminfee1`, `roompeakseasonminfee2`, `roomintro`, `roombathfacility`, `roombath`, `roomhometheater`, `roomaircondition`, `roomtv`, `roompc`, `roomcable`, `roominternet`, `roomrefrigerator`, `roomtoiletries`, `roomsofa`, `roomcook`, `roomtable`, `roomhairdryer`, `roomsize2`, `roomimg1`-`roomimg5`, `roomimg1alt`-`roomimg5alt`, `cpyrhtDivCd1`-`cpyrhtDivCd5` |

반복정보 유형 예시:

| 타입 | 반복정보 예시 |
|---|---|
| 관광지 | 입장료, 화장실, 관람료, 이용가능시설, 주차요금, 예약안내, 외국어안내서비스 |
| 문화시설 | 체험프로그램, 이용가능시설, 입장료, 관람료, 예약안내, 외국인 체험 가능 프로그램 |
| 행사/공연/축제 | 행사소개, 줄거리, 출연, 제작, 행사내용, 참가안내 |
| 레포츠 | 이용요금, 주요시설 |
| 쇼핑 | 제조유래, 구입방법안내, 입점브랜드, 세금환급방법, 체험안내, 강습안내 |

PARAVOCA 구현:

- 숙박 객실 가격 필드는 참고값일 수 있으므로 판매가격으로 확정하지 않습니다.
- `infoname`/`infotext`는 raw text 형태로 source document에 넣되, QA가 가격/시간/예약 관련 항목을 탐지할 수 있도록 structured summary를 별도로 만들면 좋습니다.

## 13. `detailImage2` 이미지정보 조회

Endpoint:

```text
GET /detailImage2
```

용도:

- 콘텐츠별 상세 이미지 URL과 저작권 유형을 조회합니다.
- 음식점 타입은 `imageYN=N`일 때 음식 메뉴 이미지 성격입니다.

요청 파라미터:

| 파라미터 | 필수 | 설명 |
|---|---:|---|
| 공통 파라미터 | 일부 | 공통 호출 규칙 참고 |
| `contentId` | Y | 콘텐츠 ID |
| `imageYN` | N | `Y`: 콘텐츠 이미지, `N`: 음식점 메뉴 이미지 |

응답 필드:

| 필드 | 설명 |
|---|---|
| `contentid` | 콘텐츠 ID |
| `imgname` | 이미지명 |
| `originimgurl` | 원본 이미지 URL |
| `smallimageurl` | 썸네일 이미지 URL |
| `serialnum` | 이미지 일련번호 |
| `cpyrhtDivCd` | 저작권 유형 |

PARAVOCA 구현:

- Evidence image candidates와 Poster Studio 참고 이미지 후보로 사용합니다.
- `cpyrhtDivCd=Type3`는 변경금지 조건이 있으므로 AI 이미지 편집/변형의 직접 소스로 쓰지 않도록 UI/QA에서 표시해야 합니다.

## 14. `areaBasedSyncList2` 관광정보 동기화 목록 조회

Endpoint:

```text
GET /areaBasedSyncList2
```

용도:

- 수정일과 표출 여부 기준으로 관광정보 변경 목록을 조회합니다.
- 운영 DB와 Chroma 색인의 증분 동기화에 사용합니다.

요청 파라미터:

| 파라미터 | 필수 | 설명 |
|---|---:|---|
| 공통 파라미터 | 일부 | 공통 호출 규칙 참고 |
| `showflag` | N | `1`: 표출, `0`: 비표출 |
| `modifiedtime` | N | 콘텐츠 변경일. 연도, 연월, 연월일 형식 가능 |
| `arrange` | N | 정렬 코드 |
| `contentTypeId` | N | 관광타입 |
| `lDongRegnCd`, `lDongSignguCd` | N | 법정동 코드 |
| `lclsSystm1/2/3` | N | 신분류체계 |
| `oldContentid` | N | 이전 콘텐츠 ID. DB 동기화 시 이전 key 조회용 |

응답 필드:

- 목록 공통 응답 필드.
- `oldContentid`: 이전 콘텐츠 ID. DB 저장 동기화 시 이전 key 조회 용도.
- `showflag`: 콘텐츠 표출 여부.

문서상 주의:

- 사용자가 제공한 v4.4 response schema excerpt의 `areaBasedSyncList2.cpyrhtDivCd` 설명에는 `필수요청파라메터가없음(NO_MANDATORY_REQUEST_PARAMETERS_ERROR)`라는 오류 코드 문구가 들어 있습니다. 동일 필드가 다른 목록 API에서 저작권 유형으로 쓰이므로 구현에서는 필드명 기준으로 저작권 유형 값으로 처리하되, 이 operation의 원문 설명은 오기 가능성으로 기록합니다.

PARAVOCA 구현:

- Phase 9.6의 필수 범위는 아니지만, 실제 서비스 전환 시 nightly sync/reindex의 핵심입니다.
- `showflag=0` 콘텐츠는 기존 evidence/source document를 비활성 처리해야 합니다.

## 15. `detailPetTour2` 반려동물 동반여행 정보 조회

Endpoint:

```text
GET /detailPetTour2
```

용도:

- 콘텐츠별 반려동물 동반 조건을 조회합니다.
- 반려동물 동반 상품 또는 QA 조건 검수에 사용합니다.

요청 파라미터:

| 파라미터 | 필수 | 설명 |
|---|---:|---|
| 공통 파라미터 | 일부 | 공통 호출 규칙 참고 |
| `contentid` | N | 콘텐츠 ID. 미입력 시 전체 반려동물 정보 조회 |

원문 표에는 `contentid`로 표기되어 있으나 예시 URL은 `contentId`를 사용합니다. 구현에서는 `contentId`를 우선 사용하고, 필요하면 `contentid` alias도 허용하는 방식이 안전합니다.

응답 필드:

| 필드 | 설명 |
|---|---|
| `contentid` | 콘텐츠 ID |
| `acmpyPsblCpam` | 동반 가능 동물 |
| `acmpyNeedMtr` | 동반 시 필요사항 |
| `acmpyTypeCd` | 동반 유형 |
| `etcAcmpyInfo` | 기타 동반 정보 |
| `relaAcdntRiskMtr` | 사고 대비사항 |
| `relaRntlPrdlst` | 관련 렌탈 품목 |
| `relaFrnshPrdlst` | 관련 비치 품목 |
| `relaPurcPrdlst` | 관련 구매 품목 |
| `relaPosesFclty` | 관련 구비 시설 |

PARAVOCA 구현:

- Phase 10 이후 Data Enrichment Agent에서 요청 테마가 반려동물일 때 선택 호출합니다.
- 반려동물 가능 여부는 조건부 표현으로만 생성해야 하며, 최종 운영자는 공식 안내를 확인해야 합니다.

## 사용하기로 한 API 중 이 response schema에 없는 범위

사용자가 제공한 response schema excerpt는 PARAVOCA가 현재 구현했거나 Phase 9.6에서 전환하려는 KorService2 operation을 모두 포함합니다.

포함된 현재/예정 KorService2 operation:

| 범위 | 포함된 operation |
|---|---|
| 현재 provider 구현 | `areaCode2`, `areaBasedList2`, `searchKeyword2`, `searchFestival2`, `searchStay2`, `detailCommon2`, `detailIntro2`, `detailInfo2`, `detailImage2`, `categoryCode2`, `locationBasedList2` |
| Phase 9.6 전환 예정 | `ldongCode2`, `lclsSystmCode2` |
| 향후 동기화/테마 후보 | `areaBasedSyncList2`, `detailPetTour2` |

다만 PARAVOCA 전체 데이터 보강 계획에는 KorService2가 아닌 KTO API도 포함되어 있습니다. 아래 API들은 이 문서의 response schema excerpt에 세부 endpoint/필드 명세가 없으므로, 구현 전 별도 Swagger/활용매뉴얼 확인이 필요합니다.

| API/source_family | 문서/코드상 쓰기로 한 범위 | 이 문서의 상태 |
|---|---|---|
| 한국관광공사 지역별 관광 자원 수요 API | 지역별 관광 서비스/문화 자원 수요 신호. `한국관광공사_국문 관광정보 서비스_GW`가 아니라 별도 수요지수/수요 신호 API입니다. | KorService2에는 미포함. 별도 [99_13_KTO_REGIONAL_TOURISM_DEMAND_SPEC.md](./99_13_KTO_REGIONAL_TOURISM_DEMAND_SPEC.md)에 정리 |
| `kto_photo_contest` 관광공모전 사진 수상작 정보 | `photoContestSearch`, `photoContestSync` 성격의 사진 후보/동기화 | 미포함 |
| `kto_wellness` 웰니스관광정보 | 키워드/지역/위치/상세/이미지 계열 웰니스 관광정보 | 미포함 |
| `kto_medical` 의료관광정보 | 의료관광 키워드 검색, 공통/소개/반복/의료관광 상세 | 미포함 |
| `kto_pet` 반려동물 동반여행 서비스 | 별도 서비스의 지역/위치 검색과 동반 조건 상세 | 미포함. KorService2 `detailPetTour2`와 혼동하지 말 것 |
| `kto_durunubi` 두루누비 정보 서비스_GW | 코스 목록, 길 목록, GPX/route asset | 미포함 |
| `kto_audio` 관광지 오디오 가이드정보_GW | 키워드/위치 검색, 오디오 가이드 상세 | 미포함 |
| `kto_eco` 생태 관광 정보_GW | 생태 관광 후보 조회와 상세 | 미포함 |
| `kto_tourism_photo` 관광사진 정보_GW | 관광사진 검색/동기화 | 미포함 |
| `kto_tourism_bigdata` 관광빅데이터 정보서비스_GW | 지역/기간별 방문자 수요 신호 | 미포함 |
| `kto_crowding_forecast` 관광지 집중률 방문자 추이 예측 정보 | 관광지 집중률 예측 신호 | 미포함 |
| `kto_related_places` 관광지별 연관 관광지 정보 | 지역/키워드 기반 연관 관광지 | 미포함 |

## 신분류체계 xlsx 요약

제공된 xlsx 파일의 핵심 시트:

```text
분류체계_관광타입맵핑
```

컬럼 구조:

| 컬럼 | 의미 |
|---|---|
| `A/B` | 대분류 코드/명 |
| `C/D` | 중분류 코드/명 |
| `E/F` | 소분류 코드/명 |
| `G/H/I` | 국문/다국어 관광타입 코드와 관광타입명 |
| `K/L/M` | 관광타입 코드표 보조 영역 |

확인 결과:

| ContentTypeId | 타입 | xlsx mapping 건수 |
|---:|---|---:|
| `12` | 관광지 | 105 |
| `14` | 문화시설 | 17 |
| `15` | 축제/공연/행사 | 20 |
| `25` | 여행코스 | 6 |
| `28` | 레포츠 | 47 |
| `32` | 숙박 | 11 |
| `38` | 쇼핑 | 13 |
| `39` | 음식점 | 21 |

운영 규칙:

- xlsx는 code seed로 사용할 수 있지만, live API `lclsSystmCode2?lclsSystmListYn=Y`를 canonical source로 둡니다.
- xlsx와 live API의 건수 차이는 sync 시 diff report로 남깁니다.
- 자연어 테마 매핑은 `lclsSystm1Nm`, `lclsSystm2Nm`, `lclsSystm3Nm`, alias keyword를 함께 색인해 retrieval로 찾습니다.

## PARAVOCA provider 전환 요구사항

현재 `backend/app/tools/tourism.py`는 다음을 개선해야 합니다.

1. `ldong_code()` 추가
   - `ldongCode2` 호출
   - 시도/시군구 전체 catalog caching 지원

2. `lcls_system_code()` 추가
   - `lclsSystmCode2` 호출
   - 전체 분류체계 catalog caching 지원

3. 기존 목록/search method 파라미터 전환
   - 기존: `region_code`, `areaCode`
   - 신규: `ldong_regn_cd`, `ldong_signgu_cd`
   - 분류: `lcls_systm_1`, `lcls_systm_2`, `lcls_systm_3`

4. `TourismItem` 정규화 확장
   - `legacy_area_code`: 응답 `areacode`
   - `legacy_sigungu_code`: 응답 `sigungucode`
   - `ldong_regn_cd`: 응답 `lDongRegnCd`
   - `ldong_signgu_cd`: 응답 `lDongSignguCd`
   - `lcls_systm_1/2/3`: 응답 `lclsSystm1/2/3`

5. RAG metadata 전환
   - `region_code` filter는 backward compatibility로 유지
   - primary filter는 `ldong_regn_cd`, `ldong_signgu_cd`
   - provider/model 변경처럼 metadata 기준 변경 후 reset reindex 필요

## 구현상 주의할 데이터 품질 문제

- 일부 legacy 응답에는 `areacode`가 비어 있고 `lDongRegnCd`만 있는 경우가 있습니다.
- 일부 목록 응답과 상세 응답의 지역 코드가 서로 다를 수 있습니다. 상세 `detailCommon2`를 우선합니다.
- 행사 검색은 날짜 필수입니다. 기간 없는 요청은 workflow에서 합리적인 기간을 정하거나 사용자 확인이 필요합니다.
- `detailIntro2`의 가격/시간/휴무 필드는 HTML fragment나 줄바꿈이 섞일 수 있습니다.
- 이미지 저작권 유형은 생성/변형/게시 가능 여부와 다릅니다. UI에서 별도 확인 대상입니다.
- API 문서는 v4.4지만 실제 운영 API는 예전 필드를 혼합해 반환합니다. parser는 양쪽 필드를 모두 받아야 합니다.
