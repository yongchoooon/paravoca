# D09. 한국관광공사 API Connectors

한국관광공사 MCP는 사용하지 않는다.
A05 baseline 수집과 A07A, A07A2, A07B~A07D 보강 lane은 모두 Ennoia API 커넥터로 구현한다.

Ennoia API 커넥터 URL에 `${serviceKey}`, `${keyword}` 같은 변수를 넣으면 변수 입력이 자동 생성된다.
공통 파라미터는 URL에 직접 포함한다.
HTTP 헤더와 바디는 사용하지 않는다.

공통 변수:

| 키 | 설명 | 필수 |
|---|---|---|
| serviceKey | 공공데이터포털 한국관광공사 서비스 인증키 | ON |
| numOfRows | 결과 수. URL에 고정해도 됨 | OFF |
| pageNo | 페이지. 기본 1 | OFF |

## 기존 run 일치성 점검 요약

기존 run에서 실제 핵심으로 쓰던 API와 현재 커넥터 일치성:

| API | 현재 상태 | 비고 |
|---|---|---|
| `areaBasedList2` | 일치 | A05A에서 contentTypeId 12/28 수집. 현재는 `arrange=Q`, `numOfRows=20`으로 편향 완화 |
| `searchKeyword2` | 일치 | A05B keyword 수집 |
| `searchFestival2` | 일치 | A05B festival 수집. `eventStartDate`가 있을 때만 호출 |
| `searchStay2` | 일치 | A05B stay 수집 |
| `detailCommon2` | 수정 필요 후 일치 | KorService2에서는 legacy YN 파라미터를 제거하고 `contentId`만 사용 |
| `detailIntro2` | 일치 | `contentId`, `contentTypeId` 사용 |
| `detailInfo2` | 일치 | `contentId`, `contentTypeId` 사용 |
| `detailImage2` | 수정 후 일치 | KorService2에서는 `subImageYN`을 제거하고 `contentId`, `imageYN`만 사용 |

보강 lane의 추가 API는 기존 run의 핵심 TourAPI 흐름은 아니며, 요청 theme/gap이 있을 때만 호출한다.
이 API들은 A07C/A07D에서 보조 신호로만 사용하고, 실패해도 A05/A07A 핵심 상품화 흐름을 막지 않는다.

## A05 Baseline 커넥터

### 1. 관광정보 지역기반 목록

CoreTourApiCollectorAgent에서 사용한다.

| 항목 | 입력값 |
|---|---|
| 이름 | 관광정보 지역기반 목록 |
| Method | GET |
| URL | `https://apis.data.go.kr/B551011/KorService2/areaBasedList2?serviceKey=${serviceKey}&numOfRows=${numOfRows}&pageNo=${pageNo}&MobileOS=ETC&MobileApp=PARAVOCAAX&_type=json&arrange=${arrange}&contentTypeId=${contentTypeId}&lDongRegnCd=${lDongRegnCd}&lDongSignguCd=${lDongSignguCd}` |

필수 변수:

| 키 | 설명 |
|---|---|
| lDongRegnCd | BaselineSearchPlanAgent 출력의 `ldong_regn_cd` |
| lDongSignguCd | BaselineSearchPlanAgent 출력의 `ldong_signgu_cd` |
| contentTypeId | 관광지 12 또는 레포츠 28 |
| arrange | `Q` |
| pageNo | `1` |
| numOfRows | `20` |

CoreTourApiCollectorAgent는 이 커넥터를 두 번 호출한다.
`arrange=A`, `pageNo=1`, `numOfRows=20` 고정은 제목순 첫 페이지 편향이 크므로 사용하지 않는다.

```text
contentTypeId=12, arrange=Q, pageNo=1, numOfRows=20
contentTypeId=28, arrange=Q, pageNo=1, numOfRows=20
```

정렬 코드 기준:
- `Q`: 대표 이미지 우선 + 수정일순. 이미지 없는 항목도 뒤쪽에 포함될 수 있으므로 이미지 필터가 아니라 정렬 편향 완화용으로 본다.

