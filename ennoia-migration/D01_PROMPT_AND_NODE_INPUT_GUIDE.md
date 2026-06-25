# D01. Prompt and Node Input Guide

## 사용자 입력

사용자 입력은 `Workflow Input.messages`로 들어온다.
프롬프트에서는 `${messages}`로 참조한다.
별도 `user_message` state는 만들지 않는다.

## Agent 노드 생성 순서

Start 바로 다음에는 `Classify Request Type` 노드를 둔다.
카테고리는 `여행 상품 추천해줘`, `그 내용으로 포스터 만들어줘`, `판매용 상품 기획서 만들어줘`, `운영 체크리스트 만들어줘`, `마케팅 패키지 만들어줘`, `노션 페이지로 만들어줘` 여섯 개로 만든다.
`여행 상품 추천해줘`는 A00으로 연결하고, `그 내용으로 포스터 만들어줘`는 A15로 연결한다.
판매용 상품 기획서와 운영 체크리스트 branch는 AreaCodeResolverAgent로 먼저 연결한다.
마케팅 패키지 branch는 `관광사진 키워드 검색`만 사용하므로 A25 MarketingStrategistVisualSignalAgent로 바로 연결한다.
`노션 페이지로 만들어줘`는 A28R NotionPagePayloadBuilderAgent를 거쳐 A28 NotionPagePublishAgent로 연결한다.

| 순서 | 파일 | Ennoia Agent/Node 이름 | 응답 포맷 |
|---:|---|---|---|
| 0 | `A00_PREFLIGHT_VALIDATION_AGENT.md` | `PreflightValidationAgent` | json_schema |
| 1 | `A02_PLANNER_AGENT.md` | `PlannerAgent` | json_schema |
| 2 | `A03_GEO_RESOLVER_AGENT.md` | `GeoResolverAgent` | json_schema |
| 3 | `A05_BASELINE_SEARCH_PLAN_AGENT.md` | `BaselineSearchPlanAgent` | json_schema |
| 3A | `A05A_CORE_TOURAPI_COLLECTOR_AGENT.md` | `CoreTourApiCollectorAgent` | json_schema |
| 3B | `A05B_SUPPLEMENTAL_TOURAPI_COLLECTOR_AGENT.md` | `SupplementalTourApiCollectorAgent` | json_schema |
| 3D | `A05D_CANDIDATE_MERGE_DEDUPE_AGENT.md` | `CandidateMergeDedupeAgent` | json_schema |
| 4 | `A06_DATA_GAP_PROFILER_AGENT.md` | `DataGapProfilerAgent` | json_schema |
| 5 | `A07_API_CAPABILITY_ROUTER_AGENT.md` | `ApiCapabilityRouterAgent` | json_schema |
| 5A | `A07A_TOURAPI_DETAIL_ENRICHMENT_AGENT.md` | `TourApiDetailEnrichmentAgent` | json_schema |
| 5A2 | `A07A2_TOURAPI_INTRO_IMAGE_ENRICHMENT_AGENT.md` | `TourApiIntroImageEnrichmentAgent` | json_schema |
| 5B | `A07B_VISUAL_DATA_ENRICHMENT_AGENT.md` | `VisualDataEnrichmentAgent` | json_schema |
| 5C | `A07C_ROUTE_SIGNAL_ENRICHMENT_AGENT.md` | `RouteSignalEnrichmentAgent` | json_schema |
| 5D | `A07D_THEME_DATA_ENRICHMENT_AGENT.md` | `ThemeDataEnrichmentAgent` | json_schema |
| 6 | `A08_ENRICHMENT_RESULT_MERGE_AGENT.md` | `EnrichmentResultMergeAgent` | json_schema |
| 7 | `A09_DATA_ANALYST_AGENT.md` | `DataAnalystAgent` | json_schema |
| 8 | `A10_RESEARCH_ANALYST_AGENT.md` | `ResearchAnalystAgent` | json_schema |
| 9 | `A11_PRODUCT_MANAGER_AGENT.md` | `ProductManagerAgent` | json_schema |
| 10 | `A12_BRAND_MARKETING_LEAD_AGENT.md` | `BrandMarketingLeadAgent` | json_schema |
| 10B | `A12B_GROWTH_MARKETING_LEAD_AGENT.md` | `GrowthMarketingLeadAgent` | json_schema |
| 11 | `A13_QA_COMPLIANCE_MANAGER_AGENT.md` | `QAComplianceManagerAgent` | json_schema |
| 13A | `A14A_CUSTOMER_SUCCESS_MANAGER_AGENT.md` | `CustomerSuccessManagerAgent` | json_schema |
| 14 | `A14_PROPOSAL_EDITOR_AGENT.md` | `ProposalEditorAgent` | text |
| 15 | `A15_POSTER_BRIEF_AGENT.md` | `PosterBriefAgent` | json_schema |
| 16 | `A16_POSTER_PROMPT_BUILDER_AGENT.md` | `PosterPromptBuilderAgent` | json_schema |
| 17 | `A17_POSTER_IMAGE_GENERATOR_AGENT.md` | `PosterImageGeneratorAgent` | text |
| 17R | `A17R_AREA_CODE_RESOLVER_AGENT.md` | `AreaCodeResolverAgent` | json_schema |
| 18 | `A18_PRODUCT_PLANNER_RELATED_ROUTE_ANALYST_AGENT.md` | `ProductPlannerRelatedRouteAnalystAgent` | json_schema |
| 20 | `A20_PRODUCT_PLANNER_SALES_PACKAGE_AGENT.md` | `ProductPlannerSalesPackageAgent` | json_schema |
| 21 | `A21_PRODUCT_PLANNER_PROPOSAL_EDITOR_AGENT.md` | `ProductPlannerProposalEditorAgent` | text |
| 22 | `A22_OPERATIONS_MANAGER_CROWDING_RISK_ANALYST_AGENT.md` | `OperationsManagerCrowdingRiskAnalystAgent` | json_schema |
| 23 | `A23_OPERATIONS_MANAGER_RUNBOOK_AGENT.md` | `OperationsManagerRunbookAgent` | json_schema |
| 24 | `A24_OPERATIONS_MANAGER_PROPOSAL_EDITOR_AGENT.md` | `OperationsManagerProposalEditorAgent` | text |
| 25 | `A25_MARKETING_STRATEGIST_VISUAL_SIGNAL_AGENT.md` | `MarketingStrategistVisualSignalAgent` | json_schema |
| 26 | `A26_MARKETING_STRATEGIST_CAMPAIGN_PACKAGE_AGENT.md` | `MarketingStrategistCampaignPackageAgent` | json_schema |
| 27 | `A27_MARKETING_STRATEGIST_PROPOSAL_EDITOR_AGENT.md` | `MarketingStrategistProposalEditorAgent` | text |
| 28R | `A28R_NOTION_PAGE_PAYLOAD_BUILDER_AGENT.md` | `NotionPagePayloadBuilderAgent` | json_schema |
| 28 | `A28_NOTION_PAGE_PUBLISH_AGENT.md` | `NotionPagePublishAgent` | text |

