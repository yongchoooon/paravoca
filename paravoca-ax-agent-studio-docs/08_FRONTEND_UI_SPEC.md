# Frontend UI 명세

## 프론트엔드 목표

PARAVOCA AX Agent Studio의 프론트엔드는 여행 상품화 운영툴입니다. 첫 화면부터 실제 workflow 실행, 상품 초안 검토, 근거 확인, 리스크 검수, 평가 지표 확인이 가능해야 합니다.

핵심 화면:

1. Dashboard
2. Workflow Builder
3. Run Console
4. Result Review
5. Poster Studio
6. Data Sources
7. Evaluation Dashboard
8. Cost Dashboard
9. Settings

현재 Phase 10 코드에는 Dashboard, message 중심 run 생성 form, run 생성 전 Preflight 검증, run table, task 선택/전체 선택/삭제, React Flow workflow preview, Run Detail, GeoResolver 결과 표시, 지역 후보 안내 UI, 국내 지원 범위 안내, Result Review, approval action, revision history, AI 수정/직접 수정/QA 재검수 modal, Run Detail Evidence의 상세 정보/이미지 후보 표시, Data Coverage panel, Recommended Data Calls panel, QA Review Avoid 표시가 구현되어 있습니다. Mantine `AppShell.Navbar` 기반 전역 navigation shell은 아직 구현되지 않았으며, `14_POST_PHASE7_IMPLEMENTATION_PLAN.md`의 Phase 10.1에서 Dashboard 중심 화면을 앱 전체 layout으로 전환합니다. 노드 편집형 Workflow Builder, Poster Studio, Data Sources 독립 화면, Evaluation Dashboard, Cost Dashboard, Settings 독립 화면은 후속 Phase 목표로 유지합니다.

Run 생성 modal은 상품 개수를 최대 5개로 제한합니다. 사용자가 자연어로 6개 이상을 요청하거나 관광 상품 기획과 무관한 문장을 입력하면 backend `PreflightValidationAgent` 응답을 받아 modal 안에 경고를 표시하고 Run Detail로 넘어가지 않습니다. Workflow Preview에는 이 Preflight gate가 표시되지만, 실제 run이 생성되지 않은 실패이므로 Run Detail의 단계별 진행 목록에는 표시하지 않습니다.

현재 Run Detail의 상세 진행 단계는 개발자가 `agent_steps`와 Gemini 호출 흐름을 확인하기 위한 debug UI입니다. 일반 사용자용 화면에서는 내부 agent 이름과 개별 planner lane을 모두 진행 상태로 보여주지 않고, 더 적은 수의 자연어 단계로 묶어 표시하는 방향을 Phase 10.1 이후 UX 정리 범위에 포함합니다.

## 기술 제약

반드시 사용:

- React 또는 Next.js
- TypeScript
- Mantine UI
- CSS Modules 또는 SCSS Modules
- React Flow
- Tabler Icons 또는 lucide-react

사용 금지:

- Tailwind CSS
- shadcn/ui
- Bootstrap
- Bootstrap class 기반 layout
- Bootstrap component library
- shadcn scaffold component

## UI 톤

SaaS 운영 도구처럼 조용하고 밀도 있게 만듭니다. Mantine 기본 컴포넌트를 쓰되 default theme 그대로 방치하지 말고, 제품 고유의 spacing, radius, color, table density, status color를 지정합니다.

권장:

- Mantine `AppShell` 기반 좌측 navigation + 상단 header
- `Table`, `Tabs`, `Badge`, `Button`, `ActionIcon`, `Menu` 중심의 운영 UI
- `Drawer`로 node inspector, evidence detail, mobile sidebar 표시
- `Modal`로 승인/반려/재실행 confirmation 처리
- `Notification`으로 workflow 실행, 실패, 승인 완료 피드백 표시
- 결과 preview와 source evidence를 나란히 배치
- workflow canvas는 넓게
- 버튼은 명확한 command 중심

피해야 할 것:

