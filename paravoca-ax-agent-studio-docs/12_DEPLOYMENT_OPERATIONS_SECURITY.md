# 배포, 운영, 보안 명세

## 배포 목표

MVP는 로컬 데모와 저비용 클라우드 배포를 모두 지원합니다.

우선순위:

1. 로컬 Docker Compose 실행
2. 로컬 without Docker 실행
3. Render/Railway/Fly.io backend 배포
4. Vercel frontend 배포
5. PostgreSQL/Qdrant managed 또는 container 배포

## 로컬 실행 구성

### Docker Compose 서비스

```yaml
services:
  backend:
    build: ./backend
    env_file: .env
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app
      - ./data:/data

  frontend:
    build: ./frontend
    ports:
      - "5173:5173"
    environment:
      - VITE_API_BASE_URL=http://localhost:8000/api

  qdrant:
    image: qdrant/qdrant
    ports:
      - "6333:6333"
    volumes:
      - ./data/qdrant_storage:/qdrant/storage
```

Chroma만 사용할 경우 Qdrant 서비스는 생략 가능합니다.

## 환경변수

`.env.example`:

```env
APP_ENV=local
DATABASE_URL=sqlite:///./data/paravoca.db
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]

TOURAPI_SERVICE_KEY=
TOURAPI_DETAIL_ENRICHMENT_LIMIT=5

VECTOR_DB=chroma
CHROMA_PATH=./data/chroma
QDRANT_URL=http://localhost:6333

GEMINI_API_KEY=
GEMINI_CHECK_MODEL=gemini-2.5-flash-lite
GEMINI_GENERATION_MODEL=gemini-2.5-flash-lite
GEMINI_MAX_RETRIES=3
GEMINI_JSON_MAX_RETRIES=2
GEMINI_RETRY_BASE_SECONDS=1.5
GEMINI_RETRY_MAX_SECONDS=12
LLM_USAGE_LOG_DIR=logs
APP_LOG_DIR=logs

# Future Poster Studio
OPENAI_API_KEY=
OPENAI_IMAGE_MODEL=gpt-image-2
POSTER_GENERATION_ENABLED=false
POSTER_ASSET_DIR=poster_assets

DEFAULT_CHEAP_MODEL=
DEFAULT_STANDARD_MODEL=
DEFAULT_PREMIUM_MODEL=
PREMIUM_MODEL_ENABLED=false

USD_KRW_RATE=1400
DAILY_BUDGET_KRW=1000
MONTHLY_BUDGET_KRW=30000
WORKFLOW_BUDGET_KRW=300
EVAL_RUN_BUDGET_KRW=3000

LLM_ENABLED=true
SECRET_KEY=change-me
```

## Secret 관리

금지:

- API key를 Git에 commit
- frontend env에 secret key 저장
- run logs에 full key 출력
- LLM prompt에 secret 포함

권장:

- `.env`는 `.gitignore`
- production은 platform secret manager 사용
- key 존재 여부만 UI 표시
- logs에서는 key masking

## CORS

MVP:

```python
allow_origins = settings.cors_origins
```

Production:

- frontend domain만 허용
- wildcard 금지

## 인증/권한

MVP:

- 단일 demo user
- header 기반 dev user optional

P1:

- email/password 또는 OAuth
- role-based access
- project/team membership

권한:

| Action | Admin | Operator | Reviewer | Viewer |
|---|---|---|---|---|
| Run workflow | yes | yes | no | no |
| Approve | yes | yes | yes | no |
| Reject | yes | yes | yes | no |
| View results | yes | yes | yes | yes |
| Change model policy | yes | no | no | no |
| Run eval | yes | yes | no | no |
| Billing settings | yes | no | no | no |

## 로그

### Application logs

필수 필드:

- timestamp
- level
- request_id
- run_id
- step_id
- message

### Agent logs

DB 저장:

- agent step input/output summary
- prompt version
- model
- latency
- error

주의:

- 전체 prompt/response를 모두 저장할지 여부는 설정으로 제어
- 민감정보가 들어갈 수 있으므로 production에서는 summary 중심

### Tool logs

저장:

