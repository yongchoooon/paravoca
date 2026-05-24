# Phase 18 Evidence UX Redesign

## Status

Implemented.

Phase 18 re-scopes the old Evidence/Visual Evidence plan. The product-image mismatch and generic fallback contamination work was handled in Phase 17.1/17.3, so this phase focuses on the user-facing Evidence review surface.

## What changed

### 1. User-facing Evidence display model

Run Detail now builds a deterministic display model for each evidence document instead of showing raw `source_document.content` in the default Evidence drawer.

The display model separates:

- source label
- image candidates
- basic information
- information useful for product copy
- information to confirm before publishing
- original links
- Developer raw data

If an evidence document has no useful overview/body text, the table summary is left blank instead of falling back to raw API snippets such as `제목: ... 유형: ... 지역코드...`.

This is code-based, not a new LLM Agent. It does not invent facts and does not create fallback evidence.

### 2. Raw API dump moved to Developer raw data

Before Phase 18, Evidence detail could show text like:

```text
제목: ... 유형: ... 지역코드: ... 법정동코드: ... 상세 소개: usefee: 무료 / ...
```

That raw string is still available for debugging, but only inside the folded `Developer raw data` section together with raw metadata. The normal Evidence drawer now presents structured sections.

### 3. Trust percentage and collection timestamp removed from normal UI

The previous `신뢰도 90%` / `신뢰도 55%` wording was misleading because those values are internal heuristics, not statistical truth. Normal user-facing screens no longer show numeric trust/source confidence. Evidence detail uses one source label, `한국관광공사 관광 데이터 기반`, for official tourism-data-backed sources.

Collection timestamps such as `수집 2026. 05. 23...` are also hidden from the normal Evidence screen because they are operational metadata, not user-facing evidence content. Internal values such as `trust_level`, `source_confidence`, `retrieved_at`, and raw metadata remain in Developer raw data.

### 4. User-friendly Evidence copy

The Run Detail UI now uses operator-friendly labels:

- `추천 보강 호출` -> `추가 데이터 확인 내역`
- `Claim 제한` -> `표현 시 주의할 정보`
- `Coverage note` -> `근거 범위 메모`
- raw/internal source-id correction messages are filtered out of normal Result Review evidence notes

The UI avoids phrases like “말하면 안 됨” and instead uses review-oriented language such as `게시 전 확인이 필요한 정보` and `표현 시 주의할 정보`.

### 5. Evidence table summary cleanup

Evidence table rows keep short column names, but the summary column now uses the user-facing display summary rather than raw snippets. If no user-facing summary exists, the summary cell stays blank. The table no longer shows collection timestamps or numeric trust percentages in the normal user surface.

### 6. Result Review evidence state cleanup

The product evidence state keeps source count, review count, and image candidates, but removes raw/internal wording from normal user-facing notes. New runs now store structured product review notes with `audience` and `category` fields so the UI can show only user-facing notes without relying on broad keyword filtering.

Categories map to the UI as follows:

- `publish_check` -> `게시 전 확인이 필요한 정보`
- `copy_caution` -> `표현 시 주의할 정보`
- `evidence_scope` -> `근거 범위 메모`
- `internal_diagnostic` -> Developer/debug only

Legacy runs without structured notes are handled with a narrow compatibility classifier for known old internal messages. Internal diagnostics remain available in Developer/debug areas.

## What did not change

- No new LLM Agent was added.
- Poster Studio image candidate logic was not changed.
- Phase 17 no-fallback/source stability behavior was not changed.
- Product-level Evidence Bundle remains cancelled.
- Raw metadata and source identifiers are not deleted; they are moved out of the default user surface.

## Verification

Completed checks on 2026-05-24:

- `conda run -n paravoca-ax-agent-studio pytest -q backend/app/tests` -> 184 passed, 2 skipped
- `PATH=/Users/yongchoooon/miniforge3/envs/paravoca-ax-agent-studio/bin:$PATH npm run build` -> passed with the existing Vite chunk-size warning

Required checks:

```bash
conda run -n paravoca-ax-agent-studio pytest -q backend/app/tests
PATH=/Users/yongchoooon/miniforge3/envs/paravoca-ax-agent-studio/bin:$PATH npm run build
```

Manual checks:

- Open an existing run and go to Evidence + QA.
- Open an evidence row.
- Confirm the default drawer shows structured sections instead of raw API text.
- Confirm `신뢰도 90%` style labels and `수집 ...` timestamps are gone from normal UI.
- Confirm only one `한국관광공사 관광 데이터 기반` source label appears in the Evidence detail drawer.
- Confirm raw content and metadata remain in Developer raw data.
- Confirm selected evidence filtering still shows the union of source ids used by all products.