TourAPI 목록 정렬에는 랜덤 코드가 없으므로, Core 수집은 대표 이미지가 있고 최근 수정된 관광지 20개와 레포츠 20개를 가져오는 방식으로 제목순 첫 페이지 편향을 줄인다.
raw 최대치는 40개지만 지역 내 실제 결과 수, 중복, 부적합 후보 제외 때문에 최종 `core_candidates`는 40개보다 적을 수 있다.

### 2. 관광정보 키워드 검색

SupplementalTourApiCollectorAgent에서 지역 확정 시 기본 사용한다.

| 항목 | 입력값 |
|---|---|
| 이름 | 관광정보 키워드 검색 |
| Method | GET |
| URL | `https://apis.data.go.kr/B551011/KorService2/searchKeyword2?serviceKey=${serviceKey}&numOfRows=10&pageNo=1&MobileOS=ETC&MobileApp=PARAVOCAAX&_type=json&arrange=A&keyword=${keyword}&lDongRegnCd=${lDongRegnCd}&lDongSignguCd=${lDongSignguCd}` |

SupplementalTourApiCollectorAgent는 keyword_queries 중 최대 5개만 사용한다.
키워드 검색 결과는 content_id 중복 제거 후 최대 10개만 출력한다.
숙박/호텔/스테이 키워드는 keyword_queries에 넣지 않는다.
숙박은 `관광정보 숙박 검색`에서 처리한다.

### 3. 관광정보 축제 검색

SupplementalTourApiCollectorAgent에서 eventStartDate가 있을 때 사용한다.

| 항목 | 입력값 |
|---|---|
| 이름 | 관광정보 축제 검색 |
| Method | GET |
| URL | `https://apis.data.go.kr/B551011/KorService2/searchFestival2?serviceKey=${serviceKey}&numOfRows=10&pageNo=1&MobileOS=ETC&MobileApp=PARAVOCAAX&_type=json&arrange=A&eventStartDate=${eventStartDate}&eventEndDate=${eventEndDate}&lDongRegnCd=${lDongRegnCd}&lDongSignguCd=${lDongSignguCd}` |

eventStartDate가 없으면 SupplementalTourApiCollectorAgent는 이 커넥터를 호출하지 않는다.
축제/행사 의도가 있거나 "이번 달" 같은 상대 기간이 있으면 BaselineSearchPlanAgent가 eventStartDate/eventEndDate를 채워야 한다.
이때 기준 날짜는 Ennoia의 오늘 날짜 추가 기능으로 시스템 프롬프트 맨 위에 삽입되는 `### Current date is ...` 값이다.

### 4. 관광정보 숙박 검색

SupplementalTourApiCollectorAgent에서 지역 확정 시 기본 사용한다.

| 항목 | 입력값 |
|---|---|
| 이름 | 관광정보 숙박 검색 |
| Method | GET |
| URL | `https://apis.data.go.kr/B551011/KorService2/searchStay2?serviceKey=${serviceKey}&numOfRows=10&pageNo=1&MobileOS=ETC&MobileApp=PARAVOCAAX&_type=json&arrange=A&lDongRegnCd=${lDongRegnCd}&lDongSignguCd=${lDongSignguCd}` |

## A07A Detail 커넥터

### 5. 관광정보 공통상세

| 항목 | 입력값 |
|---|---|
| 이름 | 관광정보 공통상세 |
| Method | GET |
| URL | `https://apis.data.go.kr/B551011/KorService2/detailCommon2?serviceKey=${serviceKey}&MobileOS=ETC&MobileApp=PARAVOCAAX&_type=json&contentId=${contentId}&numOfRows=10&pageNo=1` |

주의:
`detailCommon2`에는 `defaultYN`, `firstImageYN`, `areacodeYN`, `catcodeYN`, `addrinfoYN`, `mapinfoYN`, `overviewYN`을 넣지 않는다.
현재 KorService2는 위 legacy YN 파라미터를 거부할 수 있으며, `INVALID_REQUEST_PARAMETER_ERROR(addrinfoYN)`가 나오면 이 URL을 아직 수정하지 않은 것이다.
공통상세 호출에는 `contentTypeId`도 넣지 않는다. `contentTypeId`는 소개정보/반복정보 호출에만 사용한다.

### 6. 관광정보 소개정보

