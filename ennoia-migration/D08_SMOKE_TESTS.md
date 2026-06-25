# D08. Smoke Tests

## 목적

Ennoia 캔버스가 최소 분기까지 정상 동작하는지 확인한다.
현재 1차 검증 범위는 PreflightValidationAgent부터 GeoResolverAgent 뒤 if/else까지다.
2차 검증 범위는 A05 계열 baseline 수집 체인이다.
3차 검증 범위는 A06~A08 보강 라우팅과 API 커넥터 실행 체인이다.
4차 검증 범위는 Classify 분기와 A15/A16/A17 포스터 생성 branch다.
5차 검증 범위는 Classify 후속 실무 branch와 A18~A28이다.

## 확인할 연결

```text
Start
→ Classify Request Type
  - 여행 상품 추천해줘
  - 그 내용으로 포스터 만들어줘
  - 판매용 상품 기획서 만들어줘
	  - 운영 체크리스트 만들어줘
	  - 마케팅 패키지 만들어줘
	  - 노션 페이지로 만들어줘
→ A00 PreflightValidationAgent
→ If/else: ${preflight_validation.last_output.supported} == true
→ A02 PlannerAgent
→ A03 GeoResolverAgent
→ If/else: ${geo_resolution.last_output.geo_resolved} == true
→ A05 BaselineSearchPlanAgent
→ A05A CoreTourApiCollectorAgent
→ A05B SupplementalTourApiCollectorAgent
→ A05D CandidateMergeDedupeAgent
→ A06 DataGapProfilerAgent
→ If/else: ${data_gap_profile.last_output.enrichment_needed} == true
→ A07 ApiCapabilityRouterAgent
→ A07A TourApiDetailEnrichmentAgent
→ A07A2 TourApiIntroImageEnrichmentAgent
→ A07B VisualDataEnrichmentAgent
→ A07C RouteSignalEnrichmentAgent
→ A07D ThemeDataEnrichmentAgent
→ A08 EnrichmentResultMergeAgent
```

## 필수 테스트 케이스

| 입력 | 기대 결과 | 통과 기준 |
|---|---|---|
| `부산 영도에서 2030 커플 대상으로 반나절 관광상품 3개 만들어줘` | 정상 지역 확정 | `GeoResolverAgent.geo_resolved == true` |
| `대청도에서 가족 대상 관광상품 3개 만들어줘` | 섬/세부 지명을 상위 시군구로 확정 | GeoResolverAgent가 인천광역시 옹진군으로 확정하고 `geo_resolved == true` |
| `충청도에서 웰니스 숙박 연계 여행 상품 3개 추천해줘` | 광역권 복수 지역 확정 | GeoResolverAgent가 충청북도와 충청남도를 모두 `resolved_locations`에 넣고 `geo_resolved == true` |
| `중구에서 가족 대상 관광상품 3개 만들어줘` | 모호 지역 차단 | `GeoResolverAgent.geo_resolved == false` |
| `광주에서 가족 대상 관광상품 3개 만들어줘` | 모호 지역 차단 | `GeoResolverAgent.geo_resolved == false` |
| `부산 영도에서 관광상품 6개 만들어줘` | 상품 개수 제한 | `PreflightValidationAgent.supported == false`, `reason_code == "product_count_exceeds_limit"` |

## 현재 통과 확인

### 중구

PlannerAgent는 `region`을 `중구`로 유지해야 한다.
PlannerAgent가 `서울특별시 중구` 같은 가정을 만들면 실패다.

GeoResolverAgent는 아래처럼 unresolved를 반환해야 한다.

```text
geo_scope.status = unresolved
resolved_locations = []
clarification_candidates = 후보 예시 배열
center.lat = null
center.lng = null
confidence = low
geo_resolved = false
```

Geo if/else는 Else 경로로 가야 한다.

### 광주

GeoResolverAgent는 광주광역시와 경기도 광주시 중 하나를 임의로 고르면 안 된다.
Geo if/else는 Else 경로로 가야 한다.

### 대청도

GeoResolverAgent는 `대청도`를 인천광역시 옹진군으로 확정해야 한다.

### 충청도

GeoResolverAgent는 `충청도`를 unresolved로 보내면 안 된다.
`충청도`는 충청북도와 충청남도를 함께 의미하는 광역권 표현으로 처리한다.

