# D04. Build Plan

## 1. 문서 폴더

문서 폴더는 만들지 않는다.
기준 문서는 만들지 않고 Agent 시스템 프롬프트에 직접 포함한다.

`TourAPI_법정동_후보`는 `A03_GEO_RESOLVER_AGENT.md` 시스템 메시지에 전체 후보 목록으로 직접 포함한다.
GeoResolverAgent에는 문서 폴더와 한국관광공사 API 커넥터를 연결하지 않는다.

다른 규칙성 문서 폴더는 만들지 않는다.
`pv_workflow`, `pv_guardrails`, `kto_fields`, `pv_marketing`에 해당하던 내용은 각 Agent 시스템 프롬프트에 직접 포함한다.

## 2. Agent 만들기

A00~A14와 조기 종료 고객 안내용 A14A를 만든다.
A05 baseline 단계는 A05, A05A, A05B, A05D로 나눠 만든다.
A06~A08 보강 단계는 A06, A07, A07A, A07A2, A07B, A07C, A07D, A08로 나눠 만든다.
A09 이후는 공모전 제출용 프로젝트 팀 페르소나로 만든다: DataAnalystAgent, ResearchAnalystAgent, ProductManagerAgent, BrandMarketingLeadAgent, GrowthMarketingLeadAgent, QAComplianceManagerAgent, ProposalEditorAgent.
A15~A28 후속 branch는 포스터 생성, 판매용 상품 기획서, 운영 체크리스트, 마케팅 패키지, Notion 저장을 담당한다. Notion 저장은 A28R payload 정리와 A28 API 호출로 나눈다.
A01 PreflightStatusAgent, A04 GeoStatusAgent, A06S GapRouteStatusAgent는 만들지 않는다.

System Message에는 `agent-prompts/Axx_*.md` 파일 전체를 붙여넣는다.
A07A, A07A2, A07B~A07D 출력은 별도 Set state 없이 각 Agent의 `${schema_name.last_output}`을 A08에 직접 넘긴다.
A07 보강 단계에는 Orchestrator 노드를 쓰지 않는다.
ApiCapabilityRouterAgent 뒤에서 A07A, A07A2, A07B~A07D 일반 Agent 노드를 순차로 모두 통과시킨다.

응답 포맷:

```text
A00, A02~A03, A05, A05A, A05B, A05D, A06, A07, A07A, A07A2, A07B~A07D, A08~A13, A14A, A15~A16, A17R, A18, A20, A22, A23, A25, A26, A28R: json_schema
A14, A17, A21, A24, A27, A28: text
```

## 3. 캔버스 노드 순서

```text
Start
→ Classify Request Type
  - 여행 상품 추천해줘: A00
  - 그 내용으로 포스터 만들어줘: A15
  - 판매용 상품 기획서 만들어줘: AreaCodeResolverAgent
  - 운영 체크리스트 만들어줘: AreaCodeResolverAgent
  - 마케팅 패키지 만들어줘: A25
  - 노션 페이지로 만들어줘: A28R → A28
→ A00
→ If/else ${preflight_validation.last_output.supported} == true
→ A02
→ A03
→ If/else ${geo_resolution.last_output.geo_resolved} == true
→ A05
→ A05A
→ A05B
→ A05D
→ A06
→ If/else ${data_gap_profile.last_output.enrichment_needed} == true
  - NO_ENRICHMENT_NEEDED:
    → A09
  - ENRICHMENT_NEEDED:
    → A07
    → A07A
    → A07A2
    → A07B
    → A07C
    → A07D
    → A08
    → Set state enrichment_output
    → A09
→ A10
→ A11
→ A12 BrandMarketingLeadAgent
→ A12B GrowthMarketingLeadAgent
→ A13
→ Set state qa_output
→ A14
→ Set state proposal_output
→ End
```

State 기준:
- json_schema Agent 출력은 `${schema_name.last_output}`으로 직접 참조한다.
- JSON 결과를 `preflight_output`, `baseline_output` 같은 별도 state로 옮기지 않는다.
- 예외적으로 A08 `last_message`는 `enrichment_output`, A13 `last_message`는 `qa_output`에 저장한다.
- 다만 Agent 프롬프트 입력에는 `enrichment_output`, `qa_output`을 직접 쓰지 않고 `${enrichment_result_merge.last_output}`, `${qa_compliance_manager.last_output}`을 쓴다.
- text 출력 중 `CustomerSuccessManagerAgent`는 `customer_message_output`, `ProposalEditorAgent`는 `proposal_output`으로 저장한다.
- A17/A21/A24/A27의 text 출력은 각각 `poster_output`, `product_planner_proposal_output`, `operations_manager_proposal_output`, `marketing_strategist_proposal_output`으로 저장한다.
- `Set Final Markdown`은 만들지 않는다.

## 3-1. A05D 구성 기준

A05D CandidateMergeDedupeAgent는 보조 후보 병합, 중복 제거, 지역 재필터, shortlist 선정을 한 번에 수행한다.
A05E CandidateShortlistAgent는 만들지 않는다.

