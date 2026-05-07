# PARAVOCA AX Agent Studio

PARAVOCA AX Agent Studio는 공공 관광 데이터를 여행 상품 운영자의 업무 결과물로 바꾸는 AI 워크플로우 시스템입니다. 지역, 기간, 타깃 고객을 입력하면 상품 후보 발굴, 상품 콘셉트 작성, 상세페이지 카피와 FAQ 생성, 운영 리스크 검수, 사람 승인까지 하나의 흐름으로 이어집니다.

## 핵심 메시지

PARAVOCA AX는 여행 상품 운영자에게 "무엇을 팔 수 있을지"를 제안합니다.

관광지, 축제, 숙박, 지역 정보처럼 흩어져 있는 데이터를 운영자가 검토할 수 있는 출시 준비 초안으로 정리하고, 근거 문서와 확인이 필요한 정보를 함께 보여줍니다. 여행 플랫폼 운영자, 상품 MD, 콘텐츠 매니저, 지자체 관광 담당자가 반복적으로 수행하는 리서치와 문서 작성 시간을 줄이는 데 초점을 둡니다.

## 프로젝트 강점

- 공공 관광 데이터를 상품 후보, 코스, 상세페이지 카피, FAQ, 검색 키워드로 연결합니다.
- TourAPI와 RAG 검색 결과를 근거로 사용하고, 출처가 약한 정보는 운영자 확인 대상으로 분리합니다.
- QA/Compliance 단계에서 날짜 오류, 가격 단정, 과장 표현, 출처 누락 같은 운영 리스크를 점검합니다.
- Human Approval과 Revision Workflow로 AI 초안을 사람이 검토, 수정, 승인하는 흐름을 제공합니다.
- Gemini API와 rule-based mode를 함께 지원해 비싼 GPU 없이도 실무형 AI 자동화 흐름을 구성할 수 있습니다.
- 후속 단계에서 웹 검색/검색 grounding과 사용자 추가 입력을 붙여 TourAPI만으로 부족한 운영 시간, 예약 조건, 집결지, 가격/포함사항, 최신 공지 근거를 보강할 계획입니다.
- 후속 기능으로 Run Review 결과를 활용한 포스터 생성 workflow를 확장할 수 있습니다.

## 후속 기능: Poster Studio

Poster Studio는 승인 또는 검토 중인 workflow run 결과를 바탕으로 여행 상품 홍보 포스터를 만드는 기능입니다. 상품 초안, 마케팅 카피, FAQ, 운영 주의사항, 근거 문서를 활용해 포스터에 들어갈 내용을 추천하고, 사용자가 옵션과 문구를 직접 고른 뒤 이미지 생성용 프롬프트를 확정합니다.

예상 workflow:

1. 사용자가 Run Review에서 포스터를 만들 상품을 선택합니다.
2. Poster Prompt Agent가 상품명, 타깃 고객, 핵심 가치, 지역/기간, 주요 코스, CTA, 운영 주의사항 후보를 추천합니다.
3. UI는 포스터 목적과 스타일 옵션을 제공합니다.
4. 사용자는 추천된 문구와 옵션을 남기거나 삭제하고, 직접 수정합니다.
5. Poster Prompt Agent가 최종 이미지 생성 프롬프트를 구조화합니다.
6. Poster Image Agent가 OpenAI Image API로 포스터 이미지를 생성합니다.
7. 생성된 포스터는 원본 run, 선택한 상품, 프롬프트, 옵션, 비용 로그와 함께 저장됩니다.

사용자 선택 옵션 후보:

- 목적: 상품 상세페이지 대표 이미지, SNS 피드, 스토리/릴스 커버, 오프라인 홍보 포스터
- 비율: 1:1, 4:5, 9:16, A4 세로
- 분위기: 프리미엄, 로컬 감성, 가족 친화, 액티비티 중심, 축제/시즌 강조
- 텍스트 밀도: 최소 문구, 핵심 문구 중심, 상세 정보 포함
- 포함 문구: 상품명, 한 줄 소개, 지역/기간, 핵심 코스, 타깃, CTA, 확인 필요 안내
- 이미지 기준: AI 생성 배경, TourAPI 이미지 참고, 이미지 없이 그래픽 중심

구현 시점의 기본 이미지 모델 후보는 OpenAI 공식 Image generation 문서 기준 `gpt-image-2`입니다. 모델명, 가격, 지원 파라미터는 변동될 수 있어 실제 구현 직전에 공식 문서를 다시 확인합니다.