```text
geo_scope.status = resolved
resolved_locations includes 충청북도(ldong_regn_cd=43)
resolved_locations includes 충청남도(ldong_regn_cd=44)
geo_resolved = true
clarification_candidates = []
```
`대청도`는 후보 행의 정식 시군구명이 아니라 세부 섬 지명이므로 `resolved_locations[].sub_area_terms`와 `keywords`에 남긴다.

```text
geo_scope.status = resolved
geo_resolved = true
resolved_locations[0].name = 인천광역시 옹진군
resolved_locations[0].ldong_regn_cd = 28
resolved_locations[0].ldong_signgu_cd = 720
resolved_locations[0].sub_area_terms includes 대청도
geo_scope.status = resolved
```

## 여기서 짚고 넘어갈 것

1. Preflight 분기는 정상이다.
2. PlannerAgent는 지역 확정을 하지 않아야 한다.
3. GeoResolverAgent는 모호 지역을 대표값으로 확정하지 않아야 한다.
4. StatusAgent는 만들지 않고 if/else에서 `json_schema` structured output 필드를 직접 비교한다.
5. `A03_GEO_RESOLVER_AGENT.md` 시스템 메시지 안에 `TourAPI_법정동_후보` 전체 목록이 들어 있다.
6. GeoResolverAgent는 이 후보 목록 안에서만 지역을 확정하고, 모호하면 unresolved로 보낸다.

## 다음 단계로 넘어가기 전 체크

- `${preflight_validation.last_output.supported} == true` 조건이 If 경로로 간다.
- `${geo_resolution.last_output.geo_resolved} == true` 조건이 확정 지역만 If 경로로 보낸다.
- `중구`, `광주`는 Else 경로로 간다.
- `A02_PLANNER_AGENT.md`, `A03_GEO_RESOLVER_AGENT.md` 최신 프롬프트가 Ennoia 화면에 반영되어 있다.
- GeoResolverAgent에는 문서 폴더와 한국관광공사 API 커넥터가 연결되어 있지 않다.

## A05 계열 테스트

| 입력 | 기대 결과 |
|---|---|
| `부산광역시 중구에서 가족 대상 여행 상품 3개 추천해줘` | A05A가 area 12/28을 수집하고 A05D가 최대 15개 source_items 출력 |
| `대청도에서 가족 대상 관광상품 3개 만들어줘` | A05B가 대청도 keyword 검색을 실행하고 A05D source_items가 인천광역시 옹진군 맥락으로 제한 |
| `충청도에서 웰니스 숙박 연계 여행 상품 3개 추천해줘` | A05A/A05B가 충청북도와 충청남도 각각에 대해 API를 호출하고, A05D가 두 지역 후보를 모두 유지 가능 |
| `부산에서 이번 달 축제 중심 여행 상품 3개 추천해줘` | A05가 `### Current date is ...` 기준 eventStartDate/eventEndDate를 만들고 A05B가 축제 검색 실행 |
| `부산에서 1박 2일 가족 여행 상품 3개 추천해줘` | A05B가 숙박 검색을 실행하고 stay 후보를 supplemental_candidates에 포함 |

## A06~A08 계열 테스트

| 입력 | 기대 결과 |
|---|---|
| `부산광역시 중구에서 가족 대상 여행 상품 3개 추천해줘` | A06이 missing_detail_info 또는 missing_operating_hours 계열 gap을 만들고 `route_status = "ENRICHMENT_NEEDED"` 출력 |
| `부산광역시 중구에서 1박 2일 가족 여행 상품 3개 추천해줘` | A07 route에 tourapi_detail이 포함되고, A07A가 A05D 이후 후보에 대해 보강을 시도. missing_detail_info가 있으면 `관광정보 공통상세`가 1순위로 호출 |
| `서울특별시 종로구에서 역사 문화 여행 상품 3개 추천해줘` | A06 gap의 `related_gap_types`에 `missing_image_asset`이 있으면 A07 route에 visual_data도 포함되고, call_agents에 `VisualDataEnrichmentAgent`가 포함되어야 함 |
| `부산광역시 중구에서 반려동물 동반 여행 상품 3개 추천해줘` | A07 route에 theme_data가 포함되고 A07D가 반려동물 API 커넥터 호출 |
| `부산광역시 중구에서 반려동물 동반 가족 여행 상품 3개 추천해줘` | A07 route의 call_agents에 tourapi_detail, visual_data, theme_data가 함께 있으면 A07A, A07B, A07D가 모두 실행되고 A08의 coverage_by_lane에서 세 lane이 `not_run`이 아니어야 함 |
| `부산광역시 중구에서 오디오 해설 중심 여행 상품 3개 추천해줘` | A07 route에 theme_data가 포함되고 A07D가 오디오 스토리/테마 검색 호출 |
| `부산광역시 중구에서 주변 연계 중심 여행 상품 3개 추천해줘` | A07 route에 route_signal이 포함되고 A07C가 `연관관광지 지역 검색`, `연관관광지 키워드 검색` API 커넥터를 호출 대상으로 판단 |