- tool name
- arguments
- status
- latency
- response summary
- error

API key는 저장하지 않습니다.

## 모니터링

MVP dashboard에서 표시:

- workflow success/fail count
- average latency
- average cost
- failed tool calls
- budget usage

P1:

- OpenTelemetry
- Prometheus/Grafana
- Sentry
- LangSmith or similar optional

## Backup

MVP local:

- `data/paravoca.db`
- `data/chroma`
- `reports/`

Production:

- PostgreSQL automated backup
- object storage for reports/eval artifacts
- vector DB snapshot

## 배포 옵션

### Option A: 로컬 데모

가장 안정적인 포트폴리오 데모입니다.

```bash
docker compose up --build
```

장점:

- 비용 거의 없음
- 실제 TourAPI 기반 데모 가능
- 영상 녹화 쉬움

### Option B: Render/Railway backend + Vercel frontend

구성:

- Backend: Render/Railway/Fly.io
- Frontend: Vercel
- DB: SQLite는 ephemeral 문제 때문에 production에는 부적합, PostgreSQL 사용 권장
- Vector DB: Chroma persistent 또는 Qdrant Cloud/container

주의:

- 무료 플랜 sleep으로 첫 응답 지연 가능
- API key secret 설정 필요
- workflow 장기 실행 timeout 확인 필요

### Option C: 단일 VPS

Docker Compose 전체를 한 서버에서 실행합니다.

장점:

- 구조 단순
- Qdrant/Postgres 포함 가능

단점:

- 서버 관리 필요

## 보안 체크리스트

### API

- input validation
- request size limit
- rate limit
- CORS 제한
- auth required for mutation APIs
- approval required for export APIs

### LLM

- prompt injection 주의
- source text와 instruction 분리
- tool allowlist
- tool argument validation
- external write tool approval gate

### Poster Studio

- OpenAI API key는 backend env에만 저장
- 포스터 생성은 `POSTER_GENERATION_ENABLED=true`일 때만 허용
- 이미지 생성 전 사용자가 prompt와 옵션을 확인
- 생성 이미지는 기본 `needs_review` 상태로 저장
- 승인 전 외부 게시/export 차단
- 이미지 안 텍스트는 사람이 최종 검수
- 가격, 예약 가능 여부, 운영 일정 단정 표현 차단
- TourAPI 이미지 참고/재사용 시 license note 확인
- OpenAI Image API 모델명, 가격, moderation 설정은 구현 직전에 공식 문서로 재확인

### Data

- 공공데이터 license note 보존
- 이미지 사용 제한 표시
- raw data와 generated claim 구분
- 출처 없는 주장 표시

### Payment

P2 결제 구현 시:

- secret key server only
- webhook signature 검증
- billing key 암호화
- idempotency key 사용
- payment status와 entitlement 분리

## 장애 대응

### TourAPI 실패

사용자 표시:

```text
공공데이터 API 조회 일부가 실패해 캐시/샘플 데이터로 결과를 생성했습니다.
실제 운영 전 최신 정보 확인이 필요합니다.
```

### LLM 실패

대응:

- retry
- backup model
- partial output
- failed step 표시

### Vector DB 실패

대응:

- 실패 로그 저장
- run 실패 처리
- eval report에 retrieval failure 기록

### Budget exceeded

대응:

- workflow 중단 또는 cheap mode 전환
- UI에 budget alert 표시

## 운영 runbook

### 새 데이터 동기화

```bash
python -m app.data.sync --region 부산 --provider tourapi
```

### RAG 재색인

```bash
python -m app.rag.ingest --source tourism_items
```

### Smoke eval

```bash
python -m app.evals.run_eval --dataset app/evals/datasets/smoke.jsonl --sample-size 3
```

### 비용 리포트

```bash
python -m app.costs.report --month 2026-05
```

## Production readiness gap

MVP에서 production으로 가기 전에 필요한 것:

- real auth
- PostgreSQL migration
- queue worker
- webhook verification
- rate limiting
- retry policy hardening
- data retention policy
- 개인정보 처리방침
- 결제 약관
- API quota management
- automated backup
