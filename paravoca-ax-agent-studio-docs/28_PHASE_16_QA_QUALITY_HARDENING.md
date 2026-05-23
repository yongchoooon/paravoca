# Phase 16 QA Quality Hardening

Status: implemented

Last updated: 2026-05-23

## Scope

Phase 16 focused on QA evidence-risk quality and revision QA recheck stability.

Out of scope for this phase:

- Marketing copy quality hardening
- RAG/source linking redesign
- Evidence and image selection redesign
- Costs dashboard
- Deployment/demo hardening

## Implemented QA Criteria

QA now separates user-facing QA issues from internal diagnostics.

User-facing QA issues should focus on:

- User `avoid` violations
- Unsupported factual claims
- Missing source evidence for customer-facing concrete claims
- Operational uncertainty stated as fact
- High-risk safety, price, booking, operating-hour, language, medical, wellness, or pet-policy claims

`avoid` is interpreted through evidence risk, not as a blind keyword ban. QA should judge whether the customer-facing phrase is a concrete claim that is not supported by the linked evidence. If the linked evidence directly supports the claim, QA should not create a user-facing issue merely because the phrase matches an avoid category.

QA should not create user-facing issues for:

- Copy being too short, generic, or not attractive enough
- Safe uncertainty phrases such as "확인 필요", "문의 필요", "변동될 수 있습니다", "운영자 확인 후 게시"
- Raw source metadata gaps
- Internal field names or source-id correction details

## User-facing Message Policy

QA messages must use human-readable Korean labels and quote the actual customer-facing problem phrase when possible.

The following internal terms are sanitized or moved out of the user QA list:

- `field_path`
- `sales_copy.sections[0].body`
- `source_id`
- `doc_id`
- `needs_review`
- `missing_pet_policy`

Internal correction/source-link issues are classified as `internal_diagnostic` and kept for Developer/debug review instead of the normal QA table.

## Issue Types

Phase 16 added or standardized these QA categories:

- `avoid_rule`
- `unsupported_claim`
- `source_missing`
- `operational_uncertainty`
- `internal_diagnostic`
- `content_format`

Existing specific types such as `price_claim`, `booking_claim`, `operating_hours_claim`, `theme_claim`, and `safety_claim` remain compatible, but each issue also carries an `issue_category` for broader grouping.

## Revision QA Diff

Revision runs now include `revision.qa_diff_summary` and `revision.qa_recheck_mode`.

For AI partial rewrite and QA-only revision runs that have selected QA issues, the system now performs a targeted recheck:

- The patch prompt receives the selected QA issue and the current value of the affected field.
- The model is instructed to patch only that selected field.
- The server applies only the field paths allowed by the selected QA issue.
- The QA recheck evaluates only whether the originally selected QA issue is resolved or still open.
- It does not scan for brand-new issues during the targeted recheck.
- Unselected original QA issues are carried into the revision result instead of disappearing.

QA recheck modes:

- `qa_only_recheck`: manual edit or QA-only recheck
- `ai_partial_rewrite_recheck`: AI partial rewrite followed by QA recheck
- `not_rechecked`: manual save without QA

Targeted QA diff statuses:

- `resolved`
- `still_open`

Full QA diff statuses are reserved for non-targeted QA reruns only. The normal AI revision flow should not surface `new_issue` or `pre_existing_gap` because it is not doing a broad re-audit.

Targeted recheck behavior:

- If the selected original problem quote is no longer present in the current target field, the server can mark the selected issue as `resolved` even if the LLM returns `still_open`.
- If a selected or carried-over issue remains open, the user-facing message is rewritten to quote the current problem phrase from the target field where possible.
- If the LLM does not quote a customer-facing phrase, the backend validator either rewrites the message from the current target field or excludes the issue from the normal user QA list.
- Manual edit sends the current QA issues for targeted recheck so all existing issues remain visible unless they are resolved.

## AI Revision Change Review

AI partial rewrite revisions now also include `revision.change_review`.

- The backend records changed product/marketing fields with `before`, `after`, `field_label`, and related original QA issue metadata.
- Run Detail highlights only pending AI changes at the changed field location. It does not show a separate all-change summary card above the product detail.
- Each changed field shows separate `이전` and `현재` regions, not a compressed arrow sentence.
- Product buttons and content tabs show red count badges when that product/tab has pending AI changes.
- The operator can accept the current AI change with the green check or revert to the previous value with the red X.
- Accept/revert updates the same revision run. It does not create another revision.
- If a reverted change has a related original QA issue, that issue is restored into the current QA list.

## Revision Patch Prompt Policy

