# D03. Current Run Model

## 기존 run 핵심 흐름

기준 파일:

```text
backend/app/agents/workflow.py
backend/app/agents/state.py
backend/app/api/routes_runs.py
```

기존 흐름:

```text
preflight
→ planner
→ geo resolver
→ baseline data
→ data gap profiler
→ enrichment planning
→ enrichment execution
→ evidence fusion
→ research synthesis
→ product strategy
→ marketing strategy
→ QA/compliance
→ final report
```

## Ennoia 대응

| 기존 코드 단계 | Ennoia Agent |
|---|---|
| preflight validation | A00 PreflightValidationAgent |
| preflight branch value | A00 structured output의 `supported` |
| planner | A02 PlannerAgent |
| geo resolver | A03 GeoResolverAgent |
| geo branch value | A03 structured output의 `geo_resolved` |
| baseline 수집 계획 | A05 BaselineSearchPlanAgent |
| areaBasedList2 core 수집 | A05A CoreTourApiCollectorAgent |
| searchKeyword2/searchFestival2/searchStay2 보조 수집 | A05B SupplementalTourApiCollectorAgent |
| 후보 병합/중복 제거/지역 재필터/shortlist 선정 | A05D CandidateMergeDedupeAgent |
| data gap profiler | A06 DataGapProfilerAgent |
| gap branch value | A06 structured output의 `route_status` |
| API capability router | A07 ApiCapabilityRouterAgent |
| detail 보강 lane | A07A TourApiDetailEnrichmentAgent |
| intro/image 보강 lane | A07A2 TourApiIntroImageEnrichmentAgent |
| visual 보강 lane | A07B VisualDataEnrichmentAgent |
| route/signal 보강 lane | A07C RouteSignalEnrichmentAgent |
| theme 보강 lane | A07D ThemeDataEnrichmentAgent |
| lane 결과 병합 | A08 EnrichmentResultMergeAgent |
| data analysis | A09 DataAnalystAgent |
| research | A10 ResearchAnalystAgent |
| product management | A11 ProductManagerAgent |
| brand marketing | A12 BrandMarketingLeadAgent |
| growth marketing | A12B GrowthMarketingLeadAgent |
| QA/compliance | A13 QAComplianceManagerAgent |
| customer success fallback | A14A CustomerSuccessManagerAgent |
| final proposal assembly | A14 ProposalEditorAgent |
| poster brief assembly | A15 PosterBriefAgent |
| poster prompt building | A16 PosterPromptBuilderAgent |
| poster image generation | A17 PosterImageGeneratorAgent |

## 이식하지 않는 것

| 기존 기능 | Ennoia 처리 |
|---|---|
| 리비전 | 제외 |
| 웹 UI 탭별 결과 | 최종 Markdown 하나로 통합 |
| 포스터 생성 | Classify의 별도 branch에서 외부 이미지 생성 API 커넥터로 테스트 구현 |
| Python 내부 검증 코드 | 프롬프트 가드레일과 QA Agent로 대체 |
| TourAPI 직접 호출 코드 | A05A~A05B와 A07A, A07A2, A07B~A07D는 한국관광공사 API 커넥터 사용 |

## 상태 이식 원칙

기존 코드의 run state를 Ennoia Set state로 그대로 옮기지 않는다.
`json_schema` Agent 출력은 Ennoia의 `${schema_name.last_output}`으로 직접 참조한다.

```text
planner.last_output
geo_resolution.last_output
baseline_search_plan.last_output
core_tourapi_collector.last_output
supplemental_tourapi_collector.last_output
candidate_merge_dedupe.last_output
data_gap_profile.last_output
api_capability_router.last_output
tourapi_detail_enrichment.last_output
visual_data_enrichment.last_output
route_signal_enrichment.last_output
theme_data_enrichment.last_output
enrichment_result_merge.last_output
data_analyst.last_output
research_analyst.last_output
product_manager.last_output
brand_marketing_lead.last_output
growth_marketing_lead.last_output
qa_compliance_manager.last_output
poster_brief.last_output
poster_prompt.last_output
```