A08 검증 기준:

- A08에는 API 커넥터를 연결하지 않는다.
- A08은 A07A, A07A2, A07B~A07D의 `lane_enrichment` 결과만 병합한다.
- 실패한 API는 `failed_calls`에 남긴다.
- 처리하지 못한 contentId 또는 호출하지 못한 API는 `skipped_calls` 또는 `failed_calls`에 남긴다.
- A07B에서 관광사진 키워드 검색 결과가 0건이면 실패가 아니므로 `failed_calls`가 아니라 `skipped_calls`에 `reason=no_items`로 남긴다.
- `failed_calls`는 가능하면 `resultCode`, `resultMsg`, invalid parameter 이름까지 포함해야 한다. 모든 항목이 단순 `reason=call_failed`로만 나오면 커넥터 URL/변수 매핑을 다시 확인한다.
- A07A의 `failed_calls`에 `reason=call_failed`만 단독으로 있는 항목이 대량 발생하면 실패로 본다. 구체 오류가 없으면 `connector_invocation_unverified` 또는 `connector_mapping_suspect`로 원인을 좁혀야 한다.
- `관광정보 공통상세` 또는 `관광정보 소개정보`가 전체 contentId에서 실패하지만 `관광정보 반복정보`나 `관광정보 이미지정보`가 일부 성공하면 데이터 부재가 아니라 해당 커넥터 URL/변수/노드 연결 문제로 보고 커넥터 설정을 재검증한다.
- 응답 raw 전체를 복사하지 않고 `enriched_items`, `visual_assets`, `route_signals`, `theme_candidates`로 줄여서 출력한다.
- A07A/A08의 `enriched_items[].images`와 A07B/A08의 `visual_assets`는 각각 최대 6개만 출력한다.
- A07A 상세 커넥터의 `numOfRows`는 후보 개수 제한이 아니라 해당 `contentId` 내부 응답 row 수 제한이다. 기준은 `detailCommon2=10`, `detailInfo2=5`다.
- A07A2 상세 커넥터의 `numOfRows` 기준은 `detailIntro2=5`, `detailImage2=10`이다.
- A07B의 `관광사진 키워드 검색` 커넥터는 keyword별 사진 목록을 `numOfRows=6&pageNo=1`로 요청하고, 여러 keyword 호출 후에도 최종 `visual_assets`는 최대 6개만 남긴다.
- A11은 PlannerAgent의 normalized_request.product_count만큼 `product_ideas`를 출력해야 한다. 요청이 “여행 상품 3개”이면 A11의 `product_ideas`도 3개여야 한다.
- A11은 evidence_cards가 1~2개뿐이라는 이유로 상품 수를 줄이지 않는다. 확인된 장소명, productization_advice, opportunity_areas, target_insights를 사용해 서로 다른 콘셉트의 상품을 보수적으로 구성한다.
- A11은 홈페이지 URL 또는 예약 URL이 없다는 이유로 상품 후보를 제외하거나 상품 수를 줄이지 않는다.
- A14 최종 응답은 단순 코스 추천이 아니라 상품별 세일즈 포인트, FAQ, SNS 문구/해시태그, 판매 실험, 게시 전 확인사항이 포함된 여행 상품 제안서여야 한다.
- 요청이 “여행 상품 3개”이면 A14 최종 응답도 3개 상품을 출력해야 한다. A11이 상품 수를 맞추는 것이 1차 책임이며, 중간 ProductManagerAgent가 부족하게 만들었을 때만 A14가 확인된 후보와 보강 정보를 사용해 보수적으로 채운다.
- A14 최종 응답에는 `ev-001`, `ev-004` 같은 내부 evidence id를 그대로 출력하지 않는다. 근거는 출처 요약 또는 확인된 정보 요약으로 표시한다.
- A14 최종 응답은 앞선 Agent 출력에 공식 홈페이지, 예약 페이지, 안내 페이지 등 실제 URL이 있을 때 HTML `a` 태그 버튼으로 관련 링크를 제공한다. URL이 없으면 관련 링크를 추측해서 만들지 않는다.
- A14는 URL이 없는 상품도 최종 추천에 유지한다. URL이 없으면 해당 상품의 “관련 링크” 섹션만 생략한다.
- A07A/A08 `fields_added`에 `detail_common=homepage:`, `detail_intro=eventhomepage:`, `detail_intro=reservationurl:` 같은 URL성 항목이 있으면 A14 최종 응답의 해당 상품에 HTML 링크 버튼이 있어야 한다.
- SourceDocument/RAG 근거에 `field=홈페이지; value=...; source=detailCommon2` 형태가 있으면 A14는 그 URL도 관련 링크 후보로 사용한다.
- A07D `theme_candidates[].raw_reference`에 웰니스/반려동물 API에서 온 `homepage:`, `eventhomepage:`, `reservationurl:` 항목이 있으면 A14 최종 응답의 해당 상품에 HTML 링크 버튼이 있어야 한다.
- A14 상품 이미지 HTML은 각 `img`를 같은 원본 이미지 URL의 `a` 태그로 감싸고, 클릭 시 새 탭에서 원본 이미지를 열 수 있어야 한다.
- A14 상품 본문에서 `한 줄 소개`, `추천 대상`, `상품 콘셉트`, `구성 장소`, `추천 동선`, `확인된 핵심 정보`, `관련 링크`, `왜 추천하는지`, `판매 실행 정보`는 `**제목**:` 형식이 아니라 `### 제목` 형식이어야 한다.
- A14의 FAQ 표 안에서 답변은 `- A:`가 아니라 `→ A:`로 표기한다.
- `www.`로 시작하는 홈페이지 값은 A14 버튼의 `href`에서 `https://`가 붙어야 한다.
- `<a href="...">...</a>` 형태나 `해운대 문화관광 http://...`처럼 설명 문구와 URL이 섞인 홈페이지 값도 A14 버튼의 실제 `href`로 추출되어야 한다.
- A14 성공 응답 마지막에는 `# 앞으로 가능한 것` 아래 `## 1. AI 포스터 만들기` 안내와 스타일 선택 예시가 있어야 한다.
- A14 성공 응답 마지막에는 `## 2. 판매용 상품 기획서 만들기`, `## 3. 운영 체크리스트 만들기`, `## 4. 마케팅 패키지 만들기`가 있어야 한다.
- A14의 2번, 3번, 4번 후속 기능 안내에는 각각 예시 요청이 3개씩 있어야 한다.