## 공모전/포트폴리오 관점

이 프로젝트의 중심은 여행 상품화입니다. 공공 관광 데이터를 운영자가 바로 검토할 수 있는 상품 초안, 마케팅 문구, FAQ, 리스크 체크리스트, 승인 이력으로 연결합니다.

심사위원이나 채용 평가자가 확인할 수 있는 지점은 명확합니다.

- 여행 플랫폼 운영 업무의 실제 반복 작업을 모델링했습니다.
- 공공데이터를 비즈니스 업무 결과물로 변환합니다.
- LLM 생성 결과에 근거 문서, QA 검수, 사람 승인 절차를 붙였습니다.
- API 사용량, latency, 예상 비용을 기록해 운영 비용 감각을 보여줍니다.
- 작은 여행사와 지역 관광사업자도 접근 가능한 API 기반 구조를 지향합니다.

현재 구현 범위는 Phase 0부터 Phase 9까지입니다.

## 현재 구현 범위

- FastAPI backend scaffold
- SQLite + SQLAlchemy 연결
- 기본 workflow template seed
- `GET /api/health`
- `GET /api/workflows`
- `POST /api/workflow-runs`
- `GET /api/workflow-runs`
- `GET /api/workflow-runs/{run_id}`
- `GET /api/workflow-runs/{run_id}/steps`
- `GET /api/workflow-runs/{run_id}/tool-calls`
- `GET /api/workflow-runs/{run_id}/llm-calls`
- `GET /api/workflow-runs/{run_id}/approvals`
- `GET /api/workflow-runs/{run_id}/result`
- `POST /api/workflow-runs/{run_id}/approve`
- `POST /api/workflow-runs/{run_id}/reject`
- `POST /api/workflow-runs/{run_id}/request-changes`
- `POST /api/workflow-runs/{run_id}/revisions`
- `POST /api/rag/ingest/tourism`
- `POST /api/rag/search`
- `POST /api/llm/key-check`
- `GET /api/data/sources/capabilities`
- `GET /api/data/tourism/search`
- `POST /api/data/tourism/details/enrich`
- React + Mantine UI frontend scaffold
- MantineProvider, Notifications, project theme
- React Flow preview
- workflow run 생성 dashboard
- TourAPI provider interface
- TourApiProvider
- 관광 데이터 검색 API
- tool call logging
- 관광 검색 결과 `tourism_items` upsert
- `source_documents` 생성
- Chroma 기반 local vector index/search
- KTO API capability catalog
- source family, trust level, license note, data quality metadata 저장 구조
- KTO 데이터 보강용 DB 모델 기본 구조
- `tourism_entities`, `tourism_visual_assets`, `tourism_route_assets`, `tourism_signal_records`
- `enrichment_runs`, `enrichment_tool_calls`, `web_evidence_documents`
- KorService2 상세 보강 provider method
- `detailCommon2`, `detailIntro2`, `detailInfo2`, `detailImage2`
- `categoryCode2`, `locationBasedList2`
- content_id 기반 상세 보강 API
- TourAPI 검색 결과의 상세 주소, 홈페이지, 개요, 좌표, 대표 이미지 보강
- content type별 소개 정보와 이용 시간, 주차, 쉬는 날, 문의, 요금성 안내 저장
- `detailImage2` 결과를 게시 후보가 아닌 `candidate` 이미지 후보로 저장
- 보강된 source document를 Chroma에 재색인
- Run Detail Evidence에서 상세 정보와 이미지 후보 확인
- LangGraph workflow skeleton
- Planner, Data, Research, Product, Marketing, QA/Compliance Agent
- Human Approval Node
- workflow run 생성 시 `awaiting_approval`까지 rule-based 또는 Gemini 실행
- agent step, tool call, LLM call, latency, cost 기록 구조
- approval DB/API
- Result Review UI
- Run Detail UI
- 근거 문서 + QA issue 검토
- approve/reject/request changes 액션
- JSON export
- Gemini LLM gateway
- rule-based 생성 모드와 Gemini LLM 설정 전환
- Product, Marketing, QA/Compliance Agent Gemini 연결
- Gemini JSON 응답 검증과 실패 로그 기록
- Gemini 호출별 token, latency, cost 기록
- `backend/logs/llm_usage.jsonl`, `llm_usage.csv`, `llm_usage_summary.json` 파일 기반 LLM 사용량 로그
- `backend/logs/workflow_errors.jsonl`, `workflow_errors.log` 파일 기반 workflow 실패 로그
- Gemini 2.5 Flash-Lite paid tier 기준 예상 비용 기록
- Revision Workflow
- `workflow_runs.parent_run_id`, `revision_number`, `revision_mode` 저장
- request changes, 선택한 QA issue, QA 설정을 revision context로 전달
- `manual_save`, `manual_edit`, `llm_partial_rewrite`, `qa_only` revision mode
- 모든 revision은 최상위 원본 run 아래에 생성되고 `revision_number`만 증가
- manual save는 수정 내용을 새 revision run에 저장하고 QA를 다시 실행하지 않음
- manual edit은 수정한 products/marketing_assets를 새 revision run에 저장하고 QA만 재실행
- qa_only는 기존 결과를 유지하고 QA/Compliance Agent만 재실행
- llm_partial_rewrite는 전체 재생성 없이 선택한 QA issue와 requested changes를 기반으로 필요한 필드만 patch
- Result Review UI의 AI 수정/직접 수정/QA 재검수, revision metadata, revision history, manual edit form
- revision 실행 전 create run 때의 region/period/target/preferences/avoid 설정을 확인하고 수정 가능
- QA 메시지에서 `disclaimer`, `not_to_claim`, `sales_copy` 같은 내부 필드명은 사용자 친화적 라벨로 표시
- JSON export에 revision metadata 포함

