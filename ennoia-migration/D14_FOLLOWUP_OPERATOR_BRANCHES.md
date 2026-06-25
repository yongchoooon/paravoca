# D14. 후속 실무 Branch 설계

이 문서는 A14 여행 상품 추천 이후 사용자가 후속 요청을 했을 때 실행되는 실무 branch를 정리한다.

## Classify 카테고리

Start 바로 다음 `Classify Request Type`에는 아래 카테고리를 둔다.

| 카테고리 | 연결 |
|---|---|
| `여행 상품 추천해줘` | A00 PreflightValidationAgent |
| `그 내용으로 포스터 만들어줘` | A15 PosterBriefAgent |
| `판매용 상품 기획서 만들어줘` | AreaCodeResolverAgent |
| `운영 체크리스트 만들어줘` | AreaCodeResolverAgent |
| `마케팅 패키지 만들어줘` | A25 MarketingStrategistVisualSignalAgent |
| `노션 페이지로 만들어줘` | A28R NotionPagePayloadBuilderAgent → A28 NotionPagePublishAgent |

`노션 페이지로 만들어줘` 카테고리 예시:
- 노션 페이지로 만들어줘
- 방금 내용을 Notion 문서로 저장해줘
- 지금 내용 노션에 정리해줘
- 방금 나온 내용을 노션 페이지로 만들어줘

공통 context parser Agent는 만들지 않는다.
판매용 상품 기획서와 운영 체크리스트 branch의 AreaCodeResolverAgent가 사용자 요청, `proposal_output`, 기존 상품 관련 `${schema_name.last_output}`에서 상품 번호와 선택 상품 지역을 해석하고 공식 관광지 시군구 코드표 기준 `areaCd`, `signguCd`를 출력한다.
마케팅 패키지 branch는 `관광사진 키워드 검색`만 사용하므로 AreaCodeResolverAgent를 거치지 않는다.
Notion 저장 branch는 저장된 사용자-facing Markdown state만 사용하므로 별도 분석 Agent를 거치지 않는다.

## A14 마지막 안내

A14 ProposalEditorAgent는 정상 추천 응답 마지막에 `# 앞으로 가능한 것` 섹션을 붙인다.
하위 섹션은 아래 순서다.

1. AI 포스터 만들기
2. 판매용 상품 기획서 만들기
3. 운영 체크리스트 만들기
4. 마케팅 패키지 만들기
5. Notion 문서로 저장하기

포스터 안내는 A15~A17 기존 branch를 따른다.
2~5번 후속 기능 안내는 각각 사용자 예시 3개를 제공한다.

## 판매용 상품 기획서 branch

```text
AreaCodeResolverAgent
→ A18 ProductPlannerRelatedRouteAnalystAgent
→ A20 ProductPlannerSalesPackageAgent
→ A21 ProductPlannerProposalEditorAgent
→ End
```

| Agent | 역할 | API |
|---|---|---|
| AreaCodeResolverAgent | 선택 상품 지역을 공식 관광지 시군구 코드표 기준 `areaCd`, `signguCd`로 변환 | 없음 |
| A18 ProductPlannerRelatedRouteAnalystAgent | 선택 상품의 장소 기반 연관 관광지, 선택 장소, 대체 장소 후보 분석 | 연관관광지 키워드 검색 |
| A20 ProductPlannerSalesPackageAgent | 판매 가능한 상품 구조로 변환 | 없음 |
| A21 ProductPlannerProposalEditorAgent | 여행사 상품기획자용 Markdown 기획서 편집 | 없음 |

사용자에게 보여줄 정보:
- 상품 유형
- 권장 소요 시간
- 핵심 고객
- 상품화 판단
- 연관 관광지 확장 후보
  - 필수/확장/대체 구분으로 후보 표시
- 추천 판매 패키지
- 상품기획자 메모

## 운영 체크리스트 branch

```text
AreaCodeResolverAgent
→ A22 OperationsManagerCrowdingRiskAnalystAgent
→ A23 OperationsManagerRunbookAgent
→ A24 OperationsManagerProposalEditorAgent
→ End
```

