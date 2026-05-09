# Phase 10.1 AppShell Navbar and Global Navigation

작성 기준일: 2026-05-09

## 구현 상태

Phase 10.1은 구현 완료 상태입니다.

이번 Phase에서는 Dashboard 한 화면 중심이던 frontend를 Mantine `AppShell` 기반 운영툴 shell로 정리했습니다. Data Enrichment workflow나 backend 실행 로직은 바꾸지 않고, 앞으로 붙을 Data Sources, Evaluation, Costs, Poster Studio, Settings 화면을 연결할 전역 navigation 구조를 먼저 만들었습니다.

## 구현 내용

### AppShell layout

- `frontend/src/components/AppShellLayout/AppShellLayout.tsx`
- `frontend/src/components/AppShellLayout/AppShellLayout.module.css`

구현:

- Mantine `AppShell.Header`
- Mantine `AppShell.Navbar`
- Mantine `AppShell.Main`
- mobile `Burger`
- active navigation highlight
- header의 현재 section title
- planned/future 화면의 `예정` 표시

현재 navigation:

- Dashboard
- Workflow Preview
- Data Sources
- Evaluation
- Costs
- Poster Studio
- Settings

`Runs`는 별도 전역 nav item으로 분리하지 않습니다. 사용자가 기존처럼 첫 화면에서 run table을 바로 볼 수 있도록 Dashboard 안에 summary와 Runs table을 함께 둡니다.

### Dashboard 재구성

- `frontend/src/App.tsx`
- `frontend/src/pages/Dashboard.tsx`

구현:

- `App.tsx`에서 `activeSection` 상태를 관리합니다.
- `Dashboard`는 `activeSection`에 따라 Dashboard, Workflow Preview, placeholder 화면을 렌더링합니다.
- 기존 Dashboard 내부 `Tabs`는 제거했습니다.
- Dashboard 화면에는 기존 summary와 Runs table을 함께 표시합니다.
- Workflow Preview는 전역 Navbar에서 독립적으로 접근합니다.

유지한 기존 기능:

- Run 생성 modal
- run table
- task checkbox
- 전체 선택
- 선택 삭제
- parent task 선택 시 revision task 자동 선택
- revision 펼치기/선택
- Run Detail drawer
- Evidence + QA
- Data Coverage / Recommended Data Calls
- QA Review Avoid 표시
- Raw JSON / Run Logs

### Placeholder 화면

아직 구현되지 않은 화면은 실제 기능처럼 보이지 않게 `향후 연결 예정` 상태로 표시합니다.

Placeholder:

- Data Sources: KTO 추가 API, source family, catalog/sync 상태
- Evaluation: evidence 기반 상품 품질 평가, QA risk, revision 비교
- Costs: LLM 토큰/비용, run별 비용, prompt debug log 연계
- Poster Studio: 승인 상품의 포스터와 홍보 소재 생성
- Settings: feature flag, token budget, workflow 표시 수준

## Workflow Preview

Workflow Preview는 Phase 10.2 기준 구조를 유지합니다.

- Preflight
- Geo decision
- DataGap decision
- API Router
- 4 Planner lanes
- Data Calls
- Evidence Fusion
- Research/Product/Marketing/QA/Approval

React Flow는 화면이 처음 열릴 때 구현된 agent 구조가 중앙에 보이도록 기존 `scheduleWorkflowCenter`/`centerWorkflowMap` 로직을 유지합니다.

## 하지 않은 것

Phase 10.1은 frontend layout phase입니다. 아래는 구현하지 않았습니다.

- Data Sources 실제 관리 화면
- Evaluation Dashboard 실제 지표
- Cost Dashboard 실제 비용 분석
- Poster Studio 이미지 생성
- Settings 실제 설정 저장
- backend workflow 변경

## 검증

검증 명령:

```bash
PATH=/Users/yongchoooon/miniforge3/envs/paravoca-ax-agent-studio/bin:$PATH npm run build
```

결과:

- TypeScript check 통과
- Vite production build 통과

backend는 변경하지 않았으므로 backend test는 생략했습니다.

## 후속 진행

Phase 10.5는 이후 구현 완료되었습니다.

Phase 10.5에서는 AppShell 이후 사용자용 운영 화면을 다듬고, 개발자용 debug 정보와 일반 사용자용 진행/근거 화면을 분리했습니다. Run Detail에서 내부 agent 단계가 과도하게 보이는 문제, Data Coverage / Enrichment / Evidence 표시 방식, 후속 Data Sources/Evaluation/Costs 화면으로 연결될 정보 구조를 정리했습니다.