## 사용하지 않는 것

- Tailwind CSS
- shadcn/ui
- Bootstrap
- React-Bootstrap

## TourAPI 설정

TourAPI는 실제 한국관광공사 API만 사용합니다. API 키가 없거나 호출이 실패하면 tool call과 workflow run이 실패 상태로 기록되고 FastAPI 로그에 에러가 출력됩니다.

```env
TOURAPI_SERVICE_KEY=
TOURAPI_DETAIL_ENRICHMENT_LIMIT=5
```

공공데이터포털에서 한국관광공사 국문 관광정보 서비스_GW 활용신청 후 키를 넣습니다.

```env
TOURAPI_SERVICE_KEY=your_tourapi_service_key
```

LLM 키는 필수는 아닙니다. `LLM_ENABLED=false`이면 Gemini 키 없이도 rule-based workflow로 동작합니다. 실제 LLM 연동은 우선 Gemini만 사용합니다.

Gemini를 사용하려면 `.env`에 아래 값을 넣습니다.

```env
GEMINI_API_KEY=
GEMINI_CHECK_MODEL=gemini-2.5-flash-lite
GEMINI_GENERATION_MODEL=gemini-2.5-flash-lite
GEMINI_MAX_RETRIES=3
GEMINI_JSON_MAX_RETRIES=2
GEMINI_RETRY_BASE_SECONDS=1.5
GEMINI_RETRY_MAX_SECONDS=12
LLM_USAGE_LOG_DIR=logs
LLM_ENABLED=true
```

LLM mode:

- `LLM_ENABLED=false`: Planner/Data/Research/Product/Marketing/QA/RevisionPatch가 rule-based로 실행됩니다.
- `LLM_ENABLED=true`: Planner/Data/Research는 규칙 기반을 유지하고, Product/Marketing/QA와 AI revision patch만 Gemini를 호출합니다.
- `LLM_ENABLED=true`에서 Gemini 응답의 JSON 파싱/스키마 검증이 실패하면 `GEMINI_JSON_MAX_RETRIES` 횟수만큼 같은 provider로 다시 호출합니다.
- 재시도 후에도 Gemini 호출, JSON 검증, 한글 출력 검증이 실패하면 workflow run은 `failed`가 됩니다.
- 실패한 Agent는 `agent_steps.error`에 남고, Gemini 호출과 JSON 재시도 호출은 `llm_calls`에 token/latency/cost와 함께 저장됩니다.

비용 주의:

- 기본 모델은 `gemini-2.5-flash-lite`입니다.
- DB의 `llm_calls.cost_usd`에는 Gemini 2.5 Flash-Lite paid tier 예상 비용을 기록합니다.
- 비용은 공식 invoice 조회값이 아니며 token usage와 코드의 pricing table 기준 추정치입니다.
- LLM 사용량 파일 로그는 기본적으로 `backend/logs` 아래에 저장됩니다.
  - `llm_usage.jsonl`: 호출별 상세 로그
  - `llm_usage.csv`: 스프레드시트로 열기 쉬운 호출별 로그
  - `llm_usage_summary.json`: 총 호출 수, 실패 수, token, 비용 합계와 provider/model/purpose별 집계