| Agent | 역할 | API |
|---|---|---|
| AreaCodeResolverAgent | 선택 상품 지역을 공식 관광지 시군구 코드표 기준 `areaCd`, `signguCd`로 변환 | 없음 |
| A22 OperationsManagerCrowdingRiskAnalystAgent | 선택 상품 장소의 집중률/혼잡 예측 보조 신호 분석 | 관광지 집중률 예측 |
| A23 OperationsManagerRunbookAgent | 현장 운영 체크리스트와 진행 문서 생성 | 없음 |
| A24 OperationsManagerProposalEditorAgent | 운영 담당자용 Markdown 운영안 편집 | 없음 |

사용자에게 보여줄 정보:
- 혼잡/날씨/예약 리스크 표
- 혼잡도 신호 차트
- 사전 확인 체크리스트
- 당일 운영 타임라인
- 우천/혼잡/예약 변동 대응
- 고객 안내 문자
- 인솔자 메모
- 예상 문의 답변

## 마케팅 패키지 branch

```text
A25 MarketingStrategistVisualSignalAgent
→ A26 MarketingStrategistCampaignPackageAgent
→ A27 MarketingStrategistProposalEditorAgent
→ End
```

| Agent | 역할 | API |
|---|---|---|
| A25 MarketingStrategistVisualSignalAgent | 상품 장소와 테마 기준으로 상세페이지, 블로그, SNS 시각 소재 후보 분석 | 관광사진 키워드 검색 |
| A26 MarketingStrategistCampaignPackageAgent | 관광사진 `image_url`을 직접 확인해 광고 카피, SNS, 블로그, 랜딩페이지, A/B 테스트 생성 | 없음 |
| A27 MarketingStrategistProposalEditorAgent | 관광사진 `image_url` 미리보기와 마케팅 담당자용 Markdown 마케팅 패키지 편집 | 없음 |

사용자에게 보여줄 정보:
- 포지셔닝
- 시각 소재와 메시지 방향
- 관광사진 이미지 미리보기
- 광고 카피 5종
- 블로그 제목 10개
- 인스타그램 피드/릴스 문구
- 랜딩페이지 구성: 표 본문 6줄
- A/B 테스트 보드
- 표현 리스크와 검증 항목: 표 본문 4줄
- `타깃별 메시지`, `채널 적합도`는 별도 섹션으로 출력하지 않음

## Notion 저장 branch

```text
A28R NotionPagePayloadBuilderAgent
→ A28 NotionPagePublishAgent
→ End
```

| Agent | 역할 | API |
|---|---|---|
| A28R NotionPagePayloadBuilderAgent | 저장된 사용자-facing Markdown 중 요청에 맞는 문서를 선택하고 Notion 요청 payload 생성 | 없음 |
| A28 NotionPagePublishAgent | A28R payload로 Notion 페이지 생성 후 링크만 출력 | Notion 페이지 생성 |

정확 저장 원칙:
- A28R은 긴 Markdown 본문을 다시 쓰지 않고 저장 대상과 payload만 정리한다. 원문 전체를 확인할 수 없으면 일부 저장이나 요약 저장을 하지 않는다.
- A28은 문서 선택이나 본문 재작성 없이 A28R payload로 API 커넥터만 호출한다.
- Notion 페이지 생성 커넥터의 `markdown` body 필드는 A28R이 선택한 저장 state 원문에 직접 매핑한다.
- `markdown` body에는 JSON Agent의 `last_output`을 넣지 않는다. 마케팅 패키지는 `marketing_strategist_proposal_output`을 사용하고, A26 JSON 원문은 저장하지 않는다.
- Notion 페이지 생성 커넥터의 필수 body 필드는 `title`, `markdown`, `proposal_type`이다.
- A28R/A28이 만든 요약문, 축약문, 일부 발췌문, 재작성문, placeholder, 내부 재시도 메모는 Notion 저장 본문으로 쓰지 않는다.

사용자에게 보여줄 정보:
- Notion 페이지 생성 완료 문구
- 생성된 Notion 페이지 링크