| 항목 | 입력값 |
|---|---|
| 이름 | 관광정보 소개정보 |
| Method | GET |
| URL | `https://apis.data.go.kr/B551011/KorService2/detailIntro2?serviceKey=${serviceKey}&MobileOS=ETC&MobileApp=PARAVOCAAX&_type=json&contentId=${contentId}&contentTypeId=${contentTypeId}&numOfRows=5&pageNo=1` |

### 7. 관광정보 반복정보

| 항목 | 입력값 |
|---|---|
| 이름 | 관광정보 반복정보 |
| Method | GET |
| URL | `https://apis.data.go.kr/B551011/KorService2/detailInfo2?serviceKey=${serviceKey}&MobileOS=ETC&MobileApp=PARAVOCAAX&_type=json&contentId=${contentId}&contentTypeId=${contentTypeId}&numOfRows=5&pageNo=1` |

### 8. 관광정보 이미지정보

| 항목 | 입력값 |
|---|---|
| 이름 | 관광정보 이미지정보 |
| Method | GET |
| URL | `https://apis.data.go.kr/B551011/KorService2/detailImage2?serviceKey=${serviceKey}&MobileOS=ETC&MobileApp=PARAVOCAAX&_type=json&contentId=${contentId}&imageYN=Y&numOfRows=10&pageNo=1` |

A07A 연결 체크리스트:
- 위 4개 커넥터를 만든 뒤 아래처럼 나눠 연결한다.
  - `TourApiDetailEnrichmentAgent`: `관광정보 공통상세`, `관광정보 반복정보`
  - `TourApiIntroImageEnrichmentAgent`: `관광정보 소개정보`, `관광정보 이미지정보`
- 커넥터 이름은 프롬프트의 이름과 맞춘다: `관광정보 공통상세`, `관광정보 소개정보`, `관광정보 반복정보`, `관광정보 이미지정보`.
- 공통상세 변수는 `serviceKey`, `contentId`다.
- 소개정보/반복정보 변수는 `serviceKey`, `contentId`, `contentTypeId`다.
- 이미지정보 변수는 `serviceKey`, `contentId`다. `contentTypeId`와 `subImageYN`은 이미지정보 URL에 넣지 않는다.
- A07A 상세 커넥터의 `numOfRows`는 후보 개수 제한이 아니라 해당 `contentId` 내부 응답 row 수 제한이다. 기준은 `detailCommon2=10`, `detailInfo2=5`다.
- A07A2 상세 커넥터의 `numOfRows` 기준은 `detailIntro2=5`, `detailImage2=10`이다.
- `detailCommon2` 단독 테스트에서 `INVALID_REQUEST_PARAMETER_ERROR(addrinfoYN)`가 나오면 legacy YN 파라미터가 남아 있는 것이다.
- `contentId=126121` 단독 검증 기준으로 `detailCommon2`는 `resultCode=0000`, `overview`, `homepage=http://bisco.or.kr/yongdusanpark`를 반환한다.
- `contentId=126121`, `contentTypeId=12` 단독 검증 기준으로 `detailIntro2`는 `resultCode=0000`, `infocenter`, `restdate`, `usetime`, `parking`을 반환한다.
- 공식 홈페이지와 예약/안내 URL은 새 링크 전용 스키마가 아니라 A07A `fields_added`에 보존한다.
- URL성 필드의 1차 출처는 `detailCommon2.homepage`다.
- `detailIntro2`에도 contentTypeId별 URL성 필드가 있다. 행사/축제(15)는 `eventhomepage`, `bookingplace`, 레포츠(28)는 `reservation`, 숙박(32)은 `reservationlodging`, `reservationurl`, 음식점(39)은 `reservationfood`를 확인한다.
- API 값이 HTML anchor이면 `href` URL만 추출하고, 설명 문구와 URL이 섞인 값이면 실제 URL만 추출한다. `www.`로 시작하면 `https://`를 붙여 `fields_added`에 남긴다.
- 따라서 `detailCommon2` 또는 `detailIntro2`가 전체 contentId에서 `call_failed`로만 실패하고 `detailInfo2`/`detailImage2`는 일부 성공한다면 API URL 자체보다 Ennoia 노드의 커넥터 연결, 변수 매핑, 실패 원문 전달을 먼저 확인한다.
- `missing_detail_info`의 핵심은 `overview` 보강이므로 `detailCommon2`가 반드시 호출되어야 한다. `detailInfo2`만 성공하면 요금/시설 같은 보조 정보는 생길 수 있지만 overview gap은 해소되지 않는다.
- A05D CandidateMergeDedupeAgent가 이미 후보 수를 줄였으므로 A07A에는 별도 후보 개수 제한을 두지 않는다. 처리하지 못한 contentId 또는 호출하지 못한 API는 `skipped_calls` 또는 `failed_calls`에 남겨야 한다.
- A07A 단독 스모크 테스트는 `contentId=126508`, `contentTypeId=12`인 경복궁 1건과 `contentId=1277679`, `contentTypeId=12`인 부산타워 1건으로 시작한다. 정상 결과는 `failed_calls`에 `관광정보 공통상세` 실패가 없고 `enriched_items[0].fields_added`에 `detail_common=overview:`가 포함된 상태다.