- Gemini API quota 제한에 걸리면 `Quota exceeded ... Please retry in N seconds` 에러가 발생하며, 해당 workflow run은 `failed`로 기록됩니다.
- Gemini 503 high demand/temporary overload 응답은 같은 모델로 짧게 재시도합니다. 재시도 후에도 실패하면 workflow run은 `failed`가 됩니다.
- Gemini가 JSON 뒤에 추가 객체나 설명을 붙인 경우 첫 JSON 객체를 우선 파싱하고, 파싱/스키마 검증이 불가능한 경우 Gemini JSON 재시도를 수행합니다.
- workflow 실패 traceback은 `backend/logs/workflow_errors.log`와 `backend/logs/workflow_errors.jsonl`에 저장됩니다.
- OpenAI/GPT는 현재 workflow에서 사용하지 않습니다.
- 웹 검색/Google Search grounding은 현재 workflow에 구현되어 있지 않습니다. P2 이후 Data Agent 보강 기능으로 추가하며, 기본값은 비활성화하고 run당 query/grounded prompt 한도를 둘 계획입니다.
- Google Cloud 가격표 기준으로 Gemini 2.0/2.5 Flash 계열의 Google Search grounding은 grounded prompt 단위로 계산됩니다. 하루 1,500 grounded prompts 추가요금 무료 구간은 검색 grounding 추가요금에 대한 것이며, 모델 token 비용은 별도입니다. Gemini 3 계열은 search query 단위 과금이 적용될 수 있어 별도 계산이 필요합니다.

## 로컬 실행

### 1. 환경변수 준비

```bash
cp .env.example .env
```

### 2. Backend

```bash
cd backend
conda create -y -n paravoca-ax-agent-studio python=3.11
conda activate paravoca-ax-agent-studio
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Backend URL:

```text
http://localhost:8000
```

Health check:

```bash
curl http://localhost:8000/api/health
```

Tourism search:

```bash
curl -G http://localhost:8000/api/data/tourism/search \
  --data-urlencode "region=부산" \
  --data-urlencode "keyword=야경" \
  --data-urlencode "limit=5"
```

상세 보강까지 함께 확인하려면 `enrich_details=true`를 사용합니다. 이 호출은 검색 결과 중 지정한 개수에 대해 `detailCommon2`, `detailIntro2`, `detailInfo2`, `detailImage2`를 실제 TourAPI로 호출하고, `tourism_entities`, `tourism_visual_assets`, `source_documents`, Chroma index를 갱신합니다.

```bash
curl -G http://localhost:8000/api/data/tourism/search \
  --data-urlencode "region_code=6" \
  --data-urlencode "content_type=event" \
  --data-urlencode "start_date=2026-05-01" \
  --data-urlencode "limit=1" \
  --data-urlencode "enrich_details=true" \
  --data-urlencode "detail_limit=1"
```

이미 DB에 저장된 content_id를 상세 보강하려면:

```bash
curl -X POST http://localhost:8000/api/data/tourism/details/enrich \
  -H "Content-Type: application/json" \
  -d '{
    "content_ids": ["2786391"],
    "limit": 1
  }'
```

사용 가능한 데이터 source와 현재 활성화 여부는 아래 API로 확인합니다.

```bash
curl http://localhost:8000/api/data/sources/capabilities
```

Tool call logging까지 확인하려면 먼저 workflow run을 만들고 `run_id`를 검색 요청에 넘깁니다.

```bash
curl -X POST http://localhost:8000/api/workflow-runs \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": "default_product_planning",
    "input": {
      "message": "부산 외국인 야간 관광",
      "region": "부산",
      "period": "2026-05",
      "target_customer": "외국인",
      "product_count": 3,
      "preferences": ["야간 관광"]
    }
}'
```

생성 응답은 즉시 `pending` 상태로 반환됩니다. 이후 백그라운드에서 Planner/Data/Research/Product/Marketing/QA/Human Approval 단계가 실행되고, 완료되면 `awaiting_approval` 상태가 됩니다.

```bash
curl -G http://localhost:8000/api/data/tourism/search \
  --data-urlencode "region=부산" \
  --data-urlencode "keyword=야경" \
  --data-urlencode "run_id=RUN_ID_FROM_RESPONSE"