## 포스터 branch 테스트

| 입력 | 전제 | 기대 결과 |
|---|---|---|
| `3번 상품으로 포스터 만들어줘.` | 직전 여행 상품 추천 run에서 3개 상품이 생성되어 있음 | Classify가 포스터 branch로 보내고 A15가 `status=ready`, `selected_product_number=3`, `style_preset=editorial_travel` 출력 |
| `3번 상품으로 포스터 만들어줘. 스타일은 미니멀 이벤트 포스터로 하고, 한 줄 소개, 추천 대상, 구성 장소, 추천 동선, 판매/홍보 문구, SNS 홍보안, FAQ 초안을 포함해줘.` | 직전 여행 상품 추천 run에서 3개 상품이 생성되어 있음 | A15의 `style_preset=minimal_event`, `selected_sections`에 사용자가 명시한 항목이 반영되고 FAQ는 2~3개 이내 |
| `3번 상품으로 포스터 만들어줘. 유용한 정보 중심으로 알아서 구성해줘.` | 직전 여행 상품 추천 run에서 3개 상품이 생성되어 있음 | A15가 기본 포함 항목을 사용하고 `status=ready` 출력 |
| `2번 상품으로 포스터 만들어줘. 스타일은 시네마틱 나이트 시티로 하고, 2번째 이미지를 메인 분위기로 활용해줘.` | 2번 상품과 연결된 이미지가 2장 이상 있음 | A15가 `style_preset=night_city`와 2번째 이미지 URL을 `input_image_urls[0]`에 설정 |
| `2번 상품으로 포스터 만들어줘. 2번째 이미지를 메인 분위기로 활용해줘.` | 2번 상품과 연결된 이미지가 2장 미만 | A15가 `input_image_urls=[]`와 warning을 남기고, 상품 선택은 유지 |
| `포스터 만들어줘.` | 이전 여행 상품 추천 run이 없거나 저장 state가 비어 있음 | A15, A16 또는 A17이 먼저 여행 상품 추천을 생성하라는 안내 출력. 이미지 API 호출 금지 |
| `포스터 만들어줘.` | 이전 여행 상품 추천 run에 상품이 2개 이상 있음 | A15가 `needs_product_selection` 출력. 이미지 API 호출 금지 |

