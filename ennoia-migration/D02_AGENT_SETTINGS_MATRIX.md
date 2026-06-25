# D02. Agent Settings Matrix

## 공통 설정

| 항목 | 값 |
|---|---|
| 한국관광공사 데이터 호출 | API 커넥터만 사용 |
| 한국관광공사 MCP | 사용하지 않음 |
| API 커넥터 사용 Agent | A05A, A05B, A07A, A07A2, A07B, A07C, A07D, A17, A18, A22, A25, A28 |
| 오늘 날짜 추가 기능 | A05 BaselineSearchPlanAgent와 A22 OperationsManagerCrowdingRiskAnalystAgent는 켜기. PlannerAgent는 권장. A05B/A05A/A05D는 불필요 |
| 포스터 생성 | Classify의 별도 branch에서 외부 이미지 생성 API 커넥터로 테스트 구현 |
| 리비전 | 제외 |

## Agent별 설정

| Agent | Model | API 커넥터 | 문서 폴더 | 응답 포맷 | Max tokens | Temp | Frequency | Presence |
|---|---|---|---|---|---:|---:|---:|---:|
| A00 PreflightValidationAgent | gemini-3.1-flash-lite-preview 또는 동급 | 없음 | 없음 | json_schema | 1024 | 0.1 | 0 | 0 |
| A02 PlannerAgent | gemini-3.1-flash-lite-preview 또는 동급 | 없음 | 없음 | json_schema | 2048 | 0.2 | 0 | 0 |
| A03 GeoResolverAgent | gemini-3.1-flash-lite-preview 또는 동급 | 없음 | 없음 | json_schema | 2048 | 0.1 | 0 | 0 |
| A05 BaselineSearchPlanAgent | gemini-3.1-flash-lite-preview 또는 동급 | 없음 | 없음 | json_schema | 2048 | 0 | 0 | 0 |
| A05A CoreTourApiCollectorAgent | gpt-5.1 | A05 core | 없음 | json_schema | 16000 | 0 | 0 | 0 |
| A05B SupplementalTourApiCollectorAgent | gpt-5.1 | A05 keyword/festival/stay | 없음 | json_schema | 16000 | 0 | 0 | 0 |
| A05D CandidateMergeDedupeAgent | gemini-3.1-flash-lite-preview 또는 동급 | 없음 | 없음 | json_schema | 16000 | 0 | 0 | 0 |
| A06 DataGapProfilerAgent | gemini-3.1-flash-lite-preview 또는 gpt-5.1 | 없음 | 없음 | json_schema | 4096 | 0.1 | 0 | 0 |
| A07 ApiCapabilityRouterAgent | gemini-3.1-flash-lite-preview 또는 gpt-5.1 | 없음 | 없음 | json_schema | 4096 | 0 | 0 | 0 |
| A07A TourApiDetailEnrichmentAgent | gpt-5.1 | A07A common/repeat | 없음 | json_schema | 16000 | 0 | 0 | 0 |
| A07A2 TourApiIntroImageEnrichmentAgent | gpt-5.1 | A07A2 intro/image | 없음 | json_schema | 12000 | 0 | 0 | 0 |
| A07B VisualDataEnrichmentAgent | gpt-5.1 | A07B visual | 없음 | json_schema | 8192 | 0 | 0 | 0 |
| A07C RouteSignalEnrichmentAgent | gpt-5.1 | A07C route/signal | 없음 | json_schema | 16000 | 0 | 0 | 0 |
| A07D ThemeDataEnrichmentAgent | gpt-5.1 | A07D theme | 없음 | json_schema | 8192 | 0 | 0 | 0 |
| A08 EnrichmentResultMergeAgent | gemini-3.1-flash-lite-preview 또는 gpt-5.1 | 없음 | 없음 | json_schema | 8192 | 0 | 0 | 0 |
| A09 DataAnalystAgent | gpt-5.1 또는 동급 | 없음 | 없음 | json_schema | 6144 | 0.2 | 0 | 0 |
| A10 ResearchAnalystAgent | gpt-5.1 또는 동급 | 없음 | 없음 | json_schema | 4096 | 0.3 | 0 | 0 |
| A11 ProductManagerAgent | gpt-5.1 또는 동급 | 없음 | 없음 | json_schema | 8192 | 0.4 | 0.1 | 0.1 |
| A12 BrandMarketingLeadAgent | gpt-5.1 또는 동급 | 없음 | 없음 | json_schema | 8192 | 0.5 | 0.1 | 0.2 |
| A12B GrowthMarketingLeadAgent | gpt-5.1 또는 동급 | 없음 | 없음 | json_schema | 6144 | 0.4 | 0.1 | 0.1 |
| A13 QAComplianceManagerAgent | gpt-5.1 또는 동급 | 없음 | 없음 | json_schema | 4096 | 0.1 | 0 | 0 |
| A14A CustomerSuccessManagerAgent | gemini-3.1-flash-lite-preview 또는 동급 | 없음 | 없음 | json_schema | 2048 | 0.2 | 0 | 0 |
| A14 ProposalEditorAgent | gpt-5.1 또는 동급 | 없음 | 없음 | text | 8192 | 0.3 | 0.1 | 0 |
| A15 PosterBriefAgent | gpt-5.1 또는 동급 | 없음 | 없음 | json_schema | 4096 | 0.2 | 0 | 0 |
| A16 PosterPromptBuilderAgent | gpt-5.1 또는 동급 | 없음 | 없음 | json_schema | 4096 | 0.2 | 0 | 0 |
| A17 PosterImageGeneratorAgent | gpt-5.1 또는 동급 | AI 포스터 이미지 생성 | 없음 | text | 4096 | 0.2 | 0 | 0 |
| AreaCodeResolverAgent | gpt-5.1 또는 동급 | 없음 | 없음 | json_schema | 8192 | 0.1 | 0 | 0 |
| A18 ProductPlannerRelatedRouteAnalystAgent | gpt-5.1 또는 동급 | 연관관광지 키워드 검색 | 없음 | json_schema | 8192 | 0.1 | 0 | 0 |
| A20 ProductPlannerSalesPackageAgent | gpt-5.1 또는 동급 | 없음 | 없음 | json_schema | 8192 | 0.3 | 0.1 | 0 |
| A21 ProductPlannerProposalEditorAgent | gpt-5.1 또는 동급 | 없음 | 없음 | text | 8192 | 0.3 | 0.1 | 0 |
| A22 OperationsManagerCrowdingRiskAnalystAgent | gpt-5.1 또는 동급 | 관광지 집중률 예측 | 없음 | json_schema | 8192 | 0.1 | 0 | 0 |
| A23 OperationsManagerRunbookAgent | gpt-5.1 또는 동급 | 없음 | 없음 | json_schema | 8192 | 0.2 | 0 | 0 |
| A24 OperationsManagerProposalEditorAgent | gpt-5.1 또는 동급 | 없음 | 없음 | text | 8192 | 0.3 | 0.1 | 0 |
| A25 MarketingStrategistVisualSignalAgent | gpt-5.1 또는 동급 | 관광사진 키워드 검색 | 없음 | json_schema | 8192 | 0.1 | 0 | 0 |
| A26 MarketingStrategistCampaignPackageAgent | gpt-5.5 | 없음 | 없음 | json_schema | 8192 | 0.4 | 0.1 | 0.1 |
| A27 MarketingStrategistProposalEditorAgent | gpt-5.1 또는 동급 | 없음 | 없음 | text | 8192 | 0.4 | 0.1 | 0.1 |
| A28R NotionPagePayloadBuilderAgent | gpt-5.1 또는 동급 | 없음 | 없음 | json_schema | 16000 | 0.1 | 0 | 0 |
| A28 NotionPagePublishAgent | gpt-5.1 또는 동급 | Notion 페이지 생성 | 없음 | text | 4096 | 0.1 | 0 | 0 |