```

```bash
curl http://localhost:8000/api/workflow-runs/RUN_ID_FROM_RESPONSE/tool-calls
```

LLM call log:

```bash
curl http://localhost:8000/api/workflow-runs/RUN_ID_FROM_RESPONSE/llm-calls
```

Approval action:

```bash
curl -X POST http://localhost:8000/api/workflow-runs/RUN_ID_FROM_RESPONSE/approve \
  -H "Content-Type: application/json" \
  -d '{"reviewer": "operator", "comment": "Ready to publish"}'
```

```bash
curl -X POST http://localhost:8000/api/workflow-runs/RUN_ID_FROM_RESPONSE/request-changes \
  -H "Content-Type: application/json" \
  -d '{
    "reviewer": "operator",
    "comment": "Need clearer meeting point",
    "requested_changes": ["집결지 설명 보강"]
  }'
```

Revision run 생성:

```bash
curl -X POST http://localhost:8000/api/workflow-runs/RUN_ID_FROM_RESPONSE/revisions \
  -H "Content-Type: application/json" \
  -d '{
    "revision_mode": "llm_partial_rewrite",
    "comment": "Request changes 반영",
    "requested_changes": ["집결지 설명 보강", "과장 표현 완화"],
    "qa_issues": [
      {
        "product_id": "product_1",
        "severity": "medium",
        "type": "general",
        "message": "상세 설명에 과장 표현이 있습니다.",
        "suggested_fix": "완화된 표현으로 수정하세요."
      }
    ],
    "qa_settings": {
      "region": "부산",
      "period": "2026-05",
      "target_customer": "외국인",
      "product_count": 3,
      "preferences": ["야간 관광", "축제"],
      "avoid": ["가격 단정 표현", "과장 표현"],
      "output_language": "ko"
    }
  }'
```

QA만 다시 실행하려면:

```bash
curl -X POST http://localhost:8000/api/workflow-runs/RUN_ID_FROM_RESPONSE/revisions \
  -H "Content-Type: application/json" \
  -d '{
    "revision_mode": "qa_only",
    "requested_changes": ["고객 노출 문구만 다시 확인"],
    "qa_settings": {
      "region": "부산",
      "period": "2026-05",
      "target_customer": "외국인",
      "product_count": 3,
      "preferences": ["야간 관광", "축제"],
      "avoid": ["가격 단정 표현", "과장 표현"],
      "output_language": "ko"
    }
  }'
```

`manual_edit`은 frontend의 직접 수정 modal에서 수정한 products/marketing_assets를 함께 전송합니다. `manual_save`는 같은 payload를 저장하되 QA를 다시 실행하지 않습니다. `llm_partial_rewrite`는 Product/Marketing 전체를 다시 만들지 않고, 선택된 QA issue와 수정 요청에 해당하는 필드만 patch합니다.

RAG search:

```bash
curl -X POST http://localhost:8000/api/rag/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "광안리 야경 외국인 액티비티",
    "filters": {"region_code": "6"},
    "top_k": 5
  }'
```

Gemini key check:

```bash
curl -X POST http://localhost:8000/api/llm/key-check \
  -H "Content-Type: application/json" \
  -d '{"providers": ["gemini"], "max_output_tokens": 16}'
