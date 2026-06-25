# D06. Catalog and Data Strategy

## 핵심 결정

문서 검색/RAG는 사용하지 않는다.
한국관광공사 MCP는 사용하지 않는다.

`TourAPI_법정동_후보` 전체 목록은 `A03_GEO_RESOLVER_AGENT.md` 시스템 메시지 안에 직접 포함한다.
GeoResolverAgent는 그 후보 목록 안에서 지역 코드를 고른다.

## 데이터 소스 역할

| 데이터 소스 | 사용 위치 | 역할 |
|---|---|---|
| `TourAPI_법정동_후보` 임베디드 목록 | A03 GeoResolverAgent | 지역 후보 확정 |
| 한국관광공사 API 커넥터 응답 | A05A~A05B | 초기 관광 후보 데이터 수집 |
| 한국관광공사 API 커넥터 응답 | A07A, A07A2, A07B~A07D | 상세/소개/이미지/코스/신호/테마 데이터 보강 |
| 앞 Agent의 `*_output` state | A02~A14 | 여러 downstream에서 재사용되는 이전 단계 결과 전달 |
| 모델의 일반 추론 | 전체 | 구조화, 요약, 상품 구성 |

일반 추론은 근거 없는 관광 데이터 생성에 쓰지 않는다.
일반 추론은 지역 상위 행정구역 판단, 구조화, 요약, 상품 구성에만 쓴다.

## GeoResolver 방식

GeoResolverAgent는 시스템 메시지 안의 후보 목록을 기준으로 지역을 확정한다.

```text
사용자 지역 표현
→ A03 시스템 메시지 안의 TourAPI_법정동_후보 전체 목록 확인
→ 후보 목록에 직접 있는 시도/시군구면 해당 후보 선택
→ 후보 목록에 직접 없는 섬/관광지/생활권/동네명이면 일반 지식으로 상위 시군구 판단
→ 상위 시군구가 후보 목록에 있으면 해당 후보 선택
→ 후보가 여러 개면 unresolved
```

## 한국관광공사 API 사용 위치

| Agent | 사용 목적 |
|---|---|
| A05 BaselineSearchPlanAgent | API 호출 없이 core/supplemental 수집 계획 작성 |
| A05A CoreTourApiCollectorAgent | API 커넥터로 `areaBasedList2` contentTypeId=12, 28 수집 |
| A05B SupplementalTourApiCollectorAgent | API 커넥터로 `searchKeyword2`/`searchStay2` 기본 수집, `eventStartDate`가 있으면 `searchFestival2` 수집 |
| A05D CandidateMergeDedupeAgent | 후보 병합, content_id 중복 제거, 지역 재필터, 상품화에 쓸 최종 source_items 최대 15개 선정 |
| A06 DataGapProfilerAgent | API 호출 없이 보강 gap 식별 |
| A07 ApiCapabilityRouterAgent | gap을 5개 보강 lane으로 분배하고 Agent별 호출 API를 지정 |
| A07A, A07A2, A07B~A07D enrichment agents | A07 출력의 call_agents와 api_calls를 보고 자기 lane 필요 시 지정 API 커넥터 호출과 정규화 수행 |
| A08 EnrichmentResultMergeAgent | lane 결과를 하나의 enrichment_summary로 병합 |

GeoResolverAgent에는 한국관광공사 API 커넥터를 연결하지 않는다.
GeoResolverAgent는 시스템 메시지 안의 `TourAPI_법정동_후보`만 사용한다.

## 근거 규칙

- GeoResolverAgent는 `TourAPI_법정동_후보`에 없는 지역 코드를 만들지 않는다.
- `ldong_regn_cd`, `ldong_signgu_cd`는 법정동 코드 체계다.
- 한국관광공사 API 응답에 없는 관광지, 행사, 운영시간, 요금, 휴무일, 예약, 인증, 수상, 제휴는 만들지 않는다.
- A05A~A05B는 API 응답 전체를 그대로 넘기지 않고 다음 단계에 필요한 최소 후보 필드만 넘긴다.
- A05B는 지역이 확정되면 keyword와 stay를 기본 호출한다.
- A05B는 eventStartDate가 있으면 festival을 호출한다.
- A05의 상대 날짜 계산은 Ennoia의 오늘 날짜 추가 기능으로 삽입되는 `### Current date is ...` 값을 기준으로 한다.
- A05B는 날짜를 계산하지 않고 A05가 출력한 eventStartDate/eventEndDate만 사용한다.
- A05B는 호출당 numOfRows=10으로 제한하되, keyword_queries는 최대 5개까지 허용한다.
- A05D는 content_id 기준으로 중복 제거하고 collection_sources를 합친 뒤 최종 source_items를 최대 15개로 제한한다.
- 후보 수 요약은 출력하지 않는다. 후보 수와 콘텐츠 타입별 개수는 다음 단계 필수 입력이 아니고 LLM이 계산 실수하기 쉽다.
- A06은 `missing_overview`를 쓰지 않고 `missing_detail_info`로 통합한다.
- A06은 `route_status`와 `enrichment_needed`를 함께 출력해 보강 분기를 직접 제어한다.
- A07A, A07A2, A07B~A07D는 자기 lane의 API 커넥터만 호출한다.
- A07A, A07A2, A07B~A07D는 Orchestrator가 아니라 순차 실행되는 일반 Agent 노드로 만든다. 자기 Agent 이름이 A07의 call_agents에 없으면 API를 호출하지 않는다.
- 실제 호출 API는 A07의 `orchestrator_instruction.api_calls`를 우선한다.
- A07A, A07A2, A07B~A07D 출력은 Set state로 저장하지 않고 A08이 각 Agent의 `${schema_name.last_output}`을 직접 읽는다.
- A08은 API를 호출하지 않고 병합만 수행한다.
- 운영 정보가 없으면 `확인 필요`로 둔다.
- 마케팅 문구는 확인된 후보와 근거 카드의 claim만 사용한다.
- QA Agent가 금지한 표현은 최종 Markdown에서 제거한다.
