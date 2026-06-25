# D00. Canvas Flow and State

## 최종 캔버스 구조

```text
Start
→ Classify Request Type
  - 여행 상품 추천해줘:
    → A00 PreflightValidationAgent
  - 그 내용으로 포스터 만들어줘:
	    → A15 PosterBriefAgent
	    → A16 PosterPromptBuilderAgent
	    → A17 PosterImageGeneratorAgent
	    → Set state: poster_output
	    → End
  - 판매용 상품 기획서 만들어줘:
    → AreaCodeResolverAgent
	    → A18 ProductPlannerRelatedRouteAnalystAgent
	    → A20 ProductPlannerSalesPackageAgent
	    → A21 ProductPlannerProposalEditorAgent
	    → Set state: product_planner_proposal_output
	    → End
  - 운영 체크리스트 만들어줘:
    → AreaCodeResolverAgent
	    → A22 OperationsManagerCrowdingRiskAnalystAgent
	    → A23 OperationsManagerRunbookAgent
	    → A24 OperationsManagerProposalEditorAgent
	    → Set state: operations_manager_proposal_output
	    → End
	  - 마케팅 패키지 만들어줘:
	    → A25 MarketingStrategistVisualSignalAgent
	    → A26 MarketingStrategistCampaignPackageAgent
	    → A27 MarketingStrategistProposalEditorAgent
	    → Set state: marketing_strategist_proposal_output
	    → End
	  - 노션 페이지로 만들어줘:
	    → A28R NotionPagePayloadBuilderAgent
	    → A28 NotionPagePublishAgent
	    → End
```

여행 상품 추천 branch:

```text
A00 PreflightValidationAgent
→ If/else: ${preflight_validation.last_output.supported}
  - If: A02 PlannerAgent
  - Else: A14A CustomerSuccessManagerAgent
    → Set state: customer_message_output
	    → A14 ProposalEditorAgent
	    → Set state: proposal_output
	    → End
→ A03 GeoResolverAgent
→ If/else: ${geo_resolution.last_output.geo_resolved}
  - If: A05 BaselineSearchPlanAgent
  - Else: A14A CustomerSuccessManagerAgent
    → Set state: customer_message_output
	    → A14 ProposalEditorAgent
	    → Set state: proposal_output
	    → End
→ A05A CoreTourApiCollectorAgent
→ A05B SupplementalTourApiCollectorAgent
→ A05D CandidateMergeDedupeAgent
→ A06 DataGapProfilerAgent
→ If/else: ${data_gap_profile.last_output.enrichment_needed}
  - If ENRICHMENT_NEEDED:
    → A07 ApiCapabilityRouterAgent
    → A07A TourApiDetailEnrichmentAgent
    → A07A2 TourApiIntroImageEnrichmentAgent
    → A07B VisualDataEnrichmentAgent
    → A07C RouteSignalEnrichmentAgent
    → A07D ThemeDataEnrichmentAgent
    → A08 EnrichmentResultMergeAgent
    → Set state: enrichment_output
    → A09 DataAnalystAgent
  - Else NO_ENRICHMENT_NEEDED:
    → A09 DataAnalystAgent
→ A10 ResearchAnalystAgent
→ A11 ProductManagerAgent
→ A12 BrandMarketingLeadAgent
→ A12B GrowthMarketingLeadAgent
→ A13 QAComplianceManagerAgent
→ Set state: qa_output
	→ A14 ProposalEditorAgent
	→ Set state: proposal_output
	→ End
```