## A07B Visual 커넥터

### 9. 관광사진 키워드 검색

| 항목 | 입력값 |
|---|---|
| 이름 | 관광사진 키워드 검색 |
| Method | GET |
| URL | `https://apis.data.go.kr/B551011/PhotoGalleryService1/gallerySearchList1?serviceKey=${serviceKey}&MobileOS=ETC&MobileApp=PARAVOCAAX&_type=json&keyword=${keyword}&numOfRows=6&pageNo=1` |

A07B 연결 체크리스트:
- `gallerySearchList1`은 keyword 1회 호출의 사진 결과 목록을 조회한다.
- `numOfRows=6&pageNo=1`은 keyword 1회 호출에서 반환되는 사진 행 수를 최대 6개로 제한한다.
- 여러 keyword를 호출하면 전체 사진 후보는 6개를 넘을 수 있으므로 A07B 출력과 A08 병합에서 `visual_assets` 전체를 다시 최대 6개로 제한한다.

## A07C 및 후속 실무 branch 보조 커넥터

### 10. 연관관광지 지역 검색

| 항목 | 입력값 |
|---|---|
| 이름 | 연관관광지 지역 검색 |
| Method | GET |
| URL | `https://apis.data.go.kr/B551011/TarRlteTarService1/areaBasedList1?serviceKey=${serviceKey}&MobileOS=ETC&MobileApp=PARAVOCAAX&_type=json&areaCd=${areaCd}&signguCd=${signguCd}&baseYm=${baseYm}&numOfRows=10&pageNo=1` |

이 커넥터는 `99_12_KTO_RELATED_PLACES_SPEC.md`의 `TarRlteTarService1/areaBasedList1` endpoint를 사용한다.
A07C RouteSignalEnrichmentAgent에서 지역 기반 주변 연계 후보를 넓게 확인할 때 사용한다.
`areaCd`는 필수이며, `signguCd`가 확인된 경우 함께 전달한다.
`baseYm`은 `202604`를 사용한다.

### 11. 연관관광지 키워드 검색

| 항목 | 입력값 |
|---|---|
| 이름 | 연관관광지 키워드 검색 |
| Method | GET |
| URL | `https://apis.data.go.kr/B551011/TarRlteTarService1/searchKeyword1?serviceKey=${serviceKey}&MobileOS=ETC&MobileApp=PARAVOCAAX&_type=json&areaCd=${areaCd}&signguCd=${signguCd}&keyword=${keyword}&baseYm=${baseYm}&numOfRows=10&pageNo=1` |

이 커넥터는 `99_12_KTO_RELATED_PLACES_SPEC.md`의 `TarRlteTarService1/searchKeyword1` endpoint를 사용한다.
선택 상품의 장소명, 핵심 관광지명, 또는 route_signal lane의 keyword를 넣어 확장 후보와 대체 후보를 찾는다.
이 endpoint는 호출 시 `areaCd`가 필수다.
후속 branch에서는 AreaCodeResolverAgent가 공식 관광지 시군구 코드표 기준으로 출력한 `areaCd`, `signguCd`를 사용한다.
resolver가 코드를 확인하지 못한 경우에는 호출하지 않고 스킵해야 한다.

