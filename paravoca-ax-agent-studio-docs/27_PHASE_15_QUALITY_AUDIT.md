# Phase 15 Quality Audit

Phase 15 is an audit and baseline-setting phase. Do not implement quality fixes in this phase unless a later section explicitly starts a hardening phase.

## Fixed Analysis Runs for 15.0

- `run_0f3679c894d84215`
- `run_331348e02b064d28`
- `run_ac68dfed2d5345e3`
- `run_1241212633404670`
- `run_01e6aa86a21f499f`
- `run_b25b5f6c9ec24e1b`
- `run_f9182c6a30814cab`
- `run_87d306e83f1549c3`
- `run_bec1f1b99da44fe5`

Revision runs are excluded from 15.0 and handled in 15.1. Poster data is excluded from Phase 15 and should be handled in a later poster quality phase.

## Phase 15 Work Breakdown

| Workstream | Purpose | Document |
| --- | --- | --- |
| 15.0-A Run Output Inventory | Collect actual run outputs before judging quality. | [27_PHASE_15_0_A_RUN_OUTPUT_INVENTORY.md](27_PHASE_15_0_A_RUN_OUTPUT_INVENTORY.md) |
| 15.0-B QA Quality Analysis | Check whether QA evaluates only user-specified avoid items and evidence risks. | [27_PHASE_15_0_B_QA_QUALITY_ANALYSIS.md](27_PHASE_15_0_B_QA_QUALITY_ANALYSIS.md) |
| 15.0-C Marketing Quality Analysis | Analyze product names, sales copy, FAQ, SNS, claims, and repeated weak patterns. | [27_PHASE_15_0_C_MARKETING_QUALITY_ANALYSIS.md](27_PHASE_15_0_C_MARKETING_QUALITY_ANALYSIS.md) |
| 15.0-D Evidence / RAG Flow Analysis | Explain source document creation, indexing, search, EvidenceFusion, and product linkage. | [27_PHASE_15_0_D_EVIDENCE_RAG_FLOW_ANALYSIS.md](27_PHASE_15_0_D_EVIDENCE_RAG_FLOW_ANALYSIS.md) |
| 15.0-E Image Candidate Selection Analysis | Explain image candidate collection, product-image mismatch, and selection/fallback behavior. | [27_PHASE_15_0_E_IMAGE_CANDIDATE_SELECTION_ANALYSIS.md](27_PHASE_15_0_E_IMAGE_CANDIDATE_SELECTION_ANALYSIS.md) |
| 15.1 AI Revision QA Regression Analysis | Analyze why AI revision can introduce or expose more QA issues after fixing selected issues. | [27_PHASE_15_1_AI_REVISION_QA_REGRESSION_ANALYSIS.md](27_PHASE_15_1_AI_REVISION_QA_REGRESSION_ANALYSIS.md) |
| 15.2 UI Copy and Developer-Term Cleanup Inventory | List user-facing developer terms and implementation labels that should be hidden or renamed. | [27_PHASE_15_2_UI_COPY_DEVELOPER_LANGUAGE_AUDIT.md](27_PHASE_15_2_UI_COPY_DEVELOPER_LANGUAGE_AUDIT.md) |

## Current Status

- 15.0-A through 15.0-E are documented in separate files.
- 15.1 AI Revision QA Regression Analysis is documented in a separate file.
- 15.2 UI Copy and Developer-Term Cleanup Inventory is documented in a separate file.
