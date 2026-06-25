# Ennoia Migration

PARAVOCA의 기존 `run` 워크플로우를 Ennoia 대화형 멀티에이전트 앱으로 옮기기 위한 문서다.

## 문서 규칙

- `Dxx_*.md`: Ennoia 구성 가이드
- `agent-prompts/Axx_*.md`: Agent 노드 시스템 메시지에 그대로 붙여넣는 프롬프트

`agent-prompts` 폴더의 문서는 설명용 문서가 아니다. 파일 내용 전체를 복사해서 Ennoia Agent 노드의 System Message에 붙여넣는다.

## 읽는 순서

1. `D00_CANVAS_FLOW_AND_STATE.md`
2. `D01_PROMPT_AND_NODE_INPUT_GUIDE.md`
3. `D02_AGENT_SETTINGS_MATRIX.md`
4. `D03_CURRENT_RUN_MODEL.md`
5. `D04_BUILD_PLAN.md`
6. `D05_MARKDOWN_OUTPUT_CONTRACT.md`
7. `D06_CATALOG_AND_DATA_STRATEGY.md`
8. `D07_POSTER_OUT_OF_SCOPE.md` (이전 결정 기록. 현재 포스터 branch는 `D12`를 따른다.)
9. `D08_SMOKE_TESTS.md`
10. `D09_BASELINE_API_CONNECTORS.md`
11. `D10_JSON_SCHEMA_AND_NODE_REDUCTION.md`
12. `D11_AGENT_PERSONA_TEAM.md`
13. `D12_POSTER_BRANCH_AND_IMAGE_API.md`
14. `D13_IMAGE_BRIDGE_API_SPEC.md`
15. `D14_FOLLOWUP_OPERATOR_BRANCHES.md`

## 기본 결정

- 리비전 기능은 구현하지 않는다.
- 포스터 생성은 Classify의 별도 branch에서 외부 이미지 생성 API 커넥터로 테스트 구현한다.
- Start 바로 다음에 Classify 노드를 두고 `여행 상품 추천해줘`, `그 내용으로 포스터 만들어줘`, `판매용 상품 기획서 만들어줘`, `운영 체크리스트 만들어줘`, `마케팅 패키지 만들어줘`, `노션 페이지로 만들어줘` 유형으로 분기한다.
- A07 보강 단계에는 Orchestrator 노드를 쓰지 않는다. A07A, A07A2, A07B~A07D 일반 Agent 노드를 순차 실행한다.
- 전체 흐름은 고정 순서의 Agent 체인으로 만든다.
- JSON Agent는 가능한 한 `json_schema` strict 출력으로 만든다.
- 여러 downstream에서 재사용하는 산출물만 `*_output` state에 저장한다.
- if/else는 StatusAgent가 아니라 `json_schema` structured output 필드를 직접 비교한다.
- PreflightStatusAgent, GeoStatusAgent, GapRouteStatusAgent는 만들지 않는다.
- 사용자 입력은 `Workflow Input.messages`를 사용하고 별도 `user_message` state를 만들지 않는다.
- 문서 폴더는 사용하지 않는다.
- 기존 run의 `TourAPI_법정동_후보` 전체 목록은 `A03_GEO_RESOLVER_AGENT.md` 시스템 메시지 안에 직접 포함한다.
- 기존 run의 baseline data 단계는 A05, A05A, A05B, A05D로 나눠 구현한다.
- A05A는 core area 후보를 수집하고, A05B는 keyword/stay 보조 후보를 기본 수집하며 festival은 eventStartDate가 있을 때 수집한다. A05D가 병합/중복 제거/지역 재필터와 최종 15개 shortlist 생성을 한 번에 수행한다.
- A05 BaselineSearchPlanAgent는 Ennoia의 오늘 날짜 추가 기능을 켜고, 시스템 프롬프트의 `### Current date is ...` 값을 기준으로 이번 달/다음 달/축제 기간을 계산한다.
- 기존 run의 보강 단계는 A06, A07, A07A, A07A2, A07B~A07D, A08로 나눠 구현한다.
- A07A, A07A2, A07B~A07D는 순차 실행되는 일반 Agent 노드로 만든다. A07의 call_agents에 자기 이름이 있으면 `api_calls`에 지정된 한국관광공사 API 커넥터만 호출하고, 없으면 빈 lane_enrichment를 출력한다. A08은 각 Agent의 `*.last_output`을 직접 읽어 5개 lane 출력을 병합한다.
- A09 이후는 공모전 제출용 프로젝트 팀처럼 구성한다. Data Analyst, Research Analyst, Product Manager, Brand Marketing Lead, Growth Marketing Lead, QA & Compliance Manager, Proposal Editor가 순서대로 산출물을 만든다.
- A14 ProposalEditorAgent는 성공 응답 마지막에 AI 포스터 생성 요청 예시를 안내한다.
- 포스터 branch는 A15 PosterBriefAgent, A16 PosterPromptBuilderAgent, A17 PosterImageGeneratorAgent 3개로 구성한다. A15는 저장된 여행상품 산출물을 포스터 브리프로 정리하고, A16은 기존 PARAVOCA 방식의 이미지 생성 프롬프트를 만들며, A17은 외부 이미지 생성 API 커넥터를 호출해 반환된 `image_url`을 HTML로 출력한다.
- 후속 실무 branch는 A18~A28과 A28R로 구성한다. 판매용 상품 기획서, 운영 체크리스트, 마케팅 패키지는 기존 `proposal_output`과 상품 관련 structured output을 재사용한다. Notion 저장 branch는 A28R이 저장 대상 payload를 정리하고 A28이 API 호출만 수행한다.
- 한국관광공사 MCP는 쓰지 않는다. A05와 A07A, A07A2, A07B~A07D의 모든 외부 데이터 조회는 Ennoia API 커넥터 기준이다.
- 워크플로우 규칙, 한국관광공사 API 필드 해석, 근거/QA 가드레일, 마케팅 기준은 Agent 시스템 프롬프트에 직접 포함한다.
