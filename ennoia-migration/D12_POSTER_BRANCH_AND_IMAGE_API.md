# D12. Poster Branch and Image API

## 목적

여행 상품 추천이 끝난 뒤 사용자가 “3번 상품으로 포스터 만들어줘”처럼 요청하면, 기존 run에 저장된 상품 산출물을 재사용해 AI 생성 포스터를 만든다.

포스터 branch는 기존 여행 상품 추천 branch를 다시 실행하지 않는다.
이미 확보된 상품 관련 Agent의 `*.last_output`과 A14 text 출력을 저장한 `proposal_output`을 읽어 포스터 생성에 필요한 내용만 추린다.

## Classify 분기

Start 바로 다음에 `Classify Request Type` 노드를 둔다.
전체 Classify에는 여행 상품 추천, 포스터, 판매용 상품 기획서, 운영 체크리스트, 마케팅 패키지 카테고리가 있다.
이 문서는 그중 포스터 branch만 다룬다.

포스터 관련 카테고리:

| 카테고리 | 연결 |
|---|---|
| `그 내용으로 포스터 만들어줘` | A15 PosterBriefAgent |

예시 입력:

- `부산광역시 중구에서 가족 대상 여행 상품 3개 추천해줘`
- `3번 상품으로 포스터 만들어줘.`
- `3번 상품으로 포스터 만들어줘. 한 줄 소개, 추천 대상, 구성 장소, 추천 동선, 판매/홍보 문구, SNS 홍보안, FAQ 초안을 포함해줘.`
- `3번 상품으로 포스터 만들어줘. 유용한 정보 중심으로 알아서 구성해줘.`
- `2번 상품으로 포스터 만들어줘. 2번째 이미지를 메인 분위기로 활용해줘.`

## 여행 상품 추천 branch의 마지막 안내

A14 ProposalEditorAgent는 정상 추천 응답 마지막에 `AI 포스터 만들기` 안내를 붙인다.

이 안내는 사용자가 후속 요청 형식을 알 수 있게 하는 용도다.
A14가 포스터를 직접 만들거나 이미지 생성 API를 호출하지 않는다.

조기 종료 응답, 지역 모호성 안내, 지원 범위 밖 안내, 데이터 부족 안내에는 포스터 안내를 붙이지 않는다.

## 포스터 branch 구조

```text
Classify Request Type
  - 그 내용으로 포스터 만들어줘:
    → A15 PosterBriefAgent
    → A16 PosterPromptBuilderAgent
    → A17 PosterImageGeneratorAgent
    → End
```

## Agent 역할

### A15 PosterBriefAgent

역할:
- 사용자 요청에서 상품 번호와 포함할 내용을 해석한다.
- 이전 여행 상품 추천 branch의 상품 관련 `*.last_output`과 `proposal_output`을 읽는다.
- 포스터에 넣을 내용, 참고 이미지 URL, 시각 방향을 JSON으로 정리한다.
- API 커넥터를 호출하지 않는다.

주요 입력:
- `messages`
- `product_manager.last_output`
- `brand_marketing_lead.last_output`
- `growth_marketing_lead.last_output`
- `qa_compliance_manager.last_output`
- `proposal_output`
- `candidate_merge_dedupe.last_output`
- `enrichment_result_merge.last_output`

상태:
- `ready`: 포스터 생성 가능
- `needs_source_product`: 이전 여행 상품 추천 산출물이 없음
- `needs_product_selection`: 상품 번호 선택 필요
- `blocked`: 포스터 브리프 구성 불가

기본 포함 항목:
- 한 줄 소개
- 추천 대상
- 구성 장소
- 추천 동선
- 세일즈 포인트
- 판매/홍보 문구
- SNS 해시태그
- 방문 전 확인사항

사용자가 FAQ를 명시하면 FAQ는 2~3개만 포함한다.
사용자가 “유용한 정보 중심으로 알아서 구성해줘”라고 쓰면 위 기본 포함 항목을 사용한다.

이미지 처리:
- “2번째 이미지”처럼 번호가 있으면 선택 상품과 연결된 이미지 목록에서 1-based index로 선택한다.
- 이미지가 있으면 `input_image_urls` 배열에 넣는다.
- 이미지가 없으면 `input_image_urls`를 빈 배열로 두고 경고를 남긴다.
- 이미지가 없어도 상품 자체나 포스터 생성 branch를 중단하지 않는다.
- `input_image_urls`는 최대 3개까지 허용한다.

### A16 PosterPromptBuilderAgent

역할:
- A15 브리프를 기존 PARAVOCA 포스터 프롬프트 구조와 유사한 이미지 생성 프롬프트로 바꾼다.
- 프롬프트, 포스터 표시 텍스트 후보, 제약 조건, `input_image_urls`, 생성 옵션을 JSON으로 출력한다.
- API 커넥터를 호출하지 않는다.