NO_ENRICHMENT_NEEDED 경로에서는 A08을 거치지 않으므로 A09/A14가 `${enrichment_result_merge.last_output}`이 없거나 빈 값이어도 정상 경로로 취급해야 한다.
A09는 baseline evidence만으로 evidence card를 만든다.
Request Supported?의 Else와 Geo Resolved?의 Else는 A14A CustomerSuccessManagerAgent로 보낸다.
A14A는 고객에게 줄 요청 수정 안내를 구조화 JSON으로 작성하고 `customer_message_output`에 저장한다.
A14 ProposalEditorAgent는 `${customer_success_manager.last_output}`을 Markdown 안내로 편집해 최종 응답으로 출력한다.
A14 ProposalEditorAgent의 응답은 `proposal_output`에 저장한다.
포스터 branch는 상품 관련 Agent의 `${schema_name.last_output}`과 A14 text 출력을 저장한 `proposal_output`을 읽는다.
이전 여행 상품 추천 산출물이 없으면 A15 PosterBriefAgent가 먼저 여행 상품 추천을 생성하라는 안내를 출력한다.
판매용 상품 기획서, 운영 체크리스트, 마케팅 패키지 branch도 기존 여행 상품 추천 branch를 다시 실행하지 않는다.
판매용 상품 기획서와 운영 체크리스트 branch는 먼저 동일한 이름의 AreaCodeResolverAgent를 실행한다.
이 Agent는 현재 사용자 요청과 저장된 `proposal_output`, 상품 관련 `${schema_name.last_output}`을 읽어 선택 상품의 지역을 공식 관광지 시군구 코드표 기준 `areaCd`, `signguCd`로 변환한다.
마케팅 패키지 branch는 `관광사진 키워드 검색`만 사용하므로 AreaCodeResolverAgent를 거치지 않고 A25로 바로 연결한다.
Notion 저장 branch는 기존 사용자-facing Markdown state만 읽고, 여행 상품 추천 branch나 후속 실무 branch를 다시 실행하지 않는다. 저장 대상 state 원문 전체가 없거나 현재 문서가 불명확하면 다른 브랜치 state로 fallback하지 않는다.
후속 API 호출 Agent는 TourAPI 국문 관광정보의 legacy `area_code`, `sigungu_code`를 후속 API 코드로 쓰지 않는다.
공통 context parser Agent는 만들지 않는다.
Enrichment Needed?의 Else는 A14로 보내지 않는다.
보강이 필요 없다는 뜻이므로 A09부터 정상 추천 흐름을 계속 진행한다.

## Start state

| State | Type | Default | 용도 |
|---|---|---|---|
| `enrichment_output` | string | 빈 문자열 | A08 EnrichmentResultMergeAgent `last_message` 저장용. Agent 프롬프트 입력에는 이 이름을 직접 쓰지 않고 `${enrichment_result_merge.last_output}`을 쓴다. |
| `qa_output` | string | 빈 문자열 | A13 QAComplianceManagerAgent `last_message` 저장용. Agent 프롬프트 입력에는 이 이름을 직접 쓰지 않고 `${qa_compliance_manager.last_output}`을 쓴다. |
| `customer_message_output` | string | 빈 문자열 | A14A CustomerSuccessManagerAgent `last_message` 저장용. Agent 프롬프트 입력에는 `${customer_success_manager.last_output}` 사용 |
| `proposal_output` | string | 빈 문자열 | A14 최종 여행 상품 추천 Markdown. 포스터 branch에서 상품 번호와 사용자-facing 문구 확인용 |
| `poster_output` | string | 빈 문자열 | A17 최종 AI 포스터 생성 Markdown. Notion 저장 branch 재사용용 |
| `product_planner_proposal_output` | string | 빈 문자열 | A21 최종 판매용 상품 기획서 Markdown. Notion 저장 branch 재사용용 |
| `operations_manager_proposal_output` | string | 빈 문자열 | A24 최종 운영 체크리스트 Markdown. Notion 저장 branch 재사용용 |
| `marketing_strategist_proposal_output` | string | 빈 문자열 | A27 최종 마케팅 패키지 Markdown. Notion 저장 branch 재사용용 |

사용자 입력은 Start state로 만들지 않는다.
Ennoia의 `Workflow Input.messages`를 사용한다.
프롬프트에서는 `${messages}`로 참조한다.

## Set state 노드 상세

Set state 노드는 아래 이름, 대상 변수, 값으로 만든다.
`json_schema` 출력에서 if/else에 필요한 필드를 바로 읽을 수 있으면 StatusAgent를 만들지 않는다.
따라서 PreflightStatusAgent, GeoStatusAgent, GapRouteStatusAgent는 사용하지 않는다.
Set state의 값 표현식에서 `workflow.*`는 쓰지 않는다.
Ennoia CEL 평가 컨텍스트에는 `workflow`가 없을 수 있다.
대부분의 json_schema Agent 출력은 별도 Set state에 저장하지 않고 `${json_schema_name.last_output}`으로 직접 읽는다.
다만 캔버스 저장/확인용으로 A08과 A13 뒤에는 `last_message`를 각각 `enrichment_output`, `qa_output`에 저장한다.
이 두 state는 Agent 프롬프트 입력 변수명으로 직접 쓰지 않는다.
A14A의 구조화 안내 JSON과 A14 최종 Markdown처럼 후속 재사용이 필요한 값도 Set state에 저장하고, 값에는 `last_message`를 사용한다.

