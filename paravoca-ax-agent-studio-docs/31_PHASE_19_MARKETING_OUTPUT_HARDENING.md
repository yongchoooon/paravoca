# Phase 19 Marketing Output Hardening

## Scope

This document records the Phase 19.1~19.8 implementation. The work focuses on Marketing output quality only:

- Product naming / one-liner / core value standards
- Product → Marketing prompt hardening
- Evidence-safe FAQ, sales copy, SNS, claims, and disclaimer behavior

Out of scope for this pass:

- RAG/source pipeline changes
- Evidence UX changes
- Poster Studio changes
- Costs or deployment work

## 19.1 Marketing output standards

Marketing output now has explicit quality expectations in the workflow prompt and validation layer.

### Product-level standards

Product generation is instructed to produce names and short descriptions that are useful for later marketing generation:

- `title` should look like a real travel product name and include place/theme/experience signals.
- `one_liner` should explain why the customer would choose the product, not merely say that it is evidence-based.
- `core_value` should describe customer value, emotion, and target-customer context rather than only operational facts.
- Multiple products in the same run should not repeat the same title pattern, one-liner structure, or core-value wording.

### Marketing-level standards

Marketing generation now separates the role of each output:

- Sales copy should have a persuasion flow: attention → imagined experience → pre-publication checks.
- FAQ should include both purchase-decision questions and operational confirmation questions.
- SNS posts should include a hook, emotional context, and a concrete scene or place.
- Claims should preserve evidence safety while keeping useful selling points visible.
- Disclaimers should not erase the product's appeal; they should read like practical pre-publication checks.

## 19.2 Product → Marketing prompt changes

The MarketingAgent prompt now includes structured guidance for:

1. **Marketing output quality**
   - Product title, one-liner, core value, sales copy, FAQ, SNS, and claims each have a distinct role.

2. **Product-level differentiation**
   - Products in the same run must use different angles and avoid copied sentence openings.
   - The prompt explicitly calls out repeated title/headline/SNS patterns as failure cases.

3. **Evidence-safe marketing policy**
   - Verified place, event, story, exhibit, and experience facts may become selling points.
   - Price, hours, reservation, language support, safety, image usage rights, medical/wellness effects, and similar facts must remain confirmation-needed unless clearly supported.
   - Operational caution should be separated from the main selling copy instead of dominating it.

4. **Foreigner-target handling**
   - Output remains Korean for the operator UI.
   - Foreigner-target context should still shape the message: ease of understanding, local context, comfort, expected experience, and visitor concerns.

## 19.3 Evidence-safe FAQ / Claims / Disclaimer behavior

### FAQ balance

The backend validator now rejects FAQ sets that are only operational checks such as price, hours, reservation, cancellation, or confirmation. A valid FAQ set must include at least one purchase-decision question, for example:

- who the product is recommended for
- what experience the customer can expect
- why it is useful for foreign visitors
- what makes the product appealing

Operational questions are still allowed, but they cannot be the entire FAQ output.

### Internal terminology guard

User-facing Marketing text is now checked for raw internal terms before it is accepted. The guard applies to sales copy, FAQ, SNS posts, and evidence disclaimer text.

Examples of terms that should not appear in user-facing copy:

- `not_to_claim`
- `claim_limits`
- `source_id`
- `field_path`
- `missing_pet_policy`
- `needs_review`
- `data_coverage`
- `unresolved_gaps`
- `금지 claim`

The underlying schema remains backward-compatible. Existing fields such as `claim_limits` still exist for API/frontend compatibility, but user-facing text should describe them as natural Korean operating guidance.

## Compatibility notes

- Existing API shape is preserved.
- Existing Run Detail Product/Marketing/FAQ/SNS/Claims tabs should continue to render.
- No new LLM provider or fallback path was added.
- The changes are prompt and validator oriented; they do not alter RAG, Evidence UX, or Poster Studio behavior.

## Validation added

Backend tests now cover:

- Product prompt includes marketing-quality guidance for product names, one-liners, and differentiation.
- Marketing prompt includes Phase 19 quality rules, differentiation instructions, and evidence-safe marketing policy.
- Marketing validation rejects FAQ output that only contains operational checks.
- Marketing validation rejects internal diagnostic terminology in user-facing copy.
- Existing marketing asset schema preservation and repair behavior continue to pass with buyer-facing FAQ content.

## Operator-facing expected result

After this phase, generated marketing should be less formulaic:

- Product names and one-liners should feel closer to real travel products.
- Sales copy should better explain why the product is worth considering.
- FAQ should help both customer decision-making and safe publication.
- SNS posts should read more like actual promotional posts.
- Claims and disclaimers should remain evidence-safe without making the product sound unusable.

---

## Phase 19.4~19.8 Marketing Strategy Pack extension

Phase 19.4~19.8 expands Marketing output from short copy snippets into a product-level sales planning pack. The implementation keeps the existing `marketing_assets` fields backward-compatible and adds optional strategy fields on each product asset.

### 19.4 Product-level marketing_strategy

Each new MarketingAgent asset is instructed to include optional `marketing_strategy`:

- `target_segment`: primary target, secondary targets, and foreigner-context guidance when relevant.
- `product_positioning`: one-line positioning and differentiation.
- `key_selling_points`: evidence-backed selling points with evidence basis and usage notes.
- `customer_objections`: likely customer hesitation and response direction.
- `operation_checklist`: items that should be confirmed before publication/sales.

Validation requires key selling points to include an evidence basis. Information without evidence should be routed to objections/checklists instead of becoming a Selling Point.

### 19.5 landing_page_outline

Marketing output now asks for `landing_page_outline` so Sales Copy is backed by a fuller detail-page plan:

- hero headline/subheadline/hook
- why-this-product reasons
- evidence-backed points
- practical information to confirm before publishing

Run Detail renders this as a “상세페이지 구성” view rather than raw JSON.

### 19.6 faq_strategy

Existing `faq` remains for compatibility. New assets can also include:

- `buyer_faq`: purchase-conversion FAQ for customer decision-making.
- `operation_faq`: publication/operation confirmation FAQ for price, hours, reservation, language support, and similar uncertain items.

Run Detail labels these sections as “구매 전환 FAQ” and “운영 확인 FAQ”.

### 19.7 sns_campaign

Marketing assets write SNS copy only in `sns_campaign`:

- campaign angles and rationale
- format-specific posts (`feed`, `reels`, `story`) with hook/body/hashtags
- visual direction notes

The UI shows one SNS section/representative copy surface based on `sns_campaign.posts`.

### 19.8 claim_strategy

Existing `claim_limits` remains for compatibility. New assets can also include `claim_strategy`:

- `usable_claims`: evidence-backed claims that can be used now.
- `caution_phrasing`: expressions or attractive claims that require caution/confirmation before publication.

Run Detail labels these as “활용 가능한 주장” and “주의 표현”.

### Backend validation

The backend keeps old marketing assets valid when strategy fields are absent. When optional strategy fields are present, validation normalizes their structure and rejects user-facing text containing internal diagnostic terms such as `source_id`, `claim_limits`, `field_path`, `needs_review`, `data_coverage`, or `unresolved_gaps`.

The validator also prevents unsupported operational claims from being placed in `claim_strategy.usable_claims`; price/free status, hours, reservation, safety guarantees, medical/wellness effects, and language support must remain confirmation-needed unless separately grounded.

### Frontend behavior

Run Detail now adds Marketing Strategy Pack views in the existing product detail surface:

- Marketing Strategy Pack summary above the Marketing tabs
- “상품 판매 전략” tab
- “상세페이지 구성” tab
- FAQ tab extension for buyer/operation FAQ
- SNS tab extension for campaign angles/posts/visual direction
- Claims tab extension for usable claims and one consolidated caution phrasing list

Existing runs without these optional fields continue to render with the previous Sales Copy / FAQ / SNS / Claims content.

### Non-goals preserved

This phase does not introduce a separate `MarketingStrategistAgent`; it extends the existing MarketingAgent. It does not change RAG structure, Evidence UX, Costs, Deployment, or introduce fallback/fake/dummy data.


---

## Phase 19 downstream alignment

After the Strategy Pack fields were added, downstream surfaces were updated so they no longer depend only on legacy `sales_copy`, `faq`, and `claim_limits`.

### Field map and QA/revision coverage

Backend revision/QA logic now treats the following Strategy Pack paths as first-class user-facing marketing fields:

- `marketing_strategy.key_selling_points` → 핵심 Selling Point
- `landing_page_outline.hero` and detail-page outline lists → 상세페이지 구성
- `faq_strategy.buyer_faq` / `faq_strategy.operation_faq` → 구매 전환 FAQ / 운영 확인 FAQ
- `sns_campaign.posts` and campaign angles → SNS
- `claim_strategy.usable_claims` / `claim_strategy.caution_phrasing` → 활용 가능한 주장 / 주의 표현

These fields are included in deterministic public-text QA where appropriate. Caution/checklist-style fields are still displayed to operators, but the stronger unsupported-claim checks focus on customer-facing promotional assertions such as `usable_claims`.

### AI revision patching

AI partial revision can now use `marketing_field_patches` with a whitelisted `field_path` and `value`, instead of needing a new bespoke patch schema for every Strategy Pack field. Guardrails remain in place:

- patches can only touch the selected QA issue path or its child path
- source/evidence fields remain out of scope
- internal terms are rejected from user-facing patch text
- removed fields are not accepted: `reasons_to_believe`, `recommended_sales_angle`, `experience_story`, `conversion_cta`, `needs_confirmation`, `avoid_phrasing`, `safe_alternatives`

### Poster and UI behavior

Poster prompt construction now reads detail-page hero text, 핵심 Selling Point, SNS campaign posts, and caution phrasing. Strategy text is used as visual/tone/scene cue; poster visible text is still kept sparse.

Run Detail manual edit now exposes the existing Strategy Pack arrays and objects in the same revision modal, without adding broad create/delete controls. Existing older runs continue to fall back to legacy FAQ/SNS/Claims editing.

Revision change review labels and tab classification now understand Strategy Pack field paths, so accepted/reverted changes are no longer limited to legacy Sales Copy / FAQ / SNS / Claims fields.