### 12. 관광지 집중률 예측

OperationsManagerCrowdingRiskAnalystAgent에서 사용한다.

| 항목 | 입력값 |
|---|---|
| 이름 | 관광지 집중률 예측 |
| Method | GET |
| URL | `https://apis.data.go.kr/B551011/TatsCnctrRateService/tatsCnctrRatedList?serviceKey=${serviceKey}&MobileOS=ETC&MobileApp=PARAVOCAAX&_type=json&areaCd=${areaCd}&signguCd=${signguCd}&tAtsNm=${tAtsNm}&numOfRows=3&pageNo=1` |

응답 필드 기준:

| 필드 | 용도 |
|---|---|
| `cnctrRate` | 집중률 보조 신호 |
| `baseYmd` | 기준일 |
| `areaCd`, `areaNm` | 지역 코드/명 |
| `signguCd`, `signguNm` | 시군구 코드/명 |
| `tAtsNm` | 관광지명 |

주의:
- 관광지 집중률은 예측 기반 보조 지표다. 실제 현장 혼잡, 안전, 쾌적함을 보장하는 표현에 쓰지 않는다.
- `관광지 집중률 예측`은 `tAtsNm`을 함께 전달한다. `areaCd`, `signguCd`만으로 호출하면 같은 시군구의 가나다순 첫 관광지 결과가 섞일 수 있으므로 운영 체크리스트 근거로 쓰지 않는다.
- A22는 원 장소명을 먼저 호출하고 실패/미매칭일 때만 식별력 있는 fallback query를 최대 2개 추가한다. 일반 category 단어만 단독으로 넣는 query는 만들지 않는다.
- `numOfRows=3`, `pageNo=1`로 호출한다. 응답 행이 여러 개이면 A22가 오늘 날짜와 같은 `baseYmd`를 우선 선택하고, 없으면 오늘 이후 가장 가까운 날짜를 선택한다.
- A22는 Ennoia의 오늘 날짜 추가 기능을 켠다. 시스템 프롬프트의 `### Current date is ...` 값을 `YYYYMMDD`로 변환해 `baseYmd`와 비교한다.
- 명세 문서 `99_11_KTO_CROWDING_FORECAST_SPEC.md`는 요청 파라미터 표가 불완전하므로, 커넥터 생성 후 data.go.kr 미리보기에서 `areaCd`, `signguCd`, paging 파라미터 동작을 단독 테스트한다.
- 테스트 응답이 요청 지역과 무관한 전국 결과처럼 보이면 지역 파라미터가 적용되지 않은 것이므로 커넥터 URL을 재확인한다.
- `관광지 집중률 예측`의 `areaCd`, `signguCd`는 TourAPI 국문 관광정보의 legacy `area_code`, `sigungu_code`가 아니다.
- 공식 코드표 `한국관광공사_OpenAPI_관광지_시군구_코드정보_v1.0.xlsx` 기준으로 부산광역시 중구는 `areaCd=26`, `signguCd=26110`이다.
- `area_code=6`, `sigungu_code=15`는 부산 중구의 관광정보 API 코드일 수 있으나, `관광지 집중률 예측` API에는 사용하지 않는다.

## A18~A28 후속 실무 branch 커넥터

후속 branch는 기존 여행 상품 추천 branch에서 저장한 상품 산출물을 재사용한다.
API 커넥터도 새로 중복 생성하지 말고 아래 커넥터를 Agent에 연결한다.

| Agent | 연결할 커넥터 | 호출 목적 |
|---|---|---|
| A18 ProductPlannerRelatedRouteAnalystAgent | 연관관광지 키워드 검색 | 선택 상품의 확장 후보, 선택 장소, 대체 장소 탐색 |
| A22 OperationsManagerCrowdingRiskAnalystAgent | 관광지 집중률 예측 | 운영 체크리스트의 혼잡 리스크 보조 신호 |
| A25 MarketingStrategistVisualSignalAgent | 관광사진 키워드 검색 | 상세페이지, 블로그, SNS 시각 소재 후보 탐색 |
| A28R NotionPagePayloadBuilderAgent | 없음 | 저장할 사용자-facing Markdown과 Notion 요청 payload 정리 |
| A28 NotionPagePublishAgent | Notion 페이지 생성 | A28R payload로 Notion 페이지 생성 |