| Set state 노드 이름 | 대상 변수 | 값 |
|---|---|---|
| Set Enrichment Output | `enrichment_output` | `last_message` |
| Set QA Output | `qa_output` | `last_message` |
| Set Customer Message Output | `customer_message_output` | `last_message` |
| Set Proposal Output | `proposal_output` | `last_message` |
| Set Poster Output | `poster_output` | `last_message` |
| Set Product Planner Proposal Output | `product_planner_proposal_output` | `last_message` |
| Set Operations Manager Proposal Output | `operations_manager_proposal_output` | `last_message` |
| Set Marketing Strategist Proposal Output | `marketing_strategist_proposal_output` | `last_message` |

이전 방식의 `preflight_output`, `geo_output`, `search_plan_output`, `baseline_output`, `gap_output` 같은 JSON 문자열 state는 만들지 않는다.

## If/else 조건

Preflight:

```text
${preflight_validation.last_output.supported} == true
```

Geo:

```text
${geo_resolution.last_output.geo_resolved} == true
```

Gap:

```text
${data_gap_profile.last_output.enrichment_needed} == true
```

위 조건식은 json_schema structured output 필드를 직접 비교한다.
CEL 직접 입력 칸에서 `${...}` 표기가 다르면 UI가 생성한 표현식을 그대로 사용한다.
직접 `workflow.*`를 입력하지 않는다.

## A07 보강 lane 실행 위치

A07 보강 lane은 Orchestrator 자동 선택에 맡기지 않는다.
ApiCapabilityRouterAgent의 `orchestrator_instruction.call_agents`가 여러 Agent를 포함해도, Orchestrator 노드는 첫 번째로 적합하다고 판단한 Agent만 실행한 뒤 다음 단계로 빠질 수 있다.
따라서 A07A, A07A2, A07B~A07D는 모두 일반 Agent 노드로 만들고 아래 순서로 강제 통과시킨다.

```text
A07 ApiCapabilityRouterAgent
→ A07A TourApiDetailEnrichmentAgent
→ A07A2 TourApiIntroImageEnrichmentAgent
→ A07B VisualDataEnrichmentAgent
→ A07C RouteSignalEnrichmentAgent
→ A07D ThemeDataEnrichmentAgent
→ A08 EnrichmentResultMergeAgent
```

A07A, A07A2, A07B~A07D는 각자 `capability_routing.orchestrator_instruction.call_agents`에 자기 이름이 있으면 자기 lane API를 호출하고, 없으면 API 호출 없이 빈 `lane_enrichment`를 출력한다.
실제 호출할 API 커넥터는 `capability_routing.orchestrator_instruction.api_calls`를 우선한다.
이렇게 하면 `call_agents`에 `TourApiDetailEnrichmentAgent`, `TourApiIntroImageEnrichmentAgent`, `VisualDataEnrichmentAgent`, `ThemeDataEnrichmentAgent`가 동시에 있어도 각 Agent가 모두 실행된다.

A07A, A07A2, A07B~A07D 뒤에는 각각 Set state를 붙이지 않는다.
A08은 `${tourapi_detail_enrichment.last_output}`, `${tourapi_intro_image_enrichment.last_output}`, `${visual_data_enrichment.last_output}`, `${route_signal_enrichment.last_output}`, `${theme_data_enrichment.last_output}`을 직접 읽는다.

A07A, A07A2, A07B~A07D 개별 lane 출력은 A08에서만 직접 읽는다.
후속 A09와 A14는 개별 lane 결과가 아니라 A08이 만든 `${enrichment_result_merge.last_output}`을 읽는다.

Orchestrator 노드는 A07 보강 lane dispatcher로 사용하지 않는다.
복수 lane 실행이 필요한 요청에서 Orchestrator가 한 Agent만 실행하고 멈추는 것을 막기 위해, A07A, A07A2, A07B~A07D의 실행 여부 판단은 각 Agent 내부 프롬프트와 `call_agents` membership 체크로 처리한다.