A15 검증 기준:

- 이전 상품 추천 산출물이 없다는 이유로 임의 상품을 만들지 않는다.
- 상품 번호가 없고 상품이 여러 개면 상품 번호를 요구한다.
- 홈페이지 URL 또는 이미지 URL이 없다는 이유로 상품을 제외하지 않는다.
- 사용자가 이미지 번호를 지정했지만 이미지가 부족하면 경고만 남기고 포스터 생성 가능 상태를 유지한다.
- 스타일을 명시하지 않으면 `style_preset=editorial_travel`을 출력하고, 명시하면 `editorial_travel`, `night_city`, `minimal_event` 중 하나로 정규화한다.
- 포스터에 넣는 문구는 `product_manager.last_output`, `brand_marketing_lead.last_output`, `growth_marketing_lead.last_output`, `qa_compliance_manager.last_output`, `proposal_output` 기반이어야 한다.

## 후속 실무 branch 테스트

| 입력 | 전제 | 기대 결과 |
|---|---|---|
| `2번 상품을 여행사 판매용 상품 기획서로 만들어줘.` | 직전 여행 상품 추천 run에서 2번 상품이 있음 | Classify가 판매용 상품 기획서 branch로 보내고 AreaCodeResolverAgent→A18→A20→A21 순서로 실행 |
| `1번 상품을 B2B 단체 상품 기준으로 기획서 만들어줘. 필수 장소와 선택 장소를 나눠줘.` | 직전 여행 상품 추천 run에서 1번 상품이 있음 | A20이 상품 유형, 장소 후보, 상품화 리스크를 출력하고 A21이 `연관 관광지 확장 후보` 섹션 안에서 필수/확장/대체 구분 표로 편집 |
| `3번 상품을 숙박 포함형으로 판매할 수 있는지 검토하고, 대체 코스까지 포함해줘.` | 직전 여행 상품 추천 run에서 3번 상품이 있음 | A18 연관관광지 후보가 있으면 대체 코스 후보로 반영 |
| `2번 상품을 여행사 판매용 상품 기획서로 만들어줘.` | 선택 상품 지역이 부산광역시 중구임 | AreaCodeResolverAgent가 공식 관광지 시군구 코드표 기준 `areaCd=26`, `signguCd=26110`을 출력하고 A18이 이 값을 사용 |
| `1번 상품을 운영 담당자용 체크리스트로 만들어줘.` | 직전 여행 상품 추천 run에서 1번 상품이 있음 | Classify가 운영 branch로 보내고 AreaCodeResolverAgent→A22→A23→A24 순서로 실행 |
| `2번 상품의 우천 시 대체 운영안과 고객 안내 문구를 만들어줘.` | 선택 상품 지역이 부산광역시 중구임 | A22가 `관광지 집중률 예측` 호출 시 TourAPI legacy `area_code=6`, `sigungu_code=15`를 쓰지 않고 공식 관광지 시군구 코드표 기준 `areaCd=26`, `signguCd=26110`과 선택 상품 장소명 `tAtsNm`을 함께 사용 |
| `남해바래길 다랭이지겟길 힐링 트레킹을 운영 체크리스트로 만들어줘.` | 주요 장소에 `가천다랭이마을`, `사촌해변`이 포함됨 | A22가 원 장소명 호출 실패 시 `가천 다랭이`, `사촌`처럼 식별력 있는 fallback query만 소량 추가하고 `마을`, `해변` 같은 일반 단어 단독 query는 만들지 않음 |
| `1번 상품을 운영 담당자용 체크리스트로 만들어줘.` | A22 오늘 날짜 추가 기능이 켜져 있음 | A22가 `baseYmd` 여러 행 중 오늘 날짜와 같은 행을 우선 사용하고, 없으면 오늘 이후 가장 가까운 날짜를 선택 |
| `2번 상품의 우천 시 대체 운영안과 고객 안내 문구를 만들어줘.` | 직전 여행 상품 추천 run에서 2번 상품이 있음 | A23이 우천/혼잡/예약 변동 대응과 고객 안내 문자 템플릿을 출력 |
| `3번 상품을 단체 고객 20명 기준 운영 순서와 현장 리스크 중심으로 정리해줘.` | 직전 여행 상품 추천 run에서 3번 상품이 있음 | A24가 운영 타임라인, 리스크 칩, 인솔자 메모를 Markdown으로 출력 |
| `3번 상품을 마케팅 담당자용 패키지로 만들어줘.` | 직전 여행 상품 추천 run에서 3번 상품이 있음 | Classify가 마케팅 branch로 보내고 A25→A26→A27 순서로 실행 |
| `2번 상품을 가족 타깃 인스타그램 광고 중심으로 카피 5개 만들어줘.` | 직전 여행 상품 추천 run에서 2번 상품이 있음 | A26이 가족 타깃 메시지와 인스타그램 소재를 중심으로 출력 |
| `1번 상품의 블로그 제목, 상세페이지 구성, A/B 테스트 아이디어를 만들어줘.` | 직전 여행 상품 추천 run에서 1번 상품이 있음 | A27이 블로그 제목, 랜딩페이지 구성, A/B 테스트 보드를 Markdown으로 출력 |
| `운영 체크리스트 만들어줘.` | 직전 여행 상품 추천 run에 상품이 2개 이상 있음 | AreaCodeResolverAgent 또는 A22가 `needs_product_selection` 출력하고 API 호출 금지 |
| `마케팅 패키지 만들어줘.` | 이전 여행 상품 추천 run이 없음 | A25가 `needs_source_product` 출력하고 API 호출 금지 |
| `지금 내용 노션에 정리해줘.` | 현재 보이는 사용자-facing Markdown state가 명확함 | Classify가 Notion branch로 보내고 A28R이 현재 보이는 결과 원문 전체를 payload로 정리한 뒤 A28이 `Notion 페이지 생성` 커넥터를 1회 호출하고 Notion 링크만 출력 |
| `방금 내용을 Notion 문서로 저장해줘.` | 비어 있지 않은 저장 output이 하나뿐임 | A28R이 해당 Markdown을 선택해 payload를 만들고 A28이 `Notion 페이지 생성` 커넥터를 1회 호출한 뒤 Notion 링크만 출력 |
| `방금 나온 내용을 노션 페이지로 만들어줘.` | 현재 보이는 사용자-facing Markdown state가 명확함 | A28R이 현재 보이는 결과 원문 전체를 payload로 만들고 A28이 Notion 페이지 생성 |
| `노션 페이지로 만들어줘.` | 저장된 output이 없음 | A28R이 `needs_source_document`를 출력하고 A28은 커넥터를 호출하지 않고 안내만 출력 |