Ennoia API 커넥터 생성 방식:

1. Method는 모두 `GET`으로 둔다.
2. URL에는 위 표의 URL을 그대로 넣고 `${serviceKey}`, `${areaCd}`, `${signguCd}`, `${keyword}`, `${baseYm}`, `${tAtsNm}` 변수를 필요한 커넥터에만 사용한다.
3. HTTP Header와 Body는 비워둔다.
4. 공통 파라미터 `MobileOS=ETC`, `MobileApp=PARAVOCAAX`, `_type=json`, `numOfRows`, `pageNo`는 URL에 직접 포함한다.
5. `serviceKey`는 필수 변수로 설정한다.
6. A18/A22의 `areaCd`, `signguCd`는 branch 앞의 AreaCodeResolverAgent가 공식 관광지 시군구 코드표 기준으로 채운 값을 사용한다.
7. A25의 `관광사진 키워드 검색`은 `areaCd`, `signguCd` 없이 `keyword`만 사용한다.
8. `baseYm`, `keyword`, `tAtsNm`은 Agent가 호출할 때 채우는 변수다.
9. A18의 `연관관광지 키워드 검색` `baseYm`은 항상 `202604`로 고정한다.
10. `연관관광지 키워드 검색`은 resolver 출력의 `areaCd`가 없으면 호출하지 않는다.
11. `관광지 집중률 예측`은 공식 관광지 시군구 코드표 기준 `areaCd`, `signguCd`와 선택 상품 장소명 `tAtsNm`을 사용한다. 부산광역시 중구 예시는 `areaCd=26`, `signguCd=26110`이다. 원 장소명으로 결과가 없으면 A22가 고유 지명 중심 fallback `tAtsNm`을 소량 추가할 수 있다.
12. 후속 Agent는 각 API의 코드 체계를 혼용하지 않는다. TourAPI legacy `area_code`, `sigungu_code`를 후속 실무 branch의 `areaCd`, `signguCd`로 넣지 않는다.
13. 응답 타임아웃을 고려해 후속 Agent는 각 커넥터를 소수 회만 호출한다. A18은 장소명 기준 최대 3회, A22는 주요 장소 원문 호출을 우선하고 전체 fallback 호출을 최대 6회로 제한하며, A25는 장소명 또는 테마 keyword 기준 최대 3회 호출한다. A25의 `관광사진 키워드 검색`은 `numOfRows=6&pageNo=1`로 제한한다.

### 13. Notion 페이지 생성

NotionPagePublishAgent에서 사용한다. 저장 문서 선택과 payload 구성은 A28R NotionPagePayloadBuilderAgent가 먼저 수행한다.

| 항목 | 입력값 |
|---|---|
| 이름 | Notion 페이지 생성 |
| Method | POST |
| URL | `https://notion-api.yourdomain.com/notion/pages` |
| Header | `Authorization: Bearer ${NOTION_BRIDGE_TOKEN}` |
| Body | 필수 `title`, `markdown`, `proposal_type` 기준으로 구성 |

Body schema:

```json
{
  "type": "object",
  "properties": {
    "title": {
      "type": "string",
      "description": "Notion page title, max 120 characters."
    },
    "markdown": {
      "type": "string",
      "description": "Full Markdown content selected by NotionPagePayloadBuilderAgent."
    },
    "proposal_type": {
      "type": "string",
      "description": "Notion bridge classification metadata. One of travel_recommendation, poster_result, product_planner, operations, marketing. This is an API body field, not a workflow Set state."
    }
  },
  "required": [
    "title",
    "markdown",
    "proposal_type"
  ],
  "additionalProperties": false
}
```

요청 예시:

```json
{
  "title": "PARAVOCA 운영 체크리스트",
  "markdown": "## 1. 운영 리스크 요약\n...",
  "proposal_type": "operations"
}
```

응답 예시:

```json
{
  "page_url": "https://www.notion.so/...",
  "page_id": "..."
}
```