1. A05D CandidateMergeDedupeAgent 시스템 메시지는 `agent-prompts/A05D_CANDIDATE_MERGE_DEDUPE_AGENT.md` 전체 내용으로 둔다.
2. A05D 응답 포맷은 D10의 `candidate_merge_dedupe` json_schema를 사용한다.
3. A05D 출력 최상위 키는 `source_items`다.
4. 캔버스 연결은 `A05B SupplementalTourApiCollectorAgent → A05D CandidateMergeDedupeAgent → A06 DataGapProfilerAgent`로 둔다.
5. A05D 출력은 `${candidate_merge_dedupe.last_output}`으로 후속 Agent가 직접 읽는다.
6. `merged_candidates_output` state는 만들지 않는다.
7. A06 이후 Agent들은 `${candidate_merge_dedupe.last_output.source_items}`를 읽는다.

## 3-2. A05A 정렬 기준

`관광정보 지역기반 목록` API 커넥터는 제목순 첫 페이지 고정을 피하도록 아래 변수형 URL을 사용한다.

```text
https://apis.data.go.kr/B551011/KorService2/areaBasedList2?serviceKey=${serviceKey}&numOfRows=${numOfRows}&pageNo=${pageNo}&MobileOS=ETC&MobileApp=PARAVOCAAX&_type=json&arrange=${arrange}&contentTypeId=${contentTypeId}&lDongRegnCd=${lDongRegnCd}&lDongSignguCd=${lDongSignguCd}
```

A05A는 같은 커넥터를 아래 두 조합으로 호출한다.

```text
contentTypeId=12, arrange=Q, pageNo=1, numOfRows=20
contentTypeId=28, arrange=Q, pageNo=1, numOfRows=20
```

TourAPI에는 랜덤 정렬 코드가 없으므로, 대표 이미지가 있고 최근 수정된 관광지 20개와 레포츠 20개를 가져와 제목순 첫 페이지 편향과 생성일순 저품질 후보 유입을 줄인다.
raw 최대치는 40개지만 지역 내 실제 결과 수, 중복, 부적합 후보 제외 때문에 최종 `core_candidates`는 40개보다 적을 수 있다.

## 4. If/else 조건

Preflight:

```text
${preflight_validation.last_output.supported} == true
```

Preflight If:

```text
A02 PlannerAgent
```

Preflight Else:

```text
A14A CustomerSuccessManagerAgent
→ Set state customer_message_output
→ A14 ProposalEditorAgent
→ End
```

Geo:

```text
${geo_resolution.last_output.geo_resolved} == true
```

Geo If:

```text
A05 BaselineSearchPlanAgent
→ A05A CoreTourApiCollectorAgent
→ A05B SupplementalTourApiCollectorAgent
→ A05D CandidateMergeDedupeAgent
```

Geo Else:

```text
A14A CustomerSuccessManagerAgent
→ Set state customer_message_output
→ A14 ProposalEditorAgent
→ End
```

Gap:

```text
${data_gap_profile.last_output.enrichment_needed} == true
```

Gap If:

```text
A07 ApiCapabilityRouterAgent
→ A07A TourApiDetailEnrichmentAgent
→ A07A2 TourApiIntroImageEnrichmentAgent
→ A07B VisualDataEnrichmentAgent
→ A07C RouteSignalEnrichmentAgent
→ A07D ThemeDataEnrichmentAgent
→ A08 EnrichmentResultMergeAgent
→ A09 DataAnalystAgent
```

A07A, A07A2, A07B~A07D는 모두 일반 Agent 노드로 만든다.
분배 기준은 직전 A07 출력의 `capability_routing.orchestrator_instruction.call_agents`다.
각 Agent는 자기 이름이 `call_agents`에 없으면 API를 호출하지 않고 빈 `lane_enrichment`를 출력한다.
A07A, A07A2, A07B~A07D는 순차 실행한다.
Orchestrator dispatcher는 사용하지 않는다.
`call_agents`에 여러 Agent가 들어와도 Orchestrator가 하나만 실행하고 멈출 수 있으므로, 각 lane Agent가 직접 자기 실행 여부를 판단하게 한다.
A07A, A07A2, A07B~A07D 출력은 `${tourapi_detail_enrichment.last_output}`, `${tourapi_intro_image_enrichment.last_output}`, `${visual_data_enrichment.last_output}`, `${route_signal_enrichment.last_output}`, `${theme_data_enrichment.last_output}`으로 A08에 직접 입력한다.
이 구조는 Orchestrator의 단일 선택 문제를 피한다.

Gap Else:

```text
A09 DataAnalystAgent
```

Gap Else는 실패 경로가 아니다.
보강이 필요 없다는 뜻이므로 A14로 바로 보내지 않고 A09 이후 정상 추천 흐름을 계속 진행한다.

## 5. 실패 처리

Preflight 실패:

```text
A14A가 고객에게 요청 수정 안내 작성
A14가 `${customer_success_manager.last_output}`을 Markdown 안내로 편집해 최종 출력
```

Geo 실패:

```text
A14A가 후보 지역 또는 다시 입력할 예시를 제시하고 어느 지역인지 더 구체적으로 입력하라고 안내
A14가 `${customer_success_manager.last_output}`을 Markdown 안내로 편집해 최종 출력
```

A05 계열 데이터 부족:

```text
A06~A13이 빈 배열 또는 blocked JSON 반환
A14가 데이터 부족 안내 작성
```

보강 API 호출 실패:

```text
A07A, A07A2, A07B~A07D가 failed_calls에 기록
A09가 remaining_gaps와 claim 제한으로 이어받음
A14는 최종 추천 답변에서 확인 필요 사항으로 풀어쓴다
```