후속 실무 branch 기준:
- AreaCodeResolverAgent는 선택 상품 지역이 부산광역시 중구이면 `areaCd=26`, `signguCd=26110`을 출력한다.
- A18/A22/A25는 API 커넥터 실패나 빈 결과가 있어도 전체 branch를 막지 않고 JSON에 실패/스킵 이유를 남긴다.
- 마케팅 branch의 A25는 `관광사진 키워드 검색`만 사용하므로 AreaCodeResolverAgent를 거치지 않는다.
- A24의 사전 확인 체크리스트 상태 열은 `미확인` 텍스트가 아니라 빈 체크박스 `☐`로 출력한다.
- A24는 운영 체크리스트 시작부에서 “한국관광공사 자료에 따르면...”처럼 날짜와 집중률 근거를 자연어로 설명하고, “API” 같은 내부 용어를 사용자 출력에 쓰지 않는다.
- A21/A24/A27은 사용자-facing Markdown에서 내부 Agent 이름, raw JSON, API 디버그 문구를 출력하지 않는다.
- A21/A24/A27은 표, HTML 카드, HTML table 기반 시각화를 시도한다.
- A14/A17/A21/A24/A27 뒤에는 각각 최종 Markdown을 전용 state에 저장한다.
- A28R은 사용자-facing Markdown을 요약, 축약, 일부 발췌, 재작성하지 않고 Notion payload의 `markdown`에 원문 전체를 그대로 넣는다.
- A28R의 `markdown` payload는 A28R이 생성한 텍스트가 아니라 선택된 저장 state 원문 전체에 직접 매핑되어야 한다. 현재 저장 대상이 불명확하면 다른 브랜치 문서로 fallback하지 않는다.
- A28은 A28R payload의 `title`, `markdown`, `proposal_type`만 body에 넣는다.
- A28 성공 응답은 `Notion 페이지를 만들었습니다.`와 `[Notion에서 열기](...)`만 출력한다.
- A28은 `page_id`, raw 응답, 처리 시간, 내부 state 이름을 사용자에게 출력하지 않는다.