A01 PreflightStatusAgent, A04 GeoStatusAgent, A06S GapRouteStatusAgent는 `json_schema` 구조 출력으로 대체되어 새 캔버스에서는 만들지 않는다.

A07 보강 단계에는 Orchestrator 노드를 쓰지 않는다.
ApiCapabilityRouterAgent 출력의 `orchestrator_instruction.call_agents`가 복수 Agent를 포함해도 Orchestrator가 한 Agent만 실행하고 다음 단계로 빠질 수 있기 때문이다.
A07A, A07A2, A07B~A07D는 모두 일반 Agent 노드로 만들고 `A07A → A07A2 → A07B → A07C → A07D` 순서로 강제 통과시킨다.
각 Agent는 `call_agents`에 자기 이름이 있으면 자기 lane API를 호출하고, 실제 호출 커넥터는 `orchestrator_instruction.api_calls`를 우선한다.
A07A, A07A2, A07B~A07D 출력은 별도 Set state 없이 각 Agent의 `${schema_name.last_output}`을 A08에 직접 입력한다.
A08 EnrichmentResultMergeAgent 뒤에는 `last_message`를 `enrichment_output`에 저장하는 Set state를 둔다.
단, 후속 Agent 프롬프트 입력에는 `enrichment_output`을 직접 쓰지 않고 `${enrichment_result_merge.last_output}`을 사용한다.

## 출력 저장 규칙

json_schema Agent 출력은 원칙적으로 별도 Set state에 옮기지 않고 `${json_schema_name.last_output}`으로 직접 읽는다.
예를 들어 PreflightValidationAgent는 `${preflight_validation.last_output}`, CandidateMergeDedupeAgent는 `${candidate_merge_dedupe.last_output}`을 쓴다.

