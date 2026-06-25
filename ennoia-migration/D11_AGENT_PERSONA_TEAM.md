# D11. Agent Persona Team

## 목적

A09 이후 단계는 기능명 Agent가 아니라 공모전 제출용 프로젝트 팀처럼 보이도록 직원 페르소나를 입힌다.
각 Agent는 실제 채용한 담당자처럼 하나의 책임을 갖고, 앞 단계 산출물을 받아 다음 담당자에게 넘긴다.

## 후반부 프로젝트 팀

| 단계 | Agent 이름 | 직원 페르소나 | 책임 | 출력 재사용 |
|---|---|---|---|---|
| A09 | DataAnalystAgent | Data Analyst | 후보, gap, 보강 결과를 검증 가능한 근거 카드로 정리 | `${data_analyst.last_output}` |
| A10 | ResearchAnalystAgent | Research Analyst | 지역 맥락, 타깃 인사이트, 시즌성, 상품 기회를 리서치 브리프로 요약 | `${research_analyst.last_output}` |
| A11 | ProductManagerAgent | Product Manager | 요청 상품 개수에 맞춰 상품명, 콘셉트, 동선, 포함 장소, 리스크를 설계 | `${product_manager.last_output}` |
| A12 | BrandMarketingLeadAgent | Brand Marketing Lead | 상품별 포지셔닝, 랜딩 구성, FAQ, SNS 카피, 허용 claim을 작성 | `${brand_marketing_lead.last_output}` |
| A12B | GrowthMarketingLeadAgent | Growth Marketing Lead | 채널 우선순위, 전환 실험, 측정 지표, 리스크 제어를 설계 | `${growth_marketing_lead.last_output}` |
| A13 | QAComplianceManagerAgent | QA & Compliance Manager | 근거 없는 주장, 과장 표현, 운영 정보 미확정 리스크를 검수 | `${qa_compliance_manager.last_output}` + `qa_output` 저장 |
| A14A | CustomerSuccessManagerAgent | Customer Success Manager | 요청이 지원되지 않거나 지역이 모호할 때 고객 안내 메시지 작성 | `customer_message_output` |
| A14 | ProposalEditorAgent | Proposal Editor | 사용자가 요청한 여행 상품 추천 Markdown 답변을 최종 편집 | `proposal_output` |

## 실행 순서

```text
A08 EnrichmentResultMergeAgent
→ Set state enrichment_output
→ A09 DataAnalystAgent
→ A10 ResearchAnalystAgent
→ A11 ProductManagerAgent
→ A12 BrandMarketingLeadAgent
→ A12B GrowthMarketingLeadAgent
→ A13 QAComplianceManagerAgent
→ Set state qa_output
→ A14 ProposalEditorAgent
→ Set state proposal_output
→ End
```

조기 종료 경로:

```text
Request Supported? Else 또는 Geo Resolved? Else
→ A14A CustomerSuccessManagerAgent
→ Set state customer_message_output
→ A14 ProposalEditorAgent
→ End
```

## 설계 원칙

- 이름은 직원 역할처럼 보이게 하되, 출력 JSON의 핵심 계약은 유지한다.
- BrandMarketingLeadAgent와 GrowthMarketingLeadAgent를 분리해 “메시지/브랜드”와 “실험/전환”을 나눈다.
- QAComplianceManagerAgent는 두 마케팅 산출물을 모두 검수한다.
- `enrichment_output`과 `qa_output` Set state는 각각 A08/A13의 `last_message` 저장용으로 유지한다.
- Agent 프롬프트 입력에는 `enrichment_output`, `qa_output`을 직접 쓰지 않고 `${enrichment_result_merge.last_output}`, `${qa_compliance_manager.last_output}`을 사용한다.
- CustomerSuccessManagerAgent는 정상 추천을 만들 수 없는 요청에서 고객이 다시 입력할 수 있도록 안내한다.
- ProposalEditorAgent는 새 사실을 만들지 않고 앞선 직원들의 산출물을 사용자-facing 여행 상품 추천 답변으로 편집한다.
- A14 출력은 `final_markdown`이 아니라 `proposal_output`으로 저장한다. 이는 포스터 branch에서 사용자가 본 상품 번호와 문구를 재사용하기 위한 것이다.
- PosterBriefAgent는 후속 포스터 요청에서 상품 번호, 포함 항목, 참고 이미지를 해석해 포스터 브리프만 만든다.
- PosterPromptBuilderAgent는 포스터 브리프가 준비된 경우에만 기존 PARAVOCA 방식의 이미지 생성 프롬프트를 만든다.
- PosterImageGeneratorAgent는 포스터 프롬프트가 준비된 경우에만 이미지 생성 API 커넥터를 호출하고, 반환된 `image_url`을 사용자-facing Markdown/HTML로 보여준다.