A16 검증 기준:

- API 커넥터를 호출하지 않는다.
- `${poster_brief.last_output.status} != "ready"`이면 프롬프트를 만들지 않고 user_message를 전달한다.
- `${poster_brief.last_output.status} == "ready"`이면 `${poster_prompt.last_output.prompt}`를 만든다.
- `${poster_prompt.last_output.prompt}`에는 `Create one portrait travel promotion poster draft.`, `Scene/background:`, `Subject:`, `Key details:`, `Included text:`, `Composition:`, `Style summary:`, `=== CONSTRAINTS ===`가 있어야 한다.
- A16은 `${poster_brief.last_output.style_preset}`을 사용해 스타일별 scene, lighting, color, typography, composition, style summary 조각을 프롬프트에 반영한다.
- 참고 이미지가 없으면 `=== NO REFERENCE IMAGE GUIDANCE ===`가 있어야 한다.
- 참고 이미지가 있으면 `=== REFERENCE IMAGES ===`가 있어야 하며 이미지 URL 원문은 프롬프트 본문에 넣지 않는다.
- 기본값은 `size=1024x1536`, `quality=low`이다.
- 사용자가 품질을 언급해도 A16은 `quality=low`를 유지하고, Ennoia에 걸려 있는 기본 타임아웃 때문에 현재 포스터는 low quality로 생성하며 추후 개선 예정이라는 warning을 남긴다.
- `input_image_urls`는 최대 3개다.

A17 검증 기준:

- `${poster_prompt.last_output.status} != "ready"`이면 `AI 포스터 이미지 생성` API 커넥터를 호출하지 않는다.
- `${poster_prompt.last_output.status} == "ready"`이면 API 커넥터를 1회 호출한다.
- 요청 body에는 `prompt`, `input_image_urls`, `size`, `quality`가 들어간다.
- 기본값은 `size=1024x1536`, `quality=low`이다.
- A17 최종 응답에는 품질 옵션 관련 안내 문구를 쓰지 않는다.
- `model`은 특별한 이유가 없으면 요청 body에서 생략한다.
- API 응답에 `image_url`이 있으면 최종 응답에 HTML `img` 태그와 “이미지 크게 보기” 버튼이 있어야 한다.
- 최종 응답에는 이미지와 링크 버튼, 짧은 이미지 설명문만 둔다.
- 최종 응답에는 `참고 이미지`, `생성 정보`, `생성 프롬프트 요약` 섹션을 출력하지 않는다.
- API 응답에 `image_id`, `input_image_count`, `model`, `size`, `quality`, `latency_ms`, `provider_response_summary.endpoint`가 있어도 사용자-facing 응답에는 출력하지 않는다.
- 참조 이미지가 전달된 경우에도 참고 이미지 전달 사실이나 `images/edits` 엔드포인트 정보를 표시하지 않는다.
- API 응답에 `image_url`이 없으면 URL을 추측하지 않고 실패 안내를 출력한다.
- `input_image_download_failed`, `input_url_is_not_image`, `input_image_too_large` 오류는 참고 이미지 없이 다시 시도할 수 있다는 안내로 처리한다.