Set state는 후속 재사용 또는 캔버스 저장/확인이 필요한 경우에만 사용한다.
현재 유지하는 state는 `enrichment_output`, `qa_output`, `customer_message_output`, `proposal_output`, `poster_output`, `product_planner_proposal_output`, `operations_manager_proposal_output`, `marketing_strategist_proposal_output`이다.
`enrichment_output`과 `qa_output`은 각각 A08/A13의 `last_message` 저장용이며, Agent 프롬프트 입력에는 직접 쓰지 않는다.
후속 Agent 입력은 `${enrichment_result_merge.last_output}`, `${qa_compliance_manager.last_output}`을 사용한다.
`customer_message_output`은 A14A 구조화 안내 JSON의 `last_message` 저장용이며, A14는 `${customer_success_manager.last_output}`을 직접 읽어 Markdown으로 편집한다.
`proposal_output`은 A14 최종 Markdown의 후속 포스터 branch 재사용용이다.
`poster_output`, `product_planner_proposal_output`, `operations_manager_proposal_output`, `marketing_strategist_proposal_output`은 A28R Notion 저장 payload 구성용이다.
if/else도 state 문자열을 파싱하지 않고 structured output 필드를 직접 비교한다.

## GeoResolver 이식 원칙

기존 run은 `tourapi_ldong_codes` 테이블을 읽어 `TourAPI_법정동_후보` 전체를 GeoResolver 프롬프트에 넣고, LLM이 그 후보 안에서 코드를 고르게 한다.

관련 코드:

```text
backend/app/agents/workflow.py::_geo_catalog_options_for_prompt
backend/app/agents/workflow.py::_geo_resolution_prompt
backend/app/agents/geo_resolver.py::load_ldong_catalog
```

Ennoia GUI 캔버스에서는 DB 테이블을 직접 읽을 수 없으므로 `tourapi_ldong_codes`의 281개 후보를 `A03_GEO_RESOLVER_AGENT.md` 시스템 메시지에 직접 넣는다.
즉 Ennoia에서도 기존 run처럼 GeoResolver LLM 프롬프트 안에 전체 `TourAPI_법정동_후보`가 들어간다.

현재 GUI 방식의 역할 분리:

```text
1. GeoResolverAgent: 시스템 메시지의 TourAPI_법정동_후보에서 지역 후보를 고르고 모호하면 unresolved
2. BaselineSearchPlanAgent: 기존 run의 baseline 수집을 Ennoia에서 어떻게 나눠 실행할지 계획
3. CoreTourApiCollectorAgent: areaBasedList2 contentTypeId=12, 28 수집
4. SupplementalTourApiCollectorAgent: searchKeyword2/searchFestival2/searchStay2 보조 수집
5. CandidateMergeDedupeAgent: 후보 병합, content_id 중복 제거, 지역 재필터 후 최종 source_items를 최대 15개로 정리
6. DataGapProfilerAgent: source_items의 보강 공백 진단
7. ApiCapabilityRouterAgent: gap을 detail, intro/image, visual, route/signal, theme lane으로 분배
8. A07A, A07A2, A07B~A07D: 순차 실행되는 일반 Agent 노드로 만들되, A07 출력의 orchestrator_instruction.call_agents에 자기 Agent 이름이 없으면 API를 호출하지 않고 빈 lane_enrichment 출력
9. A07A, A07A2, A07B~A07D 출력은 Set state로 저장하지 않고 A08이 각 lane의 `${schema_name.last_output}`을 직접 읽음
10. EnrichmentResultMergeAgent: 다섯 lane 출력을 하나의 enrichment_summary로 병합
12. 이후 Agent: 근거 융합, 상품화, QA, Markdown 출력
```

GeoResolverAgent는 시스템 메시지의 `TourAPI_법정동_후보`에 없는 지역 코드를 만들면 안 된다.

기존 run과 완전히 같은 구조화 카탈로그 주입까지 필요하면 아래 중 하나가 필요하다.

```text
1. GeoCatalog API를 별도로 만들어 전체 법정동 카탈로그를 구조화 조회한다.
2. Ennoia의 코드 기반 멀티에이전트로 기존 GeoResolver 로직을 이식한다.
```