- landing page hero
- 큰 gradient 배경
- 장식용 카드 남발
- 과도한 둥근 모서리
- 한 가지 색상만 지배하는 UI
- 기능 설명 문구를 화면에 길게 노출
- Mantine default demo처럼 보이는 화면

## 라우팅 구조

Next.js 예시:

```text
/                         Dashboard
/workflows                Workflow template list
/workflows/:id            Workflow Builder
/runs                     Workflow run list
/runs/:id                 Run Console + Result Review
/runs/:id/posters         Poster Studio for a selected run
/data-sources             Tourism data search/cache
/evals                    Evaluation Dashboard
/evals/:id                Eval Report
/costs                    Cost Dashboard
/settings                 API keys/model policy/settings
```

React Router를 쓰는 경우도 동일 path를 사용합니다.

## 공통 레이아웃

### AppShellLayout

Mantine `AppShell`을 사용합니다.

구현 계획:

- Phase 10.1에서 현재 Dashboard 중심 화면을 `AppShellLayout` 아래로 이동합니다.
- `AppShell.Navbar`는 단순 장식이 아니라 Dashboard, Runs, Workflow Preview, Data Sources, Evaluation, Costs, Poster Studio, Settings로 이동하는 전역 navigation입니다.
- 아직 구현되지 않은 화면은 disabled/future 상태로 보여주고, 실제 기능이 있는 것처럼 표현하지 않습니다.
- Dashboard 내부 탭과 전역 navbar가 같은 역할을 반복하지 않도록 route와 화면 구성을 정리합니다.

구성:

- `AppShell.Header`
- `AppShell.Navbar`
- `AppShell.Main`
- mobile `Burger`
- command/action area
- `Notifications`

예시:

```tsx
import { AppShell, Burger, Group, Text } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";

export function AppShellLayout({ children }: { children: React.ReactNode }) {
  const [opened, { toggle }] = useDisclosure();

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{
        width: 260,
        breakpoint: "sm",
        collapsed: { mobile: !opened },
      }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="sm">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <Text fw={700}>PARAVOCA AX</Text>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="xs">
        <SidebarNav />
      </AppShell.Navbar>

      <AppShell.Main>{children}</AppShell.Main>
    </AppShell>
  );
}
```

제품 고유 레이아웃은 CSS Module로 보완합니다.

```css
.mainHeader {
  border-bottom: 1px solid var(--mantine-color-gray-3);
}

.navItem {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
}
```

### Sidebar 메뉴

- Dashboard
- Workflows
- Runs
- Data Sources
- Evaluations
- Costs
- Settings

아이콘:

- Tabler Icons 우선
- lucide-react도 허용
- icon-only action에는 `Tooltip`과 `aria-label`을 붙입니다.

### 상태 배지

Mantine `Badge`를 사용합니다.

Workflow status 색상:

| status | Mantine color | variant |
|---|---|---|
| pending | gray | light |
| running | blue | light |
| awaiting_approval | yellow | light |
| approved | green | light |
| rejected | red | light |
| failed | red | filled |
| cancelled | gray | outline |

구현 예:

```tsx
const statusColor: Record<string, string> = {
  pending: "gray",
  running: "blue",
  awaiting_approval: "yellow",
  approved: "green",
  rejected: "red",
  failed: "red",
  cancelled: "gray",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge color={statusColor[status] ?? "gray"} variant="light" size="sm">
      {status}
    </Badge>
  );
}
```

## Theme

### theme.ts

Mantine theme를 프로젝트에 맞게 조정합니다.

```tsx
import { createTheme, rem } from "@mantine/core";

export const theme = createTheme({
  primaryColor: "opsBlue",
  fontFamily:
    "Inter, Pretendard, system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
  headings: {
    fontFamily:
      "Inter, Pretendard, system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
    fontWeight: "650",
  },
  defaultRadius: "md",
  radius: {
    xs: rem(3),
    sm: rem(5),
    md: rem(7),
    lg: rem(8),
    xl: rem(10),
  },
  colors: {
    opsBlue: [
      "#edf5ff",
      "#d9e8ff",
      "#b3d0ff",
      "#89b6f8",
      "#669fee",
      "#4f90e8",
      "#4288e6",
      "#3476cc",
      "#2b68b8",
      "#1d5aa3",
    ],
  },
});
```