```

이 API는 실제 청구서를 조회하지 않습니다. API 응답의 token usage와 pricing table 기준 예상 비용을 `workflow_runs`와 `llm_calls`에 기록합니다.

Gemini workflow 실행:

```bash
LLM_ENABLED=true uvicorn app.main:app --reload
```

```bash
curl -X POST http://localhost:8000/api/workflow-runs \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": "default_product_planning",
    "input": {
      "message": "이번 달 부산에서 외국인 대상 액티비티 상품을 2개 기획해줘",
      "region": "부산",
      "period": "2026-05",
      "target_customer": "외국인",
      "product_count": 2,
      "preferences": ["야간 관광", "축제"]
    }
}'
```

생성 응답은 먼저 `pending`으로 돌아옵니다. 잠시 후 run을 다시 조회했을 때 `awaiting_approval`이 되면 `final_output.agent_execution`에서 각 Agent가 `rule_based`인지 `gemini`인지 확인할 수 있습니다.

```bash
curl http://localhost:8000/api/workflow-runs/RUN_ID_FROM_RESPONSE/llm-calls
```

파일 로그로 전체 사용량을 빠르게 확인하려면 아래 파일을 봅니다.

```bash
cat backend/logs/llm_usage_summary.json
tail -n 20 backend/logs/llm_usage.jsonl
```

Product/Marketing/QA Agent가 Gemini로 실행되면 `llm_calls`에 아래 purpose가 `provider=gemini`로 저장됩니다.

```text
product_generation
marketing_generation
qa_review
revision_patch
```

### 3. Frontend

```bash
cd frontend
conda activate paravoca-ax-agent-studio
conda install -y -n paravoca-ax-agent-studio nodejs=20
npm install
npm run dev
```

Frontend URL:

```text
http://localhost:5173
```

## Docker 실행

```bash
cp .env.example .env
docker compose up --build
```

## 테스트

Backend:

```bash
cd backend
conda activate paravoca-ax-agent-studio
pytest
```

Frontend:

```bash
cd frontend
conda activate paravoca-ax-agent-studio
npm run build
```

현재 확인된 검증 결과:

- Backend: `20 passed`
- Frontend: production build 성공
- Frontend: `npm run build`의 TypeScript check와 Vite production build 통과
- `GET /api/health` 응답 확인
- `POST /api/workflow-runs`가 즉시 `pending`을 반환하고 백그라운드 실행 후 `awaiting_approval`까지 진행되는 것 확인
- approve/reject/request changes API 동작 확인
- 실제 TourAPI 키로 부산 행사/숙박 데이터 조회 확인
- Chroma RAG search 결과 반환 확인
- `agent_steps`, `tool_calls`, `llm_calls` 저장 확인
- Gemini key check 성공 확인: paid tier 예상 비용 기록
- `LLM_ENABLED=false` rule-based workflow 테스트 통과
- `LLM_ENABLED=true` Gemini workflow 1회 실행 확인
- Product/Marketing/QA Agent의 `llm_calls`가 `provider=gemini`로 저장되는 것 확인
- Gemini 2.5 Flash-Lite paid tier 기준 workflow 예상 비용 기록 확인
- request changes가 있는 run에서 revision run 생성 확인
- manual_edit revision에서 Product/Marketing 재생성 없이 QA만 재실행 확인
- llm_partial_rewrite revision에서 Product/Marketing 전체 재생성 없이 필요한 필드만 patch한 뒤 QA 재실행 확인
- parent/revision 관계가 DB와 UI에서 원본 run 중심으로 확인되는 것 확인
- revision 실행 전 run settings와 QA settings 확인/수정 UI 확인
- QA 메시지의 내부 필드명 노출 방지와 안전한 완화 문구 오판 방지 확인
- `/api/data/sources/capabilities` 응답 확인
- 실제 TourAPI 키로 부산 행사 1건 상세 보강 확인
- `detailCommon2`, `detailIntro2`, `detailInfo2`, `detailImage2` 호출과 저장 확인
- `tourism_entities` canonical entity 저장 확인
- `tourism_visual_assets` 이미지 후보 `candidate` 저장 확인
- Run Detail Evidence에서 상세 정보와 이미지 후보 표시 확인

## 다음 Phase

다음 Phase는 Phase 9.5입니다. 현재 Chroma 검색은 임시 hash 기반 embedding을 사용하므로, 비용이 들지 않는 로컬 `sentence-transformers` 기반 semantic embedding으로 교체하고 기존 source document를 재색인합니다.

이후 Phase에서는 데이터 보강 Agent workflow, 공식 웹 근거 수집, Planner/Data/Research Agent 실제화, 평가 자동화와 운영 지표를 강화합니다. RAG retrieval recall, faithfulness, tool call accuracy, task success rate, cost per task, latency를 dataset 기반으로 측정하고 Evaluation Dashboard에서 확인할 수 있게 만듭니다.

별도 후속 Phase에서는 웹 검색/검색 grounding과 사용자 추가 정보 수집을 Data Agent 보강 기능으로 추가합니다. TourAPI에 없는 운영 시간, 예약 조건, 집결지, 가격/포함사항, 최신 행사 공지 같은 정보를 출처 URL과 조회 시각이 있는 `source=web` 근거로 저장하고, 공식 출처가 약한 정보는 `needs_review`로 분리합니다.

후속 Phase에서는 Poster Studio를 추가해 상품 기획 결과를 홍보 이미지 제작까지 확장합니다. 이 단계에서는 Poster Prompt Agent, poster option review UI, OpenAI Image API 기반 이미지 생성, poster asset 저장, 이미지 생성 비용 추적을 구현합니다.