아래 출력은 캔버스 저장/재사용을 위해 Set state로 저장한다.
`enrichment_output`, `qa_output`은 저장용 state이며 Agent 프롬프트 입력에는 직접 쓰지 않는다.

| Agent/Node | 저장 state | 값 |
|---|---|---|
| EnrichmentResultMergeAgent | `enrichment_output` | `last_message` |
| QAComplianceManagerAgent | `qa_output` | `last_message` |
| CustomerSuccessManagerAgent | `customer_message_output` | `last_message` |
| ProposalEditorAgent | `proposal_output` | `last_message` |
| PosterImageGeneratorAgent | `poster_output` | `last_message` |
| ProductPlannerProposalEditorAgent | `product_planner_proposal_output` | `last_message` |
| OperationsManagerProposalEditorAgent | `operations_manager_proposal_output` | `last_message` |
| MarketingStrategistProposalEditorAgent | `marketing_strategist_proposal_output` | `last_message` |

StatusAgent 3개는 만들지 않는다.
if/else에서는 아래 structured output 필드를 직접 비교한다.

| 분기 | 조건 필드 |
|---|---|
| request_supported | `${preflight_validation.last_output.supported} == true` |
| geo_resolved | `${geo_resolution.last_output.geo_resolved} == true` |
| enrichment_needed | `${data_gap_profile.last_output.enrichment_needed} == true` |

분기 조건은 직전 또는 upstream Agent의 structured output 필드를 UI 변수 선택기로 골라 사용한다.
CEL 직접 입력 문법이 UI 표시와 다르면 UI가 만들어준 표현식을 따른다.

Set state 값 표현식 주의:
- `workflow.*`는 쓰지 않는다. CEL 평가 컨텍스트에 `workflow`가 없으면 Set state 단계에서 실패한다.
- 저장용 Set state 값은 `last_message`를 사용한다.
- Start 입력을 테스트용으로 바로 state에 저장할 때도 값은 `last_message`를 사용한다.
- 여러 upstream Agent를 하나의 Set state에 연결하는 경우에는 UI 변수 선택기로 각 upstream Agent 출력을 지정한다.
- json_schema Agent 출력은 `${json_schema_name.last_output}`으로 직접 읽으므로 `preflight_output`, `geo_output`, `gap_output` 같은 예전 별칭 state를 만들지 않는다.
- `enrichment_output`, `qa_output`은 저장용으로만 만들고 Agent 프롬프트 입력에는 직접 쓰지 않는다.
- `customer_message_output`은 A14A 저장용, `proposal_output`은 A14 최종 Markdown의 포스터 branch 재사용용으로 Set state에 저장한다.
- `poster_output`은 A17 최종 포스터 생성 결과를 Notion 저장 branch에서 쓰기 위한 저장용 state다.
- `product_planner_proposal_output`, `operations_manager_proposal_output`, `marketing_strategist_proposal_output`은 A28R/A28 Notion 저장 branch가 후속 문서를 저장할 때 쓰는 저장용 state다.

## 최소 입력 규칙

토큰 절약을 위해 각 Agent에는 자기 역할에 필요한 state만 넣는다.
앞선 모든 state를 관성적으로 넣지 않는다.