실행 Agent:
- A07A TourApiDetailEnrichmentAgent
- A07A2 TourApiIntroImageEnrichmentAgent
- A07B VisualDataEnrichmentAgent
- A07C RouteSignalEnrichmentAgent
- A07D ThemeDataEnrichmentAgent

A07A, A07A2, A07B~A07D는 각자 자기 lane의 호출 판단, API 커넥터 호출, 정규화까지 수행한다.
A08 EnrichmentResultMergeAgent는 다섯 lane Agent의 last_output을 받아 하나의 `enrichment_summary`로 합친다.

## State 사용 기준

json_schema Agent 출력은 Agent 프롬프트 입력에서 `${schema_name.last_output}`으로 직접 연결한다.
예외적으로 A08/A13 뒤의 저장용 state `enrichment_output`, `qa_output`은 만들지만, 후속 Agent 프롬프트에는 이 state명을 직접 쓰지 않는다.
`customer_message_output`은 A14A 저장용, `proposal_output`은 A14 최종 Markdown의 포스터 branch 재사용용으로 Set state에 저장한다.
A21/A24/A27의 최종 Markdown도 Notion 저장 branch 재사용을 위해 각각 `product_planner_proposal_output`, `operations_manager_proposal_output`, `marketing_strategist_proposal_output`에 저장한다.
A17의 최종 포스터 Markdown도 Notion 저장 branch 재사용을 위해 `poster_output`에 저장한다.

if/else는 StatusAgent의 짧은 문자열이 아니라 `json_schema`가 보장한 boolean/string 필드를 직접 비교한다.

아래 state는 만들지 않는다.

| 만들지 않는 state | 이유 |
|---|---|
| `keyword_candidates_output` | A05B가 keyword/festival/stay를 `supplemental_candidates`로 통합 출력 |
| `optional_candidates_output` | A05C를 만들지 않음 |
| `merged_candidates_output` | A05D가 병합/중복 제거와 shortlist 선정을 한 번에 수행 |
| `final_markdown` | A14 출력은 포스터 branch 재사용을 위해 `proposal_output`으로 저장. 별도 `final_markdown` 이름은 만들지 않음 |

아래 state만 유지한다.

| 유지 state | 이유 |
|---|---|
| `enrichment_output` | A08 `last_message` 저장용. 후속 프롬프트 입력은 `${enrichment_result_merge.last_output}` 사용 |
| `qa_output` | A13 `last_message` 저장용. 후속 프롬프트 입력은 `${qa_compliance_manager.last_output}` 사용 |
| `customer_message_output` | A14A 구조화 안내 JSON의 `last_message` 저장용. A14는 `${customer_success_manager.last_output}`을 직접 읽어 Markdown으로 편집 |
| `proposal_output` | 사용자가 나중에 “3번 상품으로 포스터 만들어줘”라고 요청할 때 A15가 최종 사용자-facing 상품 문구와 번호를 확인 |
| `poster_output` | 사용자가 생성된 포스터 결과를 Notion 페이지로 저장할 때 A28이 사용 |
| `product_planner_proposal_output` | 사용자가 판매용 상품 기획서를 Notion 페이지로 저장할 때 A28이 사용 |
| `operations_manager_proposal_output` | 사용자가 운영 체크리스트를 Notion 페이지로 저장할 때 A28이 사용 |
| `marketing_strategist_proposal_output` | 사용자가 마케팅 패키지를 Notion 페이지로 저장할 때 A28이 사용 |

A05 계열은 baseline data 단계를 Ennoia용으로 쪼갠 것이다.
API 호출은 A05A, A05B에서 수행한다.
A05D는 API를 호출하지 않고 병합, 중복 제거, 지역 재필터, shortlist 선정을 한 번에 담당한다.

A06~A08 계열은 gap profiling, API capability routing, 5개 보강 lane, evidence fusion 전 보강 결과 병합 의미를 Ennoia용으로 쪼갠 것이다.
A07A, A07A2, A07B~A07D는 API 커넥터를 호출한다. A08은 API를 호출하지 않고 병합만 수행한다.

Classify는 Start 바로 다음에서 요청 유형 분기용으로 사용한다.
While과 User approval은 사용하지 않는다.