속도를 우선하면 A05D, A06, A07, A08은 gemini-3.1-flash-lite-preview로 둬도 된다.
A05A~A05B와 A07A, A07A2, A07B~A07D는 API 커넥터 호출/정규화가 있으므로 gpt-5.1을 권장한다.

## 응답 포맷 기준

A00, A02~A03, A05, A05A, A05B, A05D, A06, A07, A07A, A07A2, A07B~A07D, A08~A13은 `json_schema`.
A15와 A16은 `json_schema`.
AreaCodeResolverAgent는 `json_schema`.
A18, A20, A22, A23, A25, A26, A28R은 `json_schema`.
A14A는 `json_schema`, A14, A17, A21, A24, A27, A28은 `text`.
A01 PreflightStatusAgent, A04 GeoStatusAgent, A06S GapRouteStatusAgent는 만들지 않는다.
A07 보강 단계에는 Orchestrator 노드를 쓰지 않는다.
A07A, A07A2, A07B~A07D는 일반 Agent 노드로 만들고 순차 실행한다.
A07A, A07A2, A07B~A07D 출력은 별도 Set state 없이 각 Agent의 `${schema_name.last_output}`을 A08에 직접 넘긴다.

`json_schema`를 선택할 수 없는 화면이면 차선으로 `json_object`를 사용한다.
`json_object`도 선택할 수 없는 화면이면 JSON Agent도 `text`로 두고 시스템 메시지의 JSON 출력 지시를 사용한다.

## API 커넥터 연결