| Agent/Node | 필요한 입력 |
|---|---|
| A05A CoreTourApiCollectorAgent | `baseline_search_plan.last_output`, `geo_resolution.last_output` |
| A05B SupplementalTourApiCollectorAgent | `messages`, `baseline_search_plan.last_output` |
| A05D CandidateMergeDedupeAgent | `messages`, `planner.last_output`, `baseline_search_plan.last_output`, `geo_resolution.last_output`, `core_tourapi_collector.last_output`, `supplemental_tourapi_collector.last_output` |
| A06 DataGapProfilerAgent | `candidate_merge_dedupe.last_output` |
| A07 ApiCapabilityRouterAgent | `data_gap_profile.last_output` |
| A07A TourApiDetailEnrichmentAgent | `candidate_merge_dedupe.last_output`, `data_gap_profile.last_output`, `api_capability_router.last_output` |
| A07A2 TourApiIntroImageEnrichmentAgent | `candidate_merge_dedupe.last_output`, `data_gap_profile.last_output`, `api_capability_router.last_output` |
| A07B VisualDataEnrichmentAgent | `candidate_merge_dedupe.last_output`, `data_gap_profile.last_output`, `api_capability_router.last_output` |
| A07C RouteSignalEnrichmentAgent | `candidate_merge_dedupe.last_output`, `data_gap_profile.last_output`, `api_capability_router.last_output` |
| A07D ThemeDataEnrichmentAgent | `messages`, `candidate_merge_dedupe.last_output`, `data_gap_profile.last_output`, `api_capability_router.last_output` |
| A08 EnrichmentResultMergeAgent | `tourapi_detail_enrichment.last_output`, `tourapi_intro_image_enrichment.last_output`, `visual_data_enrichment.last_output`, `route_signal_enrichment.last_output`, `theme_data_enrichment.last_output` |
| A09 DataAnalystAgent | `candidate_merge_dedupe.last_output`, `data_gap_profile.last_output`, `enrichment_result_merge.last_output` |
| A10 ResearchAnalystAgent | `planner.last_output`, `data_analyst.last_output` |
| A11 ProductManagerAgent | `planner.last_output`, `data_analyst.last_output`, `research_analyst.last_output` |
| A12 BrandMarketingLeadAgent | `data_analyst.last_output`, `product_manager.last_output` |
| A12B GrowthMarketingLeadAgent | `data_analyst.last_output`, `product_manager.last_output`, `brand_marketing_lead.last_output` |
| A13 QAComplianceManagerAgent | `data_analyst.last_output`, `product_manager.last_output`, `brand_marketing_lead.last_output`, `growth_marketing_lead.last_output` |
| A14A CustomerSuccessManagerAgent | `messages`, `preflight_validation.last_output`, `geo_resolution.last_output` |
| A14 ProposalEditorAgent | `preflight_validation.last_output`, `planner.last_output`, `geo_resolution.last_output`, `candidate_merge_dedupe.last_output`, `enrichment_result_merge.last_output`, `data_analyst.last_output`, `research_analyst.last_output`, `product_manager.last_output`, `brand_marketing_lead.last_output`, `growth_marketing_lead.last_output`, `qa_compliance_manager.last_output`, `customer_success_manager.last_output` |
| A15 PosterBriefAgent | `messages`, `candidate_merge_dedupe.last_output`, `enrichment_result_merge.last_output`, `product_manager.last_output`, `brand_marketing_lead.last_output`, `growth_marketing_lead.last_output`, `qa_compliance_manager.last_output`, `proposal_output` |
| A16 PosterPromptBuilderAgent | `messages`, `poster_brief.last_output` |
| A17 PosterImageGeneratorAgent | `messages`, `poster_prompt.last_output` |
| AreaCodeResolverAgent | `messages`, `product_manager.last_output`, `proposal_output` |
| A18 ProductPlannerRelatedRouteAnalystAgent | `messages`, `product_manager.last_output`, `area_code_resolver.last_output`, `proposal_output` |
| A20 ProductPlannerSalesPackageAgent | `messages`, `product_manager.last_output`, `brand_marketing_lead.last_output`, `growth_marketing_lead.last_output`, `qa_compliance_manager.last_output`, `product_planner_related_route_analyst.last_output`, `proposal_output` |
| A21 ProductPlannerProposalEditorAgent | `messages`, `product_planner_sales_package.last_output`, `product_planner_related_route_analyst.last_output` |
| A22 OperationsManagerCrowdingRiskAnalystAgent | `messages`, `product_manager.last_output`, `qa_compliance_manager.last_output`, `area_code_resolver.last_output`, `proposal_output` |
| A23 OperationsManagerRunbookAgent | `messages`, `product_manager.last_output`, `qa_compliance_manager.last_output`, `operations_manager_crowding_risk_analyst.last_output`, `proposal_output` |
| A24 OperationsManagerProposalEditorAgent | `messages`, `operations_manager_crowding_risk_analyst.last_output`, `operations_manager_runbook.last_output` |
| A25 MarketingStrategistVisualSignalAgent | `messages`, `product_manager.last_output`, `brand_marketing_lead.last_output`, `growth_marketing_lead.last_output`, `qa_compliance_manager.last_output`, `proposal_output` |
| A26 MarketingStrategistCampaignPackageAgent | `messages`, `product_manager.last_output`, `brand_marketing_lead.last_output`, `growth_marketing_lead.last_output`, `qa_compliance_manager.last_output`, `marketing_strategist_visual_signal.last_output`, `proposal_output` |
| A27 MarketingStrategistProposalEditorAgent | `messages`, `marketing_strategist_visual_signal.last_output`, `marketing_strategist_campaign_package.last_output` |
| A28R NotionPagePayloadBuilderAgent | `messages`, `poster_output`, `proposal_output`, `product_planner_proposal_output`, `operations_manager_proposal_output`, `marketing_strategist_proposal_output` |
| A28 NotionPagePublishAgent | `messages`, `notion_page_payload_builder.last_output` |