The AI patch flow is driven by selected QA issues and target fields. The revision modal does not include a free-form "Requested changes" field for AI revision or QA recheck.

Patch input is structured around:

- current product summary
- selected QA issue
- target `product_id`
- target `field_path`
- current field value
- suggested fix
- QA settings such as region, period, target customer, preferences, and avoid

The patch output is a patch payload only. The backend then applies the patch to the original result. Source evidence, source ids, claim limits, and unrelated product/marketing fields are not rewritten by the AI patch.

Example instruction shape:

```text
선택된 QA 이슈가 가리키는 필드만 수정하세요.
Product/Marketing 전체를 다시 작성하지 마세요.
source_ids, evidence, claim_limits, not_to_claim, needs_review는 수정하지 마세요.
현재 필드 값에서 문제 문구를 제거하거나 안전한 표현으로 바꾸세요.
```

## QA Prompt Policy

The QA prompt now tells the model to create issues only for user `avoid` violations and concrete evidence risks.

Current QA criteria:

- Quote the exact customer-facing phrase in `message`.
- Do not create an issue if no problem phrase can be quoted.
- Treat avoid rules as unsupported-claim checks. The model must compare the quoted customer-facing phrase against the linked product evidence instead of applying keyword bans.
- Do not judge copy attractiveness, shortness, or generic wording in evidence-risk QA.
- Do not treat safe uncertainty wording as a problem.
- Do not expose internal field paths or raw gap names in user-facing messages.

Example message style:

```text
FAQ 답변에 문제 문구 '광주호 호수생태원은 연중무휴 무료로 개방됩니다.'가 있습니다.
무료 개방 여부는 근거 문서에 명확히 확인되지 않으므로 추가 확인이 필요합니다.
```

## Frontend Minimum Update

Run Detail now:

- Shows QA table headers in Korean
- Uses safer Korean labels for new QA issue types
- Sanitizes raw internal field names before display
- Shows revision QA diff counts when backend metadata exists
- Disables AI revision and QA recheck buttons until at least one QA issue is selected
- Shows a tooltip explaining that a QA issue must be selected first
- Keeps AI revision and QA recheck inputs focused on selected QA issues, without a free-form "Requested changes" field
- Shows all QA issues inside the direct edit modal, not only selected issues
- Allows the operator to edit the full product/marketing content in direct edit
- Keeps the direct edit left column and right editing column independently scrollable
- Uses taller textarea controls for Sales copy, FAQ, SNS, Keywords, Claims, assumptions, and do-not-claim fields
- Shows Dashboard run history as a compact history count and current/latest run row, instead of expanding revision rows by default

Developer/debug data can still include raw QA metadata and internal diagnostics.

## Dashboard / Navigation Updates

The Dashboard now treats the latest revision as the current row for a root run. Earlier revisions and the original run remain accessible through the history control, but the main table is not cluttered by revision rows by default.

The AppShell sidebar now includes a GitHub link at the bottom of the navigation.

## Related Cleanup Implemented During This Phase

Other code changes present in the current worktree and reflected in documentation:

- RAG embedding uses local `sentence-transformers` semantic embedding through `EMBEDDING_MODEL`, `EMBEDDING_DEVICE`, and `EMBEDDING_BATCH_SIZE`.
- Evaluation LLM judge depends on `GEMINI_API_KEY`.
- Default `llm_calls` provider/model values are Gemini.
- README and environment examples now describe only the current behavior.

## Verification Targets

- Backend QA validator tests cover internal diagnostic separation, copy-quality filtering, safe uncertainty filtering, and revision QA diff classification.
- Frontend build verifies the Run Detail QA table and QA diff summary rendering.

Latest verification:

- `conda run -n paravoca-ax-agent-studio pytest -q backend/app/tests`
  - `161 passed, 2 skipped`
- `PATH=/Users/yongchoooon/miniforge3/envs/paravoca-ax-agent-studio/bin:$PATH npm run build`
  - passed with the existing Vite chunk-size warning

## Main Files Changed

- `backend/app/agents/workflow.py`
- `backend/app/rag/embeddings.py`
- `backend/app/core/config.py`
- `backend/app/db/models.py`
- `backend/app/evals/runner.py`
- `backend/app/evals/llm_judge.py`
- `backend/app/tests/test_api.py`
- `frontend/src/pages/RunDetail.tsx`
- `frontend/src/pages/RunDetail.module.css`
- `frontend/src/pages/runDetailUtils.ts`
- `frontend/src/services/runsApi.ts`
- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/components/AppShellLayout/AppShellLayout.tsx`
- `.env.example`