| Agent | API 커넥터 |
|---|---|
| A05A CoreTourApiCollectorAgent | `관광정보 지역기반 목록` |
| A05B SupplementalTourApiCollectorAgent | `관광정보 키워드 검색`, `관광정보 축제 검색`, `관광정보 숙박 검색` |
| A07A TourApiDetailEnrichmentAgent | 관광정보 공통상세, 관광정보 반복정보 |
| A07A2 TourApiIntroImageEnrichmentAgent | 관광정보 소개정보, 관광정보 이미지정보 |
| A07B VisualDataEnrichmentAgent | D09의 A07B visual 커넥터 |
| A07C RouteSignalEnrichmentAgent | D09의 A07C route/signal 커넥터 |
| A07D ThemeDataEnrichmentAgent | D09의 A07D theme 커넥터 |
| A17 PosterImageGeneratorAgent | `AI 포스터 이미지 생성` |
| A18 ProductPlannerRelatedRouteAnalystAgent | `연관관광지 키워드 검색` |
| A22 OperationsManagerCrowdingRiskAnalystAgent | `관광지 집중률 예측` |
| A25 MarketingStrategistVisualSignalAgent | `관광사진 키워드 검색` |
| A28 NotionPagePublishAgent | `Notion 페이지 생성` |

샘플의 `areaCode` 기반 URL은 A05 baseline에서는 사용하지 않는다.
A05는 반드시 `lDongRegnCd`, `lDongSignguCd` 기반 URL로 새 커넥터를 만든다.

A18/A22 후속 API는 `areaCd`, `signguCd`를 요구한다. 이 값은 해당 branch 앞의 AreaCodeResolverAgent가 공식 관광지 시군구 코드표 기준으로 만든 값을 사용한다.
A25는 `관광사진 키워드 검색`을 사용하므로 AreaCodeResolverAgent를 거치지 않고 장소명 또는 테마 `keyword`를 사용한다.
예: 부산광역시 중구는 `areaCd=26`, `signguCd=26110`.
TourAPI 국문 관광정보의 legacy `area_code`, `sigungu_code`를 후속 실무 branch API 코드로 쓰지 않는다.

## A05 기준

`관광정보 지역기반 목록`에는 `contentTypeId`, `arrange`, `pageNo`, `numOfRows` 파라미터를 둔다.
A05A는 `arrange=A`, `pageNo=1` 고정 대신 `arrange=Q`로 지역기반 관광지와 레포츠를 수집한다.
A05A 호출 조합은 contentTypeId 12/28 각각에 대해 `arrange=Q`, `pageNo=1`, `numOfRows=20`이다.
A05B는 키워드와 숙박 보조 후보를 지역 확정 시 기본 수집하고, 축제 후보는 eventStartDate가 있을 때 수집한다.
A05B의 키워드/축제/숙박 커넥터는 각각 numOfRows=10 기준이다.
키워드 검색은 keyword_queries 중 최대 5개까지 호출하고, 출력은 키워드 후보 최대 10개로 줄인다.
A05B는 지역이 확정되면 keyword와 stay를 기본 호출한다.
A05B는 eventStartDate가 있으면 festival을 호출한다.
A05의 날짜 계산은 Ennoia가 시스템 프롬프트 맨 위에 자동 삽입하는 `### Current date is ...` 값을 기준으로 한다.
A05B는 날짜를 계산하지 않고 A05가 출력한 eventStartDate/eventEndDate만 사용한다.
A05D의 최종 `source_items`는 최대 15개다.
GeoResolverAgent가 "충청도"를 충청북도와 충청남도처럼 복수 resolved_locations로 확정한 경우 A05A/A05B는 첫 번째 지역만 수집하지 않고 각 resolved_location별로 API를 호출한다.
A05A/A05B는 `ldong_regn_cd="43,44"` 같은 콤마 문자열을 API 파라미터로 그대로 넘기지 않는다.
A05D는 복수 resolved_locations 중 어느 하나와 맞는 후보를 지역 일치로 본다.

## A07/A08 기준