주의:
- Ennoia 커넥터의 schema에는 위 Body schema를 넣고, 실제 호출 body에는 `title`, `markdown`, `proposal_type` 값을 담은 payload를 보낸다.
- 실제 호출 body에 `type`, `properties`, `required`, `additionalProperties` 같은 schema 객체를 보내지 않는다.
- URL은 실제 Cloudflare Tunnel public hostname으로 바꾼다.
- Header의 Bearer Token은 notion-bridge 서버의 `NOTION_BRIDGE_TOKEN`과 같아야 한다.
- A28R은 `title`, `markdown`, `proposal_type` payload를 만들고, A28은 응답의 `page_url`만 사용자에게 출력한다.
- `title`, `markdown`, `proposal_type`은 모두 필수 body 필드다.
- `markdown`에는 선택한 최종 Markdown 저장 state 원문을 그대로 넣고, API 커넥터 단계에서 요약하거나 재작성하지 않는다.
- 정확한 저장을 위해 A28R/A28이 긴 본문을 다시 생성하게 하지 말고, A28R의 `markdown` 필드는 `proposal_output`, `poster_output`, `product_planner_proposal_output`, `operations_manager_proposal_output`, `marketing_strategist_proposal_output` 중 선택된 state 원문에 직접 매핑한다.

## A07D Theme 커넥터

### 14. 웰니스 키워드 검색

| 항목 | 입력값 |
|---|---|
| 이름 | 웰니스 키워드 검색 |
| Method | GET |
| URL | `https://apis.data.go.kr/B551011/WellnessTursmService/searchKeyword?serviceKey=${serviceKey}&MobileOS=ETC&MobileApp=PARAVOCAAX&_type=json&keyword=${keyword}&langDivCd=KOR&lDongRegnCd=${lDongRegnCd}&lDongSignguCd=${lDongSignguCd}&arrange=C&numOfRows=10&pageNo=1` |

`response.header.resultCode=0000`이면서 `items=""`, `totalCount=0`이면 커넥터 실패가 아니라 해당 조건의 웰니스 후보가 없는 정상 empty 응답이다.
A07D는 이 경우 `failed_calls`가 아니라 빈 theme 후보 또는 skipped/empty 결과로 처리한다.
웰니스 API 명세상 item에는 `homepage`가 있을 수 있으므로, 응답에 값이 있으면 A07D `theme_candidates[].raw_reference`에 `homepage: URL` 형식으로 남긴다.

### 15. 반려동물 동반 키워드 검색

| 항목 | 입력값 |
|---|---|
| 이름 | 반려동물 동반 키워드 검색 |
| Method | GET |
| URL | `https://apis.data.go.kr/B551011/KorPetTourService2/searchKeyword2?serviceKey=${serviceKey}&MobileOS=ETC&MobileApp=PARAVOCAAX&_type=json&keyword=${keyword}&lDongRegnCd=${lDongRegnCd}&lDongSignguCd=${lDongSignguCd}&arrange=C&numOfRows=10&pageNo=1` |

### 16. 반려동물 동반 상세

| 항목 | 입력값 |
|---|---|
| 이름 | 반려동물 동반 상세 |
| Method | GET |
| URL | `https://apis.data.go.kr/B551011/KorPetTourService2/detailPetTour2?serviceKey=${serviceKey}&MobileOS=ETC&MobileApp=PARAVOCAAX&_type=json&contentId=${contentId}&numOfRows=10&pageNo=1` |

반려동물 동반 API의 `detailCommon2`/상세 응답에도 `homepage`가 있을 수 있으므로, 응답에 값이 있으면 A07D `theme_candidates[].raw_reference`에 `homepage: URL` 형식으로 남긴다.
테마 계열 응답의 `eventhomepage`, `reservationurl` 같은 URL성 필드도 `raw_reference`에 원래 필드명으로 보존한다.

### 17. 오디오 스토리 검색

| 항목 | 입력값 |
|---|---|
| 이름 | 오디오 스토리 검색 |
| Method | GET |
| URL | `https://apis.data.go.kr/B551011/Odii/storySearchList?serviceKey=${serviceKey}&MobileOS=ETC&MobileApp=PARAVOCAAX&_type=json&keyword=${keyword}&langCode=ko&numOfRows=10&pageNo=1` |