문서 선택 기준:
- 여행 상품 추천 결과: `proposal_output`
- AI 포스터 생성 결과: `poster_output`
- 판매용 상품 기획서: `product_planner_proposal_output`
- 운영 체크리스트: `operations_manager_proposal_output`
- 마케팅 패키지: `marketing_strategist_proposal_output`
- “지금 내용”, “지금 나온 내용”, “방금 내용”, “방금 말한 내용”, “그 내용”, “이 문서”: 현재 보이는 결과를 저장하려는 요청으로 처리
- 비어 있지 않은 저장 output이 하나뿐이면 해당 output 선택
- 비어 있지 않은 저장 output이 여러 개이고 문서 유형 단서가 없으면 오래된 다른 브랜치 문서로 fallback하지 않고 `needs_document_selection`으로 멈춘다.

## 시각화 원칙

A21, A24, A27은 마크다운에서 표, HTML 카드, HTML table 기반 시각화를 적극 사용한다.
공모전 데모에서는 렌더러가 허용하는지 직접 확인한다.
색깔 이모티콘으로 위험도나 적합도를 표현하지 않는다. 리스크 수준은 표 안에서 `낮음`, `보통`, `높음` 같은 텍스트로 표현한다.

시각화 table은 `<table style="...">` 기반으로 연관 관광지 네트워크, 상품 확장 후보, 운영 리스크 흐름, 시각 소재와 채널 연결을 표현할 때 사용한다.

## API Connector 요약

상세 URL은 `D09_BASELINE_API_CONNECTORS.md`를 따른다.

| 커넥터 | 서비스 | 사용 Agent |
|---|---|---|
| 연관관광지 키워드 검색 | `TarRlteTarService1/searchKeyword1` | A18 |
| 관광지 집중률 예측 | `TatsCnctrRateService/tatsCnctrRatedList` | A22 |
| 관광사진 키워드 검색 | `PhotoGalleryService1/gallerySearchList1` | A25 |
| Notion 페이지 생성 | Notion bridge `/notion/pages` | A28 |

커넥터 주의:
- 모두 GET이다.
- Header와 Body는 비운다.
- `serviceKey`는 필수 변수다.
- `areaCd`, `signguCd`는 A18/A22 앞의 AreaCodeResolverAgent가 공식 관광지 시군구 코드표 기준으로 채운 값을 사용한다.
- `baseYm`, `keyword`, `tAtsNm`은 Agent가 호출 시 채운다.
- A18의 `연관관광지 키워드 검색` `baseYm`은 항상 `202604`로 고정한다.
- A25의 `관광사진 키워드 검색`은 `areaCd`, `signguCd` 없이 상품 장소명 또는 테마 keyword를 사용하고 `numOfRows=6`, `pageNo=1`로 호출한다.
- `관광지 집중률 예측`은 공식 관광지 시군구 코드표 기준 코드와 선택 상품 장소명을 함께 사용한다. 부산광역시 중구 예시는 `areaCd=26`, `signguCd=26110`, `tAtsNm=자갈치 크루즈`이다. A22는 원 장소명을 먼저 호출하고 결과가 없으면 고유 지명/브랜드 중심 fallback query만 소량 추가한다.
- `관광지 집중률 예측`은 `numOfRows=3`, `pageNo=1`로 호출한다. A22는 Ennoia의 오늘 날짜 추가 기능으로 받은 현재 날짜와 응답의 `baseYmd`를 비교해 오늘 또는 오늘 이후 가장 가까운 기준일을 선택한다.
- TourAPI 국문 관광정보의 legacy `area_code`, `sigungu_code`를 후속 실무 branch API 코드로 쓰지 않는다.
- `연관관광지 키워드 검색`은 `areaCd`가 없으면 호출하지 않는다. 필수 파라미터 누락 가능성이 있으면 failed call을 만들지 말고 스킵한다.
- API 결과는 보조 신호다. 판매량, 예약 가능성, 실제 혼잡, 안전을 보장하는 claim에 사용하지 않는다.