A07A, A07A2, A07B~A07D는 순차 실행되는 일반 Agent 노드로 만든다.
각 Agent는 직전 ApiCapabilityRouterAgent 출력의 `orchestrator_instruction.call_agents`에 자기 이름이 없으면 API를 호출하지 않고 빈 결과를 출력한다.
각 Agent는 직전 ApiCapabilityRouterAgent 출력의 `orchestrator_instruction.api_calls`에 지정된 커넥터만 호출한다.
A07A, A07A2, A07B~A07D는 각자 자기 lane의 호출 판단, API 커넥터 호출, 정규화를 함께 수행한다.
A05D CandidateMergeDedupeAgent가 이미 후보 수를 줄였으므로 A07A에는 별도 후보 개수 제한을 두지 않는다.
A07A 상세 커넥터의 `numOfRows` 기준은 `detailCommon2=10`, `detailInfo2=5`다.
A07A2 상세 커넥터의 `numOfRows` 기준은 `detailIntro2=5`, `detailImage2=10`이다.
A07A에서 `missing_detail_info` 또는 overview 누락 gap이 있으면 `관광정보 공통상세`를 1순위로 호출한다.
A07A는 `관광정보 반복정보`만으로 overview gap을 해결했다고 판단하지 않는다.
처리하지 못한 contentId 또는 호출하지 못한 API는 반드시 `skipped_calls` 또는 `failed_calls`에 기록한다.
A07A, A07A2, A07B~A07D 뒤에는 Set state 노드를 만들지 않는다.
A08은 API 커넥터를 연결하지 않고 다섯 lane 출력을 하나의 `enrichment_summary`로 병합한다.

## A15/A16/A17 포스터 branch 기준

Start 바로 다음 Classify에서 `그 내용으로 포스터 만들어줘`로 분기한 요청은 A15로 연결한다.
A15는 API 커넥터를 연결하지 않고 상품 관련 Agent의 `*.last_output`과 `proposal_output`만 읽어 `${poster_brief.last_output}` JSON을 만든다.
A16은 API 커넥터를 연결하지 않고 `${poster_brief.last_output}`을 기존 PARAVOCA 방식의 `${poster_prompt.last_output}` JSON으로 바꾼다.
A17은 `${poster_prompt.last_output.status} == "ready"`일 때만 `AI 포스터 이미지 생성` API 커넥터를 호출한다.
A17의 이미지 생성 요청은 1장 고정이며, 기본 `size=1024x1536`, `quality=low`을 사용한다.
사용자가 품질을 언급해도 A16/A17은 `quality=low`을 유지하고, A17은 Ennoia에 걸려 있는 기본 타임아웃 때문에 low quality로 생성했으며 추후 개선 예정이라는 안내 문구를 출력한다.
A15/A16이 `input_image_urls`를 채웠고 API 커넥터 입력 필드가 준비되어 있으면 A17은 그 배열을 함께 전달한다.
이미지 URL이 없거나 사용자가 이미지 번호를 지정하지 않아도 포스터 생성은 계속 가능해야 한다.

## A18~A28 후속 실무 branch 기준

Start 바로 다음 Classify에는 아래 카테고리를 추가한다.

| 카테고리 | 연결 |
|---|---|
| `판매용 상품 기획서 만들어줘` | AreaCodeResolverAgent |
| `운영 체크리스트 만들어줘` | AreaCodeResolverAgent |
| `마케팅 패키지 만들어줘` | A25 MarketingStrategistVisualSignalAgent |
| `노션 페이지로 만들어줘` | A28R NotionPagePayloadBuilderAgent → A28 NotionPagePublishAgent |

후속 branch는 공통 context parser Agent를 만들지 않는다.
판매용 상품 기획서와 운영 체크리스트 branch의 AreaCodeResolverAgent가 사용자 요청, `proposal_output`, 상품 관련 `${schema_name.last_output}`에서 상품 번호와 공식 관광지 시군구 코드표 기준 `areaCd`, `signguCd`를 먼저 해석한다.
마케팅 패키지 branch는 A25가 사용자 요청과 기존 상품 산출물에서 상품 번호, 장소명, 테마 keyword를 직접 해석한다.

`연관관광지 키워드 검색` API 커넥터는 resolver 출력의 `areaCd`, `signguCd`, `keyword`, `baseYm`을 사용한다.
`관광지 집중률 예측` API 커넥터는 resolver 출력의 `areaCd`, `signguCd`와 선택 상품 장소명 `tAtsNm`을 사용한다. A22는 원 장소명을 먼저 호출하고, 결과가 없거나 매칭이 없을 때만 고유 지명/브랜드 중심 fallback query를 소량 추가한다.
`관광사진 키워드 검색` API 커넥터는 선택 상품의 장소명 또는 테마 `keyword`를 사용한다.
resolver가 코드를 확인하지 못하면 A18/A22는 해당 API 호출을 생략하고 JSON의 `analysis_notes` 또는 `skipped_calls`에 이유를 남긴다.

마크다운 편집 Agent A21/A24/A27은 raw HTML 카드/표와 HTML table 기반 pseudo-flowchart를 시도할 수 있다.

## 문서 폴더

문서 폴더는 사용하지 않는다.

`TourAPI_법정동_후보`는 `A03_GEO_RESOLVER_AGENT.md` 시스템 메시지 안에 직접 포함한다.
워크플로우 규칙, 한국관광공사 API 필드 해석, 근거/QA 가드레일, 마케팅 기준도 각 Agent 시스템 프롬프트에 직접 포함한다.