## State 사용 기준

`keyword_candidates_output`, `optional_candidates_output`, `merged_candidates_output`은 만들지 않는다.
`preflight_output`, `geo_output`, `search_plan_output`, `core_candidates_output`, `baseline_output`, `gap_output`, `capability_routing_output`, `detail_enrichment_output`, `visual_enrichment_output`, `route_signal_enrichment_output`, `theme_enrichment_output`, `evidence_output`, `research_output`, `product_output`, `brand_marketing_output`, `growth_marketing_output`은 만들지 않는다.
A05D는 `${core_tourapi_collector.last_output}`과 `${supplemental_tourapi_collector.last_output}`을 직접 읽고 최종 `source_items`를 출력한다.
`enrichment_output`은 A08 EnrichmentResultMergeAgent의 `last_message`, `qa_output`은 A13 QAComplianceManagerAgent의 `last_message` 저장용으로 만든다.
다만 A09/A14/A15 같은 Agent 프롬프트 입력에는 `${enrichment_result_merge.last_output}`, `${qa_compliance_manager.last_output}`을 사용한다.
`customer_message_output`은 A14A CustomerSuccessManagerAgent의 `last_message` 저장용으로 유지한다. A14 ProposalEditorAgent 입력에는 `${customer_success_manager.last_output}`을 사용한다.
`final_markdown`은 만들지 않는다.
A14 ProposalEditorAgent 출력은 `proposal_output`에 저장한 뒤 End에 연결한다.
`proposal_output`은 포스터 branch가 “3번 상품으로 포스터 만들어줘” 같은 후속 요청에서 최종 사용자-facing 상품 번호와 문구를 확인할 때 사용한다.
A17 PosterImageGeneratorAgent 출력은 `poster_output`에 저장한 뒤 End에 연결한다.
A21 ProductPlannerProposalEditorAgent 출력은 `product_planner_proposal_output`에 저장한 뒤 End에 연결한다.
A24 OperationsManagerProposalEditorAgent 출력은 `operations_manager_proposal_output`에 저장한 뒤 End에 연결한다.
A27 MarketingStrategistProposalEditorAgent 출력은 `marketing_strategist_proposal_output`에 저장한 뒤 End에 연결한다.

## 포스터 branch

Classify가 `그 내용으로 포스터 만들어줘`로 분기하면 A15 PosterBriefAgent로 보낸다.
A15는 이전 여행 상품 추천 branch의 상품 관련 `*.last_output`, `proposal_output`, 현재 사용자 요청을 읽어 `${poster_brief.last_output}` JSON을 만든다.
A15 뒤에는 별도 Set state를 만들지 않는다.
A16 PosterPromptBuilderAgent는 A15의 `${poster_brief.last_output}`을 바로 읽어 기존 PARAVOCA 방식의 `${poster_prompt.last_output}` JSON을 만든다.
A16 뒤에도 별도 Set state를 만들지 않는다.
A17 PosterImageGeneratorAgent는 A16의 `${poster_prompt.last_output}`을 바로 읽는다.
`${poster_prompt.last_output.status} != "ready"`이면 A17은 이미지 생성 API 커넥터를 호출하지 않고 A16의 `user_message`를 출력한다.
`${poster_prompt.last_output.status} == "ready"`이면 A17이 `AI 포스터 이미지 생성` API 커넥터를 호출하고, 반환된 `image_url`을 HTML `img` 태그와 링크 버튼으로 출력한다.

## 후속 실무 branch

Classify가 `판매용 상품 기획서 만들어줘`로 분기하면 AreaCodeResolverAgent로 보낸다.
Classify가 `운영 체크리스트 만들어줘`로 분기하면 AreaCodeResolverAgent로 보낸다.
Classify가 `마케팅 패키지 만들어줘`로 분기하면 A25 MarketingStrategistVisualSignalAgent로 바로 보낸다.
Classify가 `노션 페이지로 만들어줘`로 분기하면 A28R NotionPagePayloadBuilderAgent로 보낸 뒤 A28 NotionPagePublishAgent로 보낸다.