### 색상 원칙

- 메인 액션: blue 계열
- 성공/승인: green
- 승인 대기/주의: yellow
- 실패/위험: red
- 보조 정보: gray
- 비용/usage: cyan 또는 grape를 소량 사용 가능

화면 전체가 한 색상으로 보이지 않도록 table, panel, status, action의 색상 역할을 분리합니다.

## Dashboard

목적:

- 최근 workflow run
- 여행 상품화 workflow 상태
- 승인 대기
- 실패 run
- 이번 달 비용
- 평균 latency
- 평가 통과율

Mantine 컴포넌트:

- `SimpleGrid`
- `Paper`
- `Group`
- `Stack`
- `Text`
- `Badge`
- `Table`
- `Button`
- `ActionIcon`
- `RingProgress`
- `Progress`

구성:

- 상단 KPI grid
- 승인 대기 table
- 최근 실행 table
- 비용 trend compact chart optional

KPI:

- Runs today
- Awaiting approval
- Avg cost per task
- Avg latency
- Eval pass rate

## Workflow Builder

React Flow 기반 canvas입니다.

### 전체 레이아웃

Desktop:

```text
Node Palette | React Flow Canvas | Node Inspector
```

CSS Module:

```css
.builderShell {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr) 340px;
  height: calc(100dvh - var(--app-shell-header-height) - 32px);
  min-height: 640px;
}

.palette {
  border-right: 1px solid var(--mantine-color-gray-3);
  overflow: auto;
}

.canvas {
  min-width: 0;
  background: var(--mantine-color-gray-0);
}

.inspector {
  border-left: 1px solid var(--mantine-color-gray-3);
  overflow: auto;
}
```

Tablet/mobile:

- Node Palette는 `Drawer`
- Node Inspector는 `Drawer`
- Canvas는 full width

### 좌측 팔레트

Mantine 컴포넌트:

- `ScrollArea`
- `Stack`
- `Button`
- `Badge`
- `Text`
- `Tooltip`

노드 타입:

- User Input
- Data Collection
- RAG Search
- Research Analysis
- Product Planning
- Marketing Copy
- QA Review
- Human Approval
- Save Result

각 노드는 icon + 짧은 name + category badge로 표시합니다.

### 중앙 canvas

기능:

- drag nodes
- connect edges
- delete node/edge
- zoom/pan
- fit view
- save template
- run template

React Flow 기본 스타일 위에 CSS Modules로 node 스타일을 조정합니다.

### 우측 inspector

Mantine `Tabs`, `TextInput`, `Select`, `NumberInput`, `Checkbox`, `Switch`, `MultiSelect`, `Textarea`를 사용합니다.

선택한 node의 config를 편집합니다.

예: Data Collection node

- provider: tourapi
- region source: user_input.region
- include events: checkbox
- include stays: checkbox
- max results: number

예: QA Review node

- block high severity: checkbox
- check prohibited phrases: checkbox
- require sources: checkbox
- judge model tier: select

### Top toolbar

Mantine 컴포넌트:

- `Group`
- `Button`
- `ActionIcon`
- `Menu`
- `Tooltip`
- `Divider`

버튼:

- Save
- Run
- Validate
- Fit view
- Export JSON

아이콘:

- `IconDeviceFloppy`
- `IconPlayerPlay`
- `IconCheck`
- `IconMaximize`
- `IconDownload`

### Node 상태 표시

실행 중 run을 열면 node별 상태를 표시합니다.

- queued: gray border
- running: blue border + small loader
- succeeded: green check
- failed: red alert
- waiting_for_human: yellow pause

## Run Console

목적:

- workflow 실행 상태를 실시간 또는 polling으로 보여줍니다.

Mantine 컴포넌트:

- `Tabs`
- `Timeline`
- `Table`
- `Code`
- `JsonInput` 또는 read-only code block
- `Badge`
- `Progress`
- `Alert`
- `ScrollArea`
- `Skeleton`