프롬프트 구성 기준:
- `Create one portrait travel promotion poster draft.`
- `VISUAL DIRECTION`
- `Scene/background`
- `Subject`
- `Key details`
- `Color palette & mood`
- `REFERENCE IMAGES` 또는 `NO REFERENCE IMAGE GUIDANCE`
- `TYPOGRAPHY & TEXT LAYOUT`
- `Included text`
- `Typography rules`
- `Composition`
- `Style summary`
- `CONSTRAINTS`

기존 PARAVOCA의 `backend/app/posters/prompt_builder.py`처럼, 참고 이미지 URL은 프롬프트 본문에 직접 쓰지 않는다.
참고 이미지가 있으면 “reference image(s) are provided”라는 문맥만 넣고, 실제 URL은 `input_image_urls`로 다음 Agent에 넘긴다.

기본 생성 설정:
- 이미지 개수: 1장 고정
- `size`: `1024x1536`
- `quality`: `low`
- `input_image_urls`: 선택 입력, 최대 3개

품질 요청 처리:
- 사용자가 “고화질”, “퀄리티”, “quality”, “medium”, “high”, “low”처럼 품질을 언급해도 A16/A17은 `quality=low`를 유지한다.

### A17 PosterImageGeneratorAgent

역할:
- A16의 `${poster_prompt.last_output.prompt}`를 `AI 포스터 이미지 생성` API 커넥터에 그대로 전달한다.
- A16의 `${poster_prompt.last_output.input_image_urls}`를 API 커넥터 body에 배열로 전달한다.
- 반환된 `image_url`을 HTML `img` 태그와 링크 버튼으로 출력한다.
- 사용자-facing 출력은 생성 이미지, “이미지 크게 보기” 링크 버튼, 짧은 이미지 설명문 중심으로 구성한다.
- `참고 이미지`, `생성 정보`, `생성 프롬프트 요약` 같은 내부 처리 섹션은 출력하지 않는다.
- `image_id`, `input_image_count`, `model`, `size`, `quality`, `latency_ms`, `provider_response_summary.endpoint` 같은 내부 생성 메타데이터는 출력하지 않는다.
- 포스터 생성 결과의 Notion 저장 예시는 방금 생성한 포스터 결과 저장으로만 안내하고, 상품 기획·운영·마케팅 문서를 새로 목차화하거나 요약하라는 예시는 쓰지 않는다.

호출 조건:
- `${poster_prompt.last_output.status} == "ready"`일 때만 API 커넥터를 호출한다.
- 그 외 상태에서는 API를 호출하지 않고 A16의 `user_message`를 출력한다.

## API Connector

실제 브리지 API 계약은 `D13_IMAGE_BRIDGE_API_SPEC.md`를 기준으로 한다.

커넥터 이름:

```text
AI 포스터 이미지 생성
```

Endpoint:

```text
POST https://{현재_TUNNEL_HOST}/generate
```

예:

```text
POST https://workforce-bean-wind-associate.trycloudflare.com/generate
```

Cloudflare Quick Tunnel을 쓰는 동안 host는 실행할 때마다 바뀔 수 있으므로, Ennoia API Connector URL도 현재 tunnel URL로 갱신한다.

Headers:

```text
Authorization: Bearer {IMAGE_BRIDGE_TOKEN}
Content-Type: application/json
```

`IMAGE_BRIDGE_TOKEN`은 `.env.image-bridge`에 설정된 값과 동일해야 한다.
토큰은 Ennoia connector secret/header에만 넣고 Agent 출력이나 Markdown에 노출하지 않는다.
`GET /health`와 `GET /images/{image_id}.png`는 인증 없이 접근 가능해야 한다.
이미지 생성은 수십 초 걸릴 수 있으므로 Ennoia connector timeout은 짧게 잡지 않는다.

Request body:

```json
{
  "prompt": "Create one portrait travel promotion poster draft...",
  "input_image_urls": [
    "https://example.com/reference.jpg"
  ],
  "size": "1024x1536",
  "quality": "low"
}
```

`input_image_urls`는 선택 필드다.
비어 있으면 중간 API 서버는 OpenAI 이미지 생성 endpoint를 사용하고, 값이 있으면 서버가 URL을 다운로드해 OpenAI 이미지 edits endpoint의 `image[]` 파일로 첨부한다.
이미지 URL은 프롬프트 텍스트에 직접 넣지 않는다.
`model`은 브리지 서버 기본값을 쓰도록 보통 생략한다.

Ennoia connector의 `바디 > Code`에는 JSON Schema가 아니라 실제 요청 payload를 넣는다.
`type`, `properties`, `required`, `additionalProperties`가 들어간 schema 객체를 넣으면 서버는 그 schema 객체를 그대로 body로 받아서 `prompt` 누락 오류를 낸다.

텍스트만으로 생성할 때:

```json
{
  "prompt": "사과 이미지 그려줘",
  "input_image_urls": [],
  "size": "1024x1536",
  "quality": "low"
}
```

참조 이미지가 있을 때:

```json
{
  "prompt": "Create one portrait travel promotion poster draft...",
  "input_image_urls": [
    "https://tong.visitkorea.or.kr/cms/resource/48/4065248_image2_1.jpg"
  ],
  "size": "1024x1536",
  "quality": "low"
}
```

Builder로 직접 입력할 때는 아래 필드를 실제 요청 필드로 만든다.
Description은 값이 아니다. 예를 들어 `prompt`의 description에 “사과 이미지 그려줘”를 쓰면 안 되고, `prompt` 필드의 실제 값이 “사과 이미지 그려줘”가 되어야 한다.

| Key | Type | Description |
|---|---|---|
| `prompt` | `string` | 최종 이미지 생성 프롬프트. A17이 `${poster_prompt.last_output.prompt}` 값을 넣는다. |
| `input_image_urls` | `array` | 선택 입력. A17이 `${poster_prompt.last_output.input_image_urls}` 배열을 넣는다. 최대 3개. |
| `input_image_urls` array item | `string` | HTTP(S) image URL to use as a visual reference. |
| `size` | `string` | 기본값 `1024x1536`. |
| `quality` | `string` | 기본값 `low`. |

서버 기준 required field:

```json
["prompt", "size", "quality"]
```

`input_image_urls`는 required가 아니다.
참조 이미지가 있으면 문자열 하나가 아니라 JSON array로 보낸다.

Response body:

```json
{
  "image_url": "https://{TUNNEL_HOST}/images/abc123.png",
  "markdown": "![generated poster](https://{TUNNEL_HOST}/images/abc123.png)",
  "image_id": "abc123",
  "input_image_count": 0,
  "model": "gpt-image-2",
  "size": "1024x1536",
  "quality": "low",
  "provider_response_summary": {
    "endpoint": "images/generations"
  },
  "latency_ms": 69923
}
```

A17은 `image_url`을 1순위로 사용한다.
`markdown`, `image_id`, `input_image_count`, `provider_response_summary`, `latency_ms`는 내부 처리용 보조 필드이며 사용자-facing 응답에는 출력하지 않는다.

## 이미지 서버 구조

사용자가 제안한 1순위 구조를 기준으로 한다.

```text
Ennoia API Connector
→ https://{현재_TUNNEL_HOST}/generate
→ Cloudflare Quick Tunnel
→ 로컬 Docker 서버
→ OpenAI image API 호출
→ base64 이미지 수신
→ 로컬 디스크에 png 저장
→ https://{현재_TUNNEL_HOST}/images/xxx.png 반환
→ Ennoia Markdown/HTML에서 렌더링
```

필수 endpoint:

| Endpoint | 역할 |
|---|---|
| `POST /generate` | 이미지 생성 요청 |
| `GET /images/{id}.png` | 생성 이미지 서빙 |
| `GET /health` | 상태 확인 |

## 보안 요구사항

서버에는 반드시 아래 제한을 둔다.

- `Authorization: Bearer ...` secret token 검증
- prompt 길이 제한
- 이미지 개수 1개 고정
- 허용 size 값 제한
- quality는 서버에서 `medium`으로 고정
- 분당 요청 수 제한
- 30일 지난 이미지 자동 삭제 또는 최대 저장 용량 초과 시 오래된 이미지 삭제

OpenAI API key는 Ennoia 커넥터에 넣지 않는다.
OpenAI API key는 로컬 Docker 서버 환경변수에만 둔다.

## 실패 처리

| 상황 | 처리 |
|---|---|
| 이전 여행 상품 추천 산출물이 없음 | A15가 먼저 여행 상품 추천을 생성하라고 안내 |
| 상품 번호가 없음 + 상품이 여러 개 | A15가 상품 번호를 지정하라고 안내 |
| 요청한 이미지 번호가 없음 | A15가 경고를 남기고 참고 이미지 없이 진행 가능 |
| `422 Unprocessable Entity`와 `body.prompt Field required` | Ennoia connector body에 schema 객체가 들어간 것이므로 실제 payload 형식으로 수정 |
| A17 API 응답에 `image_url` 없음 | A17이 이미지 표시 불가 안내와 선택 상품/포함 항목 요약 출력 |
| API 호출 실패 | A17이 실패 안내. 임의 URL 생성 금지 |

## 구현 판단

초기 포스터 branch는 3개 Agent로 둔다.

- A15: 요청 해석, 상품 선택, 포함 항목 선택, 참고 이미지 선택
- A16: 기존 PARAVOCA 방식에 맞춘 이미지 생성 프롬프트 작성
- A17: API 커넥터 호출, 최종 Markdown/HTML 출력

별도 QA Agent는 초기에는 만들지 않는다.
QA 가드레일은 A15가 `qa_compliance_manager.last_output`의 금지 표현과 확인 필요 사항을 읽고, A16이 프롬프트에서 보장/최상급 표현을 금지하는 방식으로 처리한다.

나중에 포스터 생성 품질 평가, 텍스트 과다 여부, 브랜드 톤 검수까지 자동화해야 하면 A18 PosterReviewAgent를 추가한다.