### 18. 오디오 테마 검색

| 항목 | 입력값 |
|---|---|
| 이름 | 오디오 테마 검색 |
| Method | GET |
| URL | `https://apis.data.go.kr/B551011/Odii/themeSearchList?serviceKey=${serviceKey}&MobileOS=ETC&MobileApp=PARAVOCAAX&_type=json&keyword=${keyword}&langCode=ko&numOfRows=10&pageNo=1` |

## 사용 원칙

- API 키는 각 커넥터의 `serviceKey` 변수에 넣는다.
- API 응답 전체 raw를 다음 Agent 출력에 그대로 복사하지 않는다.
- A05는 `candidate_pool_summary`를 만들지 않는다.
- A06 DataGapProfilerAgent, A07 ApiCapabilityRouterAgent, A08 EnrichmentResultMergeAgent는 API를 호출하지 않는다.
- A07A, A07A2, A07B~A07D만 자기 lane의 API 커넥터를 호출한다.
- A08에는 API 커넥터를 연결하지 않는다. A08은 A07A, A07A2, A07B~A07D 결과를 병합만 한다.
- Route/signal 및 A18/A22 후속 실무 branch에서 `areaCd`, `signguCd`가 없으면 해당 API는 호출하지 않고 failed_calls 또는 skipped_calls에 남긴다.
- `lDongRegnCd`, `lDongSignguCd`를 legacy area/sigungu code로 변환해 쓰지 않는다.

## 커넥터 단독 테스트 기준

커넥터 생성 후 아래 최소 입력으로 한 번씩 테스트한다.
정상 기준은 `response.header.resultCode`가 `0000`이거나, 데이터가 없어도 API 레벨 오류가 아닌 정상 empty 응답이어야 한다.

| 커넥터 | 최소 테스트 입력 |
|---|---|
| 관광정보 지역기반 목록 | `lDongRegnCd=26`, `lDongSignguCd=200`, `contentTypeId=12`, `arrange=Q`, `pageNo=1`, `numOfRows=3` |
| 관광정보 키워드 검색 | `keyword=태종대`, `lDongRegnCd=26`, `lDongSignguCd=200` |
| 관광정보 축제 검색 | `eventStartDate=20260601`, `eventEndDate=20260630`, `lDongRegnCd=26`, `lDongSignguCd=200` |
| 관광정보 숙박 검색 | `lDongRegnCd=26`, `lDongSignguCd=200` |
| 관광정보 공통상세 | `contentId=126658` |
| 관광정보 소개정보 | `contentId=126658`, `contentTypeId=12` |
| 관광정보 반복정보 | `contentId=126658`, `contentTypeId=12` |
| 관광정보 이미지정보 | `contentId=126658` |
| 관광사진 키워드 검색 | `keyword=태종대` |
| 연관관광지 지역 검색 | `areaCd=26`, `signguCd=26110`, `baseYm=202604` |
| 연관관광지 키워드 검색 | `areaCd=26`, `signguCd=26110`, `keyword=태종대`, `baseYm=202604` |
| 관광지 집중률 예측 | `areaCd=26`, `signguCd=26110`, `tAtsNm=자갈치 크루즈`, `numOfRows=3`, `pageNo=1` |
| 웰니스 키워드 검색 | `keyword=부산`, `lDongRegnCd=26`, `lDongSignguCd=200` |
| 반려동물 동반 키워드 검색 | `keyword=반려`, `lDongRegnCd=26`, `lDongSignguCd=200` |
| 반려동물 동반 상세 | 반려동물 키워드 검색에서 나온 `contentId` |
| 오디오 스토리 검색 | `keyword=태종대` |
| 오디오 테마 검색 | `keyword=태종대` |

주의:
- `resultCode=10`은 대체로 파라미터명 또는 허용되지 않는 파라미터 문제다.
- `INVALID_REQUEST_PARAMETER_ERROR(addrinfoYN)`은 `detailCommon2`에 legacy YN 파라미터가 남아 있다는 뜻이다.
- 데이터가 없는 empty 응답은 connector 실패가 아니다. 해당 Agent 출력에서는 `no_items` 또는 `empty_response`로 기록한다.