구성:

- run summary header
- step timeline
- tool call table
- LLM call/cost table
- raw event log collapsible

### Run summary

필드:

- Run ID
- status
- created at
- elapsed time
- total cost
- model policy
- provider mode

### Step timeline

각 step row:

- agent name
- status badge
- latency
- model
- prompt version
- output summary

### Tool call table

컬럼:

- time
- tool
- status
- arguments summary
- response count
- latency
- error

## Result Review

목적:

- 생성된 상품 기획 결과를 검토 담당자가 확인하고 승인/반려합니다.

Desktop layout:

```text
Product List | Product Detail | Evidence + QA Panel
```

Mantine 컴포넌트:

- `Tabs`
- `Table`
- `ScrollArea`
- `Paper`
- `Badge`
- `Button`
- `ActionIcon`
- `Modal`
- `Drawer`
- `Alert`
- `Accordion`
- `Textarea`
- `JsonInput`

### Product list

각 item:

- title
- target
- QA status badge
- source count
- revision status

Dashboard의 run table은 최상위 원본 run 중심으로 표시합니다. revision run은 독립 행처럼 섞어 보여주지 않고, 원본 run의 `Revisions N` 액션으로 펼쳐 봅니다. 펼쳐진 revision 행은 배경색, indentation, branch marker로 하위 run임이 명확해야 하며, 펼쳐도 table column width가 흔들리지 않도록 fixed layout을 사용합니다.

Task 삭제:

- 각 task row 왼쪽에 checkbox를 둡니다.
- table 상단과 header에는 현재 표시 가능한 task를 대상으로 하는 전체 선택 checkbox를 둡니다.
- parent task를 선택하면 연결된 revision task도 자동 선택합니다.
- revision task를 개별 해제하면 parent 선택도 같이 해제해 UI 선택 상태와 실제 삭제 범위를 일치시킵니다.
- `pending`, `running` 상태의 task는 삭제 대상에서 제외하며, 실행 중인 revision이 있으면 parent task 선택도 막습니다.

### Product detail tabs

Tabs:

- Overview
- Itinerary
- Sales Copy
- FAQ
- SNS
- Keywords
- JSON

### Evidence panel

선택 상품의 source_ids를 보여줍니다.

필드:

- source title
- source type
- content_id
- snippet
- API/source link
- license note

공간이 좁으면 Evidence panel은 `Drawer`로 엽니다.

### QA panel

이슈 목록:

- severity badge
- type
- message
- field path
- suggested fix

High severity가 있으면 approval button 옆에 `Alert`를 표시합니다.

QA issue 선택:

- issue row마다 checkbox를 둡니다.
- 선택한 issue만 AI 수정 요청에 포함합니다.
- message와 suggested fix에는 `disclaimer`, `not_to_claim`, `sales_copy` 같은 내부 필드명이 노출되지 않아야 합니다.
- 사용자에게는 `유의 문구`, `운영 주의사항`, `상세 설명`, `FAQ 답변`처럼 이해 가능한 라벨을 보여줍니다.

### Approval actions

버튼:

- Approve
- Request changes
- Reject
- Export draft
- AI 수정
- 직접 수정
- QA 재검수
- 포스터 생성

승인 modal:

- comment textarea
- high risk override checkbox
- final confirm

승인/반려 후 `notifications.show`로 결과를 알립니다.

### Revision actions

Result Review 우상단에는 다음 revision action을 둡니다.

- `AI 수정`: 선택한 QA issue와 requested changes만 사용해 필요한 필드만 AI가 patch합니다. Product/Marketing 전체 재생성 UI처럼 보이면 안 됩니다.
- `직접 수정`: 운영자가 product, sales copy, FAQ, SNS posts, search keywords, assumptions, not_to_claim을 직접 수정합니다.
- `QA 재검수`: 상품 내용은 유지하고 QA/Compliance Agent만 다시 실행합니다.

Revision modal 규칙:

- 실행 전 `Run settings` panel을 보여줍니다.
- `Run settings`에는 최초 create run 때 사용한 `Request`, resolved `Geo Scope`, `Period`, `Target`, `Product count`, `Preferences`, `Avoid`가 기본값으로 표시됩니다.
- 사용자는 기본값 그대로 실행하거나 필요한 값만 수정할 수 있습니다.
- QA Review 영역에는 최초 실행 또는 마지막 revision QA 설정의 `Avoid` 기준을 badge로 표시합니다.
- `Comment`, `Requested changes`, 본문 편집 textarea는 최소 4~6줄 이상 보이게 합니다. SNS posts, search keywords, assumptions, not_to_claim은 더 긴 textarea를 사용합니다.
- `manual_edit`에는 `저장`과 `저장 후 QA 재검수` 버튼을 모두 제공합니다.
- `저장`은 `manual_save` revision을 만들고 QA를 재실행하지 않습니다.
- `저장 후 QA 재검수`는 `manual_edit` revision을 만들고 QA만 재실행합니다.
- 하단 안내 문구는 "원본 결과는 그대로 두고 새 Revision으로 기록합니다."처럼 사용자 친화적으로 작성합니다.

### Poster action

Result Review 우상단 또는 상품 detail action 영역에는 `포스터 생성` 버튼을 둘 수 있습니다.

동작:

- 선택된 product가 있으면 해당 product 기준으로 Poster Studio를 엽니다.
- 선택된 product가 없으면 product 선택 modal을 먼저 띄웁니다.
- run이 active 상태이면 버튼을 비활성화합니다.
- final_output이 없거나 QA report가 없으면 안내 `Alert`를 표시합니다.
- 승인된 run만 허용할지, `awaiting_approval` 상태도 draft poster 생성을 허용할지는 Settings의 policy로 제어합니다.

## Poster Studio

목적:

- Run Review 결과를 바탕으로 여행 상품 홍보 포스터를 생성합니다.
- 이미지 생성 전 사용자가 문구와 옵션을 검토하고 수정할 수 있게 합니다.
- 생성된 포스터와 prompt, 옵션, 비용 로그를 원본 run에 연결합니다.

기본 레이아웃:

```text
Product Context | Poster Options + Copy Review | Prompt Preview + Generated Poster
```

Mantine 컴포넌트:

- `Stepper`
- `SegmentedControl`
- `Checkbox.Group`
- `Radio.Group`
- `MultiSelect`
- `Textarea`
- `TextInput`
- `Select`
- `Paper`
- `Tabs`
- `Badge`
- `Alert`
- `Modal`
- `Drawer`
- `Image`
- `ActionIcon`

### Step 1: Product Context

표시 항목:

- 선택한 run id와 product id
- product title
- one_liner
- target customer
- core values
- itinerary highlights
- selected evidence count
- QA status
- not_to_claim / assumptions 요약

사용자는 여기서 포스터 생성에 사용할 상품을 바꿀 수 있습니다.

### Step 2: Poster Options

사용자 옵션:

- 목적: 상세페이지 대표 이미지, SNS 피드, SNS 스토리, 오프라인 A4 포스터
- 비율: 1:1, 4:5, 9:16, A4 세로
- 스타일: 프리미엄 여행, 로컬 감성, 축제 홍보, 가족 친화, 액티비티 중심
- 문구 밀도: 최소 문구, 핵심 문구 중심, 상세 정보 포함
- 포함 정보: 상품명, 지역, 기간, 타깃, 코스, 핵심 가치, CTA, 확인 필요 문구
- 이미지 기준: AI 생성 비주얼, TourAPI 이미지 참고, 그래픽 중심 배경
- custom instruction: 사용자가 직접 쓰는 추가 지시

옵션은 button group, segmented control, checkbox, textarea를 사용해 빠르게 고를 수 있게 합니다.

### Step 3: Copy Review

Poster Prompt Agent가 추천한 문구를 보여줍니다.

추천 항목:

- headline 후보 3개
- subheadline 후보 3개
- CTA 후보 3개
- 포스터에 넣을 핵심 코스
- 제외할 정보
- 운영 확인 필요 문구

사용자 조작:

- 후보 문구 선택
- 문구 직접 수정
- 문구 삭제
- 새 문구 추가
- 포함 정보 checkbox 조정

규칙:

- QA issue에 걸린 표현은 기본 선택에서 제외합니다.
- `not_to_claim`에 있는 값은 prompt constraint로만 사용하고 포스터 문구에는 넣지 않습니다.
- 가격, 예약 가능 여부, 운영 시간은 확정 정보처럼 표시하지 않습니다.

### Step 4: Prompt Preview

이미지 생성 전 최종 prompt를 표시합니다.

구성:

- final image prompt
- negative/avoid instructions
- selected text blocks
- visual style
- composition guidance
- output options
- model candidate

사용자는 prompt를 직접 수정할 수 있습니다. 직접 수정한 내용은 `manual_prompt_override=true`로 저장합니다.

### Step 5: Generate Poster

생성 액션:

- `Generate poster`
- `Regenerate with same options`
- `Duplicate options`
- `Save as draft`

생성 결과 표시:

- poster preview
- status badge: `generating`, `needs_review`, `approved`, `rejected`, `failed`
- model/provider
- latency
- estimated cost
- prompt version
- created_at

기본 이미지 모델 후보:

- `gpt-image-2`

구현 전 확인:

- OpenAI Image API 모델명
- 지원 size/quality/format
- moderation 설정
- organization verification 필요 여부
- 가격과 rate limit

### Step 6: Poster QA

검수 항목:

- 이미지 속 텍스트가 선택 문구와 일치하는지
- 텍스트가 읽히는지
- 가격/예약/일정 단정 표현이 있는지
- 과장 표현이나 안전 보장 표현이 있는지
- TourAPI 이미지 참고/재사용 시 라이선스 메모가 있는지
- 브랜드/상표/인물 리스크가 있는지

승인 액션:

- Approve poster
- Request regeneration
- Reject poster
- Export image

Export는 `approved` 상태에서만 기본 활성화합니다.

## Data Sources 화면

목적:

- 수집된 관광 데이터를 검색하고 RAG 색인 상태를 확인합니다.

Mantine 컴포넌트:

- `Table`
- `TextInput`
- `Select`
- `MultiSelect`
- `DatePickerInput`
- `Drawer`
- `Badge`
- `Button`
- `ActionIcon`
- `Pagination`
- `SegmentedControl`

구성:

- 검색 필터
- 관광 item table
- detail drawer
- sync button
- embedding status

필터:

- region
- content type
- source
- has image
- event date range
- embedding status

## Evaluation Dashboard

목적:

- 평가 실행과 결과 확인

Mantine 컴포넌트:

- `SimpleGrid`
- `Paper`
- `Table`
- `Progress`
- `RingProgress`
- `Tabs`
- `Modal`
- `Select`
- `NumberInput`
- `Button`
- `Badge`
- `Alert`

구성:

- Run eval button
- dataset selector
- model policy selector
- metrics summary
- case result table
- failures panel

Metrics:

- Retrieval Recall
- Faithfulness
- Tool Call Accuracy
- Task Success Rate
- Cost per Task
- Latency
- Human Revision Rate

Case table columns:

- case id
- input summary
- passed
- retrieval recall
- faithfulness
- tool accuracy
- cost
- latency
- failure reason

## Cost Dashboard

목적:

- 월 3만 원 내외 운영 가능성을 보여줍니다.

Mantine 컴포넌트:

- `SimpleGrid`
- `Paper`
- `Table`
- `Progress`
- `RingProgress`
- `Badge`
- `Alert`
- `Tabs`

구성:

- monthly total
- cost by provider
- cost by model
- cost by workflow step
- cost per task distribution
- budget alerts

Budget alert examples:

- daily budget 80% reached
- premium model calls exceeded threshold
- eval batch cost higher than expected

## Settings

섹션:

- API Keys status
- Tourism provider mode
- Model policy
- Budget limits
- Evaluation settings
- Export integrations

Mantine 컴포넌트:

- `Tabs`
- `Paper`
- `Stack`
- `TextInput`
- `PasswordInput`
- `Select`
- `Switch`
- `NumberInput`
- `Button`
- `Badge`
- `Alert`

API key는 값을 보여주지 않습니다. 존재 여부만 표시합니다.

```text
GEMINI_API_KEY: configured
TOURAPI_SERVICE_KEY: configured
```

## API client

Frontend service 구조:

```text
frontend/src/services/
  apiClient.ts
  workflowsApi.ts
  runsApi.ts
  approvalsApi.ts
  evalsApi.ts
  costsApi.ts
```

`apiClient.ts`:

```ts
export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${import.meta.env.VITE_API_BASE_URL}${path}`);
  if (!res.ok) throw new Error(`API error ${res.status}`);
  const body = await res.json();
  return body.data as T;
}
```

## 상태 관리

MVP:

- TanStack Query 또는 단순 hooks
- Workflow Builder canvas state는 component state 또는 Zustand

권장:

- server state: TanStack Query
- canvas state: Zustand
- modal/drawer state: Mantine `useDisclosure`
- form state: `@mantine/form`

## Notification 규칙

Mantine `@mantine/notifications`를 사용합니다.

예:

```tsx
import { notifications } from "@mantine/notifications";

notifications.show({
  title: "Workflow started",
  message: "Run run_123 is now running.",
  color: "blue",
});
```

사용 시점:

- workflow run 생성 성공
- workflow run 실패
- approval 완료
- export 완료
- eval run 완료
- budget limit 도달

## Modal과 Drawer 규칙

### Modal

짧은 확인/입력에 사용합니다.

- approve
- reject
- request changes
- delete workflow template
- run eval confirmation

### Drawer

긴 보조 정보를 보여줄 때 사용합니다.

- node inspector on small screens
- evidence detail
- source document detail
- QA issue detail
- raw JSON preview

## 반응형 기준

Desktop 우선 운영툴입니다.

- 1280px 이상: sidebar + main + inspector 3컬럼
- 768~1279px: inspector는 Drawer
- 767px 이하: workflow builder는 read/edit 제한, list/review 중심

텍스트가 버튼/배지 내부에서 잘리지 않게 합니다. 긴 run id는 truncate + tooltip 처리합니다.

## 접근성

- 버튼에는 accessible label
- icon-only button에는 tooltip과 `aria-label`
- 상태 색상만으로 의미 전달 금지, badge text 포함
- modal/drawer focus trap은 Mantine 기본 기능 사용
- keyboard navigation 가능한 table action 구성

## 주요 컴포넌트 목록

```text
components/
  AppShellLayout/
    AppShellLayout.tsx
    AppShellLayout.module.css
  SidebarNav/
    SidebarNav.tsx
    SidebarNav.module.css
  StatusBadge.tsx
  CostBadge.tsx
  WorkflowCanvas/
    WorkflowCanvas.tsx
    WorkflowCanvas.module.css
  NodePalette/
    NodePalette.tsx
    NodePalette.module.css
  NodeInspector/
    NodeInspector.tsx
    NodeInspector.module.css
  RunTimeline.tsx
  ToolCallTable.tsx
  ProductReviewPanel/
    ProductReviewPanel.tsx
    ProductReviewPanel.module.css
  EvidencePanel.tsx
  QAReportPanel.tsx
  ApprovalModal.tsx
  EvalMetricsGrid.tsx
  CostSummaryPanel.tsx
```

## 디자인 acceptance 기준

- 첫 화면이 실제 dashboard여야 합니다.
- Tailwind/shadcn/Bootstrap 관련 파일과 의존성이 없어야 합니다.
- MantineProvider와 프로젝트 theme가 적용되어야 합니다.
- Workflow Builder에서 최소 8개 노드를 배치할 수 있어야 합니다.
- Result Review에서 source evidence와 QA issue가 한 화면에서 확인 가능해야 합니다.
- 승인/반려 액션이 명확해야 합니다.
- 실행 중 상태가 polling으로 갱신되어야 합니다.
- Notification으로 주요 성공/실패 이벤트가 표시되어야 합니다.