후속 실무 branch는 기존 여행 상품 추천 branch를 다시 실행하지 않는다.
판매용 상품 기획서와 운영 체크리스트 branch의 AreaCodeResolverAgent가 현재 사용자 요청과 이전 추천 산출물에서 상품 번호, 선택 상품 지역, 공식 관광지 시군구 코드표 기준 `areaCd`, `signguCd`를 먼저 해석한다.
A18과 A22는 resolver 출력만 사용한다.
마케팅 패키지 branch의 A25는 사용자 요청과 이전 추천 산출물에서 상품 번호를 직접 해석하고, 장소명 또는 테마 keyword로 `관광사진 키워드 검색`을 호출한다.
상품 번호가 없고 이전 상품이 2개 이상이면 `needs_product_selection` 상태를 출력한다.
이전 여행 상품 추천 산출물이 없으면 `needs_source_product` 상태를 출력한다.

## Notion 저장 branch

Classify가 `노션 페이지로 만들어줘`로 분기하면 A28R NotionPagePayloadBuilderAgent로 보낸 뒤 A28 NotionPagePublishAgent로 보낸다.
A28R과 A28은 기존 여행 상품 추천 branch나 후속 실무 branch를 다시 실행하지 않는다.
A28R은 저장된 사용자-facing Markdown state 중 사용자 요청에 정확히 맞는 하나를 선택하고 `title`, `markdown`, `proposal_type` payload를 만든다.
A28은 A28R이 만든 payload로 `Notion 페이지 생성` API 커넥터를 1회 호출하고, 응답의 URL만 출력한다.
`markdown` payload에는 A26 같은 JSON Agent의 `last_output`을 넣지 않는다. 예를 들어 마케팅 패키지는 반드시 `marketing_strategist_proposal_output`을 넣고, `marketing_strategist_campaign_package.last_output` JSON은 넣지 않는다.
A28R/A28이 생성한 요약문, 축약문, 일부 발췌문, 재작성문, `...(이하 생략...)` placeholder, 내부 재시도 문장은 `markdown` body에 들어가면 안 된다. 선택된 저장 state 원문 전체를 그대로 넣어야 한다.

문서 선택 기준:
- 요청이 여행 상품 추천 결과를 말하면 `proposal_output`
- 요청이 AI 포스터 생성 결과를 말하면 `poster_output`
- 요청이 판매용 상품 기획서를 말하면 `product_planner_proposal_output`
- 요청이 운영 체크리스트를 말하면 `operations_manager_proposal_output`
- 요청이 마케팅 패키지를 말하면 `marketing_strategist_proposal_output`
- 요청이 “지금 내용”, “지금 나온 내용”, “방금 내용”, “방금 말한 내용”, “그 내용”, “이 문서”처럼 현재 보이는 결과를 가리키면 저장 요청으로 처리
- 비어 있지 않은 저장 output이 하나뿐이면 그 output을 선택
- 비어 있지 않은 저장 output이 여러 개이고 문서 유형 단서가 없으면 오래된 다른 브랜치 문서로 fallback하지 않고 `needs_document_selection`으로 멈춘다.

A28은 Notion API 커넥터 응답의 `page_url`만 사용자-facing Markdown 링크로 출력한다.

시각화가 필요한 경우 마크다운 편집 Agent가 HTML table 기반 시각화를 사용한다.

## 실패 처리

Preflight 실패는 if/else로 종료한다.
Geo 실패도 if/else로 종료한다.
두 실패 경로는 A14A CustomerSuccessManagerAgent로 연결한 뒤 A14 ProposalEditorAgent로 보낸다.
A14A는 고객에게 다시 입력할 예시를 포함한 구조화 안내 JSON을 작성한다.
A14는 `${customer_success_manager.last_output}`을 Markdown 안내로 편집해 최종 응답으로 출력한다.

A05 계열 데이터 부족 이후는 중간 if/else로 끊지 않는다.
후속 Agent가 앞선 `${schema_name.last_output}`을 읽고 빈 배열 또는 blocked JSON을 반환한다.
최종 ProposalEditorAgent가 데이터 부족 안내를 작성한다.

Gap이 없으면 DataGapProfilerAgent가 `route_status = "NO_ENRICHMENT_NEEDED"`와 `enrichment_needed = false`를 출력하고 A09로 바로 넘어간다.
이때 `${enrichment_result_merge.last_output}`은 없거나 빈 값이어도 된다.
이 경로는 실패가 아니라 보강 생략 정상 경로이므로 A14로 바로 보내지 않는다.
