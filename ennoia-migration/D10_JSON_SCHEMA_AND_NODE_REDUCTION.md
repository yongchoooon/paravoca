# D10. JSON Schema and Node Reduction

## 목적

Ennoia Agent의 응답 포맷을 `json_schema`로 지정할 수 있으면, 짧은 상태 문자열만 출력하던 StatusAgent를 만들 필요가 없다.
분기 조건은 structured output의 boolean/string 필드를 직접 읽는다.

생성하지 않는 StatusAgent:
- A01 PreflightStatusAgent
- A04 GeoStatusAgent
- A06S GapRouteStatusAgent

유지하는 Set state 기준:
- 후속 재사용 또는 로그 확인을 위해 명시적으로 저장해야 하는 출력
- A08/A13의 `last_message` 저장용 출력
- 현재 기준으로는 `enrichment_output`, `qa_output`, `customer_message_output`, `proposal_output`, `poster_output`, `product_planner_proposal_output`, `operations_manager_proposal_output`, `marketing_strategist_proposal_output`을 유지한다.
- `enrichment_output`, `qa_output`은 저장용 state이며 Agent 프롬프트 입력에는 직접 쓰지 않는다.

사용하지 않는 state 기준:
- json_schema Agent 출력 전체를 문자열로 복사한 `*_output` alias
- 바로 다음 if/else에서만 쓰는 boolean/string 상태 alias
- 바로 다음 Agent 하나에서만 쓰고 후속 재사용이 없는 출력
- 최종 End로 바로 나가는 출력

## If/else 조건

조건은 Ennoia UI의 structured output 변수 선택기로 만든다.
직접 CEL을 입력해야 한다면 UI가 생성한 표현식을 우선한다.
`workflow.*`는 사용하지 않는다.

| 분기 | StatusAgent 방식 | 현재 조건 |
|---|---|---|
| request_supported | `PreflightStatusAgent.last_message == "SUPPORTED"` | `${preflight_validation.last_output.supported} == true` |
| geo_resolved | `GeoStatusAgent.last_message == "GEO_RESOLVED"` | `${geo_resolution.last_output.geo_resolved} == true` |
| enrichment_needed | `GapRouteStatusAgent.last_message == "ENRICHMENT_NEEDED"` | `${data_gap_profile.last_output.enrichment_needed} == true` |

## Set state 원칙

A14/A17 같은 text Agent 출력 또는 A14A 같은 저장용 Agent 출력을 state에 저장할 때:

```text
대상 변수: customer_message_output, proposal_output, poster_output, product_planner_proposal_output, operations_manager_proposal_output, marketing_strategist_proposal_output
값 지정: last_message
```

A08/A13 저장용 state를 만들 때:

```text
Set Enrichment Output: enrichment_output = last_message
Set QA Output: qa_output = last_message
```

단, Agent 프롬프트 입력에는 `enrichment_output`, `qa_output`을 직접 쓰지 않는다.
후속 Agent 입력은 `${enrichment_result_merge.last_output}`, `${qa_compliance_manager.last_output}`을 사용한다.

Start 입력을 테스트용으로 state에 저장할 때도:

```text
대상 변수: 테스트용 state
값 지정: last_message
```

여러 upstream Agent가 하나의 Set state에 들어올 때:
- `last_message`만 쓰지 않는다.
- UI 변수 선택기로 각 upstream Agent의 출력 전체를 지정한다.

json_schema Agent 출력은 downstream에서 재사용되더라도 `${schema_name.last_output}`으로 직접 읽는다.
Preflight, Geo, Gap의 긴 JSON과 분기용 boolean을 별도 state로 복사하지 않는다.

| Set state | 대상 변수 | 값 |
|---|---|---|
| Set Enrichment Output | `enrichment_output` | `last_message` |
| Set QA Output | `qa_output` | `last_message` |
| Set Customer Message Output | `customer_message_output` | `last_message` |
| Set Proposal Output | `proposal_output` | `last_message` |
| Set Poster Output | `poster_output` | `last_message` |
| Set Product Planner Proposal Output | `product_planner_proposal_output` | `last_message` |
| Set Operations Manager Proposal Output | `operations_manager_proposal_output` | `last_message` |
| Set Marketing Strategist Proposal Output | `marketing_strategist_proposal_output` | `last_message` |

## A00 PreflightValidationAgent schema

응답 포맷: `json_schema`

```json
{
  "name": "preflight_validation",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "supported": { "type": "boolean" },
      "reason_code": {
        "type": "string",
        "enum": [
          "supported",
          "empty_request",
          "product_count_exceeds_limit",
          "unsupported_scope"
        ]
      },
      "user_message": { "type": "string" },
      "requested_product_count": {
        "anyOf": [
          { "type": "integer" },
          { "type": "null" }
        ]
      },
      "max_product_count": { "type": "integer" }
    },
    "required": [
      "supported",
      "reason_code",
      "user_message",
      "requested_product_count",
      "max_product_count"
    ],
    "additionalProperties": false
  }
}
```

## A18~A28 후속 실무 branch schemas

A21, A24, A27은 최종 Markdown 편집 Agent이므로 `text` 응답 포맷을 사용한다.
A28R NotionPagePayloadBuilderAgent는 Notion 저장 payload를 만드는 JSON Agent이므로 `json_schema` 응답 포맷을 사용한다.
A28 NotionPagePublishAgent는 Notion 페이지 URL만 출력하는 최종 Agent이므로 `text` 응답 포맷을 사용한다.
아래 schema는 API 신호 분석, 실무 패키지 생성, Notion 저장 payload 구성을 담당하는 JSON Agent에 적용한다.

### A17R AreaCodeResolverAgent

아래 schema는 AreaCodeResolverAgent에 사용한다.
세 후속 branch 모두 같은 Agent 이름과 같은 schema 이름 `area_code_resolver`를 사용한다.

```json
{
  "name": "area_code_resolver",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "status": { "type": "string", "enum": ["ready", "needs_source_product", "needs_product_selection", "needs_region_selection", "not_found"] },
      "selected_product_number": { "type": "string" },
      "selected_product_name": { "type": "string" },
      "areaCd": { "type": "string" },
      "signguCd": { "type": "string" },
      "areaNm": { "type": "string" },
      "signguNm": { "type": "string" },
      "matched_region_text": { "type": "string" },
      "confidence": { "type": "string", "enum": ["high", "medium", "low"] },
      "candidate_codes": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "areaCd": { "type": "string" },
            "signguCd": { "type": "string" },
            "areaNm": { "type": "string" },
            "signguNm": { "type": "string" },
            "reason": { "type": "string" }
          },
          "required": ["areaCd", "signguCd", "areaNm", "signguNm", "reason"],
          "additionalProperties": false
        }
      },
      "analysis_notes": { "type": "array", "items": { "type": "string" } },
      "user_message": { "type": "string" }
    },
    "required": ["status", "selected_product_number", "selected_product_name", "areaCd", "signguCd", "areaNm", "signguNm", "matched_region_text", "confidence", "candidate_codes", "analysis_notes", "user_message"],
    "additionalProperties": false
  }
}
```

### A18 ProductPlannerRelatedRouteAnalystAgent

```json
{
  "name": "product_planner_related_route_analyst",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "status": { "type": "string", "enum": ["ready", "needs_source_product", "needs_product_selection", "blocked"] },
      "selected_product_number": { "type": "string" },
      "selected_product_name": { "type": "string" },
      "queries": { "type": "array", "items": { "type": "string" } },
      "related_place_candidates": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "base_place": { "type": "string" },
            "related_place": { "type": "string" },
            "relation_rank": { "type": "string" },
            "category": { "type": "string" },
            "recommended_use": { "type": "string" },
            "risk_note": { "type": "string" },
            "source_connector": { "type": "string" }
          },
          "required": ["base_place", "related_place", "relation_rank", "category", "recommended_use", "risk_note", "source_connector"],
          "additionalProperties": false
        }
      },
      "analysis_notes": { "type": "array", "items": { "type": "string" } },
      "failed_calls": { "type": "array", "items": { "type": "string" } },
      "skipped_calls": { "type": "array", "items": { "type": "string" } },
      "user_message": { "type": "string" }
    },
    "required": ["status", "selected_product_number", "selected_product_name", "queries", "related_place_candidates", "analysis_notes", "failed_calls", "skipped_calls", "user_message"],
    "additionalProperties": false
  }
}
```

운영 주의:
- A18은 strict schema이므로 최상위 키는 `status`, `selected_product_number`, `selected_product_name`, `queries`, `related_place_candidates`, `analysis_notes`, `failed_calls`, `skipped_calls`, `user_message`만 허용한다.
- API 결과가 없거나 `totalCount=0`이어도 `queries_debug`, `skipped_calls_debug`, `failed_calls_debug`, `debug`, `*_extra`, `*_notes` 같은 보조 키를 만들지 않는다.
- 디버그성 정보는 필요한 경우 `analysis_notes` 배열에 문자열로만 남긴다.

### A20 ProductPlannerSalesPackageAgent

```json
{
  "name": "product_planner_sales_package",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "status": { "type": "string", "enum": ["ready", "needs_source_product", "needs_product_selection", "blocked"] },
      "selected_product_number": { "type": "string" },
      "product_name": { "type": "string" },
      "product_type": { "type": "array", "items": { "type": "string" } },
      "recommended_duration": { "type": "string" },
      "core_customers": { "type": "array", "items": { "type": "string" } },
      "required_places": { "type": "array", "items": { "type": "string" } },
      "optional_places": { "type": "array", "items": { "type": "string" } },
      "alternative_places": { "type": "array", "items": { "type": "string" } },
      "paid_free_mix": { "type": "string" },
      "sales_structure": { "type": "array", "items": { "type": "string" } },
      "risk_board": {
        "type": "object",
        "properties": {
          "commercialization_difficulty": { "type": "string" },
          "reservation_risk": { "type": "string" },
          "weather_risk": { "type": "string" },
          "accessibility_risk": { "type": "string" }
        },
        "required": ["commercialization_difficulty", "reservation_risk", "weather_risk", "accessibility_risk"],
        "additionalProperties": false
      },
      "pre_publish_checks": { "type": "array", "items": { "type": "string" } },
      "planner_memo": { "type": "array", "items": { "type": "string" } },
      "user_message": { "type": "string" }
    },
    "required": ["status", "selected_product_number", "product_name", "product_type", "recommended_duration", "core_customers", "required_places", "optional_places", "alternative_places", "paid_free_mix", "sales_structure", "risk_board", "pre_publish_checks", "planner_memo", "user_message"],
    "additionalProperties": false
  }
}
```

### A22 OperationsManagerCrowdingRiskAnalystAgent

```json
{
  "name": "operations_manager_crowding_risk_analyst",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "status": { "type": "string", "enum": ["ready", "needs_source_product", "needs_product_selection", "blocked"] },
      "selected_product_number": { "type": "string" },
      "selected_product_name": { "type": "string" },
      "crowding_signals": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "place": { "type": "string" },
            "base_date": { "type": "string" },
            "area_name": { "type": "string" },
            "crowding_rate": { "type": "string" },
            "risk_level": { "type": "string" },
            "operation_decision": { "type": "string" },
            "source_connector": { "type": "string" }
          },
          "required": ["place", "base_date", "area_name", "crowding_rate", "risk_level", "operation_decision", "source_connector"],
          "additionalProperties": false
        }
      },
      "risk_summary": { "type": "string" },
      "analysis_notes": { "type": "array", "items": { "type": "string" } },
      "failed_calls": { "type": "array", "items": { "type": "string" } },
      "skipped_calls": { "type": "array", "items": { "type": "string" } },
      "user_message": { "type": "string" }
    },
    "required": ["status", "selected_product_number", "selected_product_name", "crowding_signals", "risk_summary", "analysis_notes", "failed_calls", "skipped_calls", "user_message"],
    "additionalProperties": false
  }
}
```

운영 주의:
- A22는 Ennoia의 오늘 날짜 추가 기능을 켠다.
- `관광지 집중률 예측` 호출에는 `areaCd`, `signguCd`뿐 아니라 선택 상품 장소명 `tAtsNm`도 함께 전달한다.
- 호출은 원 장소명 기준으로 먼저 수행하고 `numOfRows=3`, `pageNo=1`을 사용한다. 원 장소명으로 결과가 없거나 매칭이 없으면 고유 지명/브랜드 중심 fallback query를 소량 추가하되, `마을`, `해변`, `길` 같은 일반 단어 단독 query는 쓰지 않는다.
- 응답의 `baseYmd`가 여러 개이면 오늘 날짜와 같은 행을 우선 선택하고, 없으면 오늘 이후 가장 가까운 날짜를 선택한다. 가장 큰 `baseYmd`를 최신 데이터로 간주하지 않는다.
- 사용자에게 보이는 `risk_summary`, `user_message`, `operation_decision`에는 “API” 같은 내부 용어를 쓰지 않는다.

### A23 OperationsManagerRunbookAgent

```json
{
  "name": "operations_manager_runbook",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "status": { "type": "string", "enum": ["ready", "needs_source_product", "needs_product_selection", "blocked"] },
      "selected_product_number": { "type": "string" },
      "product_name": { "type": "string" },
      "risk_chips": { "type": "array", "items": { "type": "string" } },
      "precheck_items": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "item": { "type": "string" },
            "owner": { "type": "string" },
            "deadline": { "type": "string" }
          },
          "required": ["item", "owner", "deadline"],
          "additionalProperties": false
        }
      },
      "operation_timeline": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "step": { "type": "string" },
            "action": { "type": "string" },
            "staff_note": { "type": "string" }
          },
          "required": ["step", "action", "staff_note"],
          "additionalProperties": false
        }
      },
      "contingencies": { "type": "array", "items": { "type": "string" } },
      "customer_message_templates": { "type": "array", "items": { "type": "string" } },
      "guide_notes": { "type": "array", "items": { "type": "string" } },
      "faq_answers": { "type": "array", "items": { "type": "string" } },
      "user_message": { "type": "string" }
    },
    "required": ["status", "selected_product_number", "product_name", "risk_chips", "precheck_items", "operation_timeline", "contingencies", "customer_message_templates", "guide_notes", "faq_answers", "user_message"],
    "additionalProperties": false
  }
}
```

### A25 MarketingStrategistVisualSignalAgent

```json
{
  "name": "marketing_strategist_visual_signal",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "status": { "type": "string", "enum": ["ready", "needs_source_product", "needs_product_selection", "blocked"] },
      "selected_product_number": { "type": "string" },
      "selected_product_name": { "type": "string" },
      "queries": { "type": "array", "items": { "type": "string" } },
      "visual_assets": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "keyword": { "type": "string" },
            "title": { "type": "string" },
            "image_url": { "type": "string" },
            "photography_location": { "type": "string" },
            "visual_hook": { "type": "string" },
            "suggested_use": { "type": "string" },
            "source_connector": { "type": "string" },
            "license_note": { "type": "string" }
          },
          "required": ["keyword", "title", "image_url", "photography_location", "visual_hook", "suggested_use", "source_connector", "license_note"],
          "additionalProperties": false
        }
      },
      "positioning_hint": { "type": "string" },
      "analysis_notes": { "type": "array", "items": { "type": "string" } },
      "failed_calls": { "type": "array", "items": { "type": "string" } },
      "skipped_calls": { "type": "array", "items": { "type": "string" } },
      "user_message": { "type": "string" }
    },
    "required": ["status", "selected_product_number", "selected_product_name", "queries", "visual_assets", "positioning_hint", "analysis_notes", "failed_calls", "skipped_calls", "user_message"],
    "additionalProperties": false
  }
}
```

### A26 MarketingStrategistCampaignPackageAgent

```json
{
  "name": "marketing_strategist_campaign_package",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "status": { "type": "string", "enum": ["ready", "needs_source_product", "needs_product_selection", "blocked"] },
      "selected_product_number": { "type": "string" },
      "product_name": { "type": "string" },
      "positioning": { "type": "string" },
      "target_messages": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "target": { "type": "string" },
            "message": { "type": "string" },
            "channel": { "type": "string" }
          },
          "required": ["target", "message", "channel"],
          "additionalProperties": false
        }
      },
      "ad_copies": { "type": "array", "items": { "type": "string" } },
      "blog_titles": { "type": "array", "items": { "type": "string" } },
      "instagram_assets": { "type": "array", "items": { "type": "string" } },
      "landing_page_sections": { "type": "array", "items": { "type": "string" } },
      "visual_asset_plan": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "image_url": { "type": "string" },
            "asset_title": { "type": "string" },
            "recommended_placement": { "type": "string" },
            "copy_direction": { "type": "string" },
            "usage_note": { "type": "string" }
          },
          "required": ["image_url", "asset_title", "recommended_placement", "copy_direction", "usage_note"],
          "additionalProperties": false
        }
      },
      "ab_tests": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "test": { "type": "string" },
            "hypothesis": { "type": "string" },
            "variant_a": { "type": "string" },
            "variant_b": { "type": "string" },
            "success_metric": { "type": "string" }
          },
          "required": ["test", "hypothesis", "variant_a", "variant_b", "success_metric"],
          "additionalProperties": false
        }
      },
      "expression_risks": { "type": "array", "items": { "type": "string" } },
      "user_message": { "type": "string" }
    },
    "required": ["status", "selected_product_number", "product_name", "positioning", "target_messages", "ad_copies", "blog_titles", "instagram_assets", "landing_page_sections", "visual_asset_plan", "ab_tests", "expression_risks", "user_message"],
    "additionalProperties": false
  }
}
```

### A28R NotionPagePayloadBuilderAgent

```json
{
  "name": "notion_page_payload_builder",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "status": { "type": "string", "enum": ["ready", "needs_document_selection", "needs_source_document", "invalid_markdown"] },
      "title": { "type": "string" },
      "markdown": { "type": "string" },
      "proposal_type": { "type": "string", "enum": ["travel_recommendation", "poster_result", "product_planner", "operations", "marketing", ""] },
      "selected_document_type": { "type": "string" },
      "user_message": { "type": "string" }
    },
    "required": ["status", "title", "markdown", "proposal_type", "selected_document_type", "user_message"],
    "additionalProperties": false
  }
}
```

운영 주의:
- A28R은 Notion API 커넥터를 호출하지 않는다.
- A28R은 저장할 사용자-facing Markdown을 선택하고 `title`, `markdown`, `proposal_type` payload만 만든다. 선택한 Markdown은 요약/축약/일부 발췌 없이 원문 전체를 사용한다.
- A28은 A28R의 payload를 그대로 사용해 Notion 페이지 생성 API를 한 번 호출하고 URL만 출력한다.
- A28R의 `markdown`에는 A26 같은 JSON Agent의 `last_output`을 넣지 않는다. 마케팅 저장 대상이 없을 때 판매용 상품 기획서 같은 다른 브랜치 문서로 fallback하지 않는다.

If/else:

```text
${preflight_validation.last_output.supported} == true
```

## A03 GeoResolverAgent schema

응답 포맷: `json_schema`

```json
{
  "name": "geo_resolution",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "geo_scope": {
        "type": "object",
        "properties": {
          "status": {
            "type": "string",
            "enum": ["resolved", "unresolved"]
          },
          "input_region": { "type": "string" },
          "resolved_locations": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "name": { "type": "string" },
                "ldong_regn_cd": { "type": "string" },
                "ldong_regn_nm": { "type": "string" },
                "ldong_signgu_cd": { "type": "string" },
                "ldong_signgu_nm": { "type": "string" },
                "confidence": { "type": "number" },
                "reason": { "type": "string" },
                "sub_area_terms": {
                  "type": "array",
                  "items": { "type": "string" }
                },
                "keywords": {
                  "type": "array",
                  "items": { "type": "string" }
                }
              },
              "required": [
                "name",
                "ldong_regn_cd",
                "ldong_regn_nm",
                "ldong_signgu_cd",
                "ldong_signgu_nm",
                "confidence",
                "reason",
                "sub_area_terms",
                "keywords"
              ],
              "additionalProperties": false
            }
          },
          "clarification_candidates": {
            "type": "array",
            "items": { "type": "string" }
          },
          "unsupported_locations": {
            "type": "array",
            "items": { "type": "string" }
          },
          "center": {
            "type": "object",
            "properties": {
              "lat": {
                "anyOf": [
                  { "type": "number" },
                  { "type": "null" }
                ]
              },
              "lng": {
                "anyOf": [
                  { "type": "number" },
                  { "type": "null" }
                ]
              }
            },
            "required": ["lat", "lng"],
            "additionalProperties": false
          },
          "radius_m": { "type": "integer" },
          "confidence": {
            "type": "string",
            "enum": ["low", "medium", "high"]
          }
        },
        "required": [
          "status",
          "input_region",
          "resolved_locations",
          "clarification_candidates",
          "unsupported_locations",
          "center",
          "radius_m",
          "confidence"
        ],
        "additionalProperties": false
      },
      "geo_warnings": {
        "type": "array",
        "items": { "type": "string" }
      },
      "geo_resolved": { "type": "boolean" }
    },
    "required": ["geo_scope", "geo_warnings", "geo_resolved"],
    "additionalProperties": false
  }
}
```

If/else:

```text
${geo_resolution.last_output.geo_resolved} == true
```

## A06 DataGapProfilerAgent schema

응답 포맷: `json_schema`

```json
{
  "name": "data_gap_profile",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "data_gap_report": {
        "type": "object",
        "properties": {
          "gaps": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "gap_id": { "type": "string" },
                "gap_type": { "type": "string" },
                "severity": {
                  "type": "string",
                  "enum": ["low", "medium", "high"]
                },
                "source_item_id": { "type": "string" },
                "target_content_id": { "type": "string" },
                "target_content_type_id": { "type": "string" },
                "target_title": { "type": "string" },
                "reason": { "type": "string" },
                "suggested_source_family": { "type": "string" },
                "related_gap_types": {
                  "type": "array",
                  "items": { "type": "string" }
                }
              },
              "required": [
                "gap_id",
                "gap_type",
                "severity",
                "source_item_id",
                "target_content_id",
                "target_content_type_id",
                "target_title",
                "reason",
                "suggested_source_family",
                "related_gap_types"
              ],
              "additionalProperties": false
            }
          },
          "global_gaps": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "gap_id": { "type": "string" },
                "gap_type": { "type": "string" },
                "severity": {
                  "type": "string",
                  "enum": ["low", "medium", "high"]
                },
                "reason": { "type": "string" },
                "suggested_source_family": { "type": "string" }
              },
              "required": [
                "gap_id",
                "gap_type",
                "severity",
                "reason",
                "suggested_source_family"
              ],
              "additionalProperties": false
            }
          },
          "do_not_claim_yet": {
            "type": "array",
            "items": { "type": "string" }
          }
        },
        "required": ["gaps", "global_gaps", "do_not_claim_yet"],
        "additionalProperties": false
      },
      "data_coverage": {
        "type": "object",
        "properties": {
          "candidate_count": { "type": "integer" },
          "gap_count": { "type": "integer" },
          "overall_gap_level": {
            "type": "string",
            "enum": ["none", "low", "medium", "high"]
          }
        },
        "required": ["candidate_count", "gap_count", "overall_gap_level"],
        "additionalProperties": false
      },
      "unresolved_gaps": {
        "type": "array",
        "items": { "type": "string" }
      },
      "enrichment_needed": { "type": "boolean" },
      "route_status": {
        "type": "string",
        "enum": ["ENRICHMENT_NEEDED", "NO_ENRICHMENT_NEEDED"]
      }
    },
    "required": [
      "data_gap_report",
      "data_coverage",
      "unresolved_gaps",
      "enrichment_needed",
      "route_status"
    ],
    "additionalProperties": false
  }
}
```

If/else:

```text
${data_gap_profile.last_output.enrichment_needed} == true
```

또는 route_status를 직접 쓰는 구성이 더 안정적으로 보이면:

```text
${data_gap_profile.last_output.route_status} == "ENRICHMENT_NEEDED"
```

## A05B SupplementalTourApiCollectorAgent schema

응답 포맷: `json_schema`

이 schema는 A05 reduced schema를 사용한다.
키워드/축제/숙박 보조 후보를 모두 `supplemental_candidates` 하나로 출력한다.
Ennoia의 structured output 검증에서는 아래 보조 필드도 required string으로 처리한다.
값이 없는 보조 string 필드는 빈 문자열 `""`로 둔다.
`null` 또는 문자열 `"null"`은 잘못된 값이다.

```json
{
  "name": "supplemental_tourapi_collector",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "supplemental_candidates": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "id": { "type": "string" },
            "source": {
              "type": "string",
              "enum": ["tourapi"]
            },
            "content_id": { "type": "string" },
            "content_type_id": { "type": "string" },
            "title": { "type": "string" },
            "address": { "type": "string" },
            "map_x": { "type": "string" },
            "map_y": { "type": "string" },
            "ldong_regn_cd": { "type": "string" },
            "ldong_signgu_cd": { "type": "string" },
            "collection_sources": {
              "type": "array",
              "items": { "type": "string" }
            },
            "overview": { "type": "string" },
            "image_url": { "type": "string" },
            "area_code": { "type": "string" },
            "sigungu_code": { "type": "string" },
            "event_start_date": { "type": "string" },
            "event_end_date": { "type": "string" }
          },
          "required": [
            "id",
            "source",
            "content_id",
            "content_type_id",
            "title",
            "address",
            "map_x",
            "map_y",
            "ldong_regn_cd",
            "ldong_signgu_cd",
            "collection_sources",
            "overview",
            "image_url",
            "area_code",
            "sigungu_code",
            "event_start_date",
            "event_end_date"
          ],
          "additionalProperties": false
        }
      }
    },
    "required": ["supplemental_candidates"],
    "additionalProperties": false
  }
}
```

## A05D CandidateMergeDedupeAgent schema

응답 포맷: `json_schema`

이 schema는 A05 reduced schema를 유지한다.
이제 A05D는 병합/중복 제거/지역 재필터와 shortlist 선정을 한 번에 수행하므로 최상위 키는 `merged_candidates`가 아니라 `source_items`다.
`overview`, `image_url`, `area_code`, `sigungu_code`, `event_start_date`, `event_end_date`는 보조 string 필드다.
Ennoia strict json_schema에서는 이 필드들을 required string으로 넣고, 값이 없으면 빈 문자열 `""`로 출력한다.
`null` 또는 문자열 `"null"`은 잘못된 값이다.
아래 schema를 사용한다.

```json
{
  "name": "candidate_merge_dedupe",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "source_items": {
        "type": "array",
        "maxItems": 15,
        "items": {
          "type": "object",
          "properties": {
            "id": { "type": "string" },
            "source": {
              "type": "string",
              "enum": ["tourapi"]
            },
            "content_id": { "type": "string" },
            "content_type_id": { "type": "string" },
            "title": { "type": "string" },
            "address": { "type": "string" },
            "map_x": { "type": "string" },
            "map_y": { "type": "string" },
            "ldong_regn_cd": { "type": "string" },
            "ldong_signgu_cd": { "type": "string" },
            "collection_sources": {
              "type": "array",
              "items": { "type": "string" }
            },
            "location_check": {
              "type": "string",
              "enum": ["matched", "needs_review"]
            },
            "overview": { "type": "string" },
            "image_url": { "type": "string" },
            "area_code": { "type": "string" },
            "sigungu_code": { "type": "string" },
            "event_start_date": { "type": "string" },
            "event_end_date": { "type": "string" }
          },
          "required": [
            "id",
            "source",
            "content_id",
            "content_type_id",
            "title",
            "address",
            "map_x",
            "map_y",
            "ldong_regn_cd",
            "ldong_signgu_cd",
            "collection_sources",
            "location_check",
            "overview",
            "image_url",
            "area_code",
            "sigungu_code",
            "event_start_date",
            "event_end_date"
          ],
          "additionalProperties": false
        }
      }
    },
    "required": ["source_items"],
    "additionalProperties": false
  }
}
```

## 나머지 JSON Agent 붙여넣기 schema

아래 schema를 Ennoia Agent 응답 포맷의 `json_schema`에 그대로 붙여넣는다.
A05 계열은 Ennoia structured output 검증에서 `null`이 string 필드로 변환되지 않는 것을 확인했으므로, 빈 값은 `null`이 아니라 빈 문자열 `""`로 둔다.

### A02 PlannerAgent

```json
{
  "name": "planner",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "normalized_request": {
        "type": "object",
        "properties": {
          "region": { "type": "string" },
          "period": { "type": "string" },
          "target_customers": { "type": "array", "items": { "type": "string" } },
          "themes": { "type": "array", "items": { "type": "string" } },
          "constraints": { "type": "array", "items": { "type": "string" } },
          "requested_outputs": { "type": "array", "items": { "type": "string" } },
          "product_count": { "type": "integer" }
        },
        "required": ["region", "period", "target_customers", "themes", "constraints", "requested_outputs", "product_count"],
        "additionalProperties": false
      },
      "assumptions": { "type": "array", "items": { "type": "string" } },
      "missing_inputs": { "type": "array", "items": { "type": "string" } },
      "execution_plan": { "type": "array", "items": { "type": "string" } }
    },
    "required": ["normalized_request", "assumptions", "missing_inputs", "execution_plan"],
    "additionalProperties": false
  }
}
```

### A05 BaselineSearchPlanAgent

```json
{
  "name": "baseline_search_plan",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "core_area": { "type": "boolean" },
      "keyword": { "type": "boolean" },
      "optional_festival": { "type": "boolean" },
      "optional_stay": { "type": "boolean" },
      "keyword_queries": { "type": "array", "items": { "type": "string" } },
      "eventStartDate": { "type": "string" },
      "eventEndDate": { "type": "string" },
      "ldong_regn_cd": { "type": "string" },
      "ldong_signgu_cd": { "type": "string" },
      "resolved_region_name": { "type": "string" },
      "reason": { "type": "string" }
    },
    "required": ["core_area", "keyword", "optional_festival", "optional_stay", "keyword_queries", "eventStartDate", "eventEndDate", "ldong_regn_cd", "ldong_signgu_cd", "resolved_region_name", "reason"],
    "additionalProperties": false
  }
}
```

### A05A CoreTourApiCollectorAgent

```json
{
  "name": "core_tourapi_collector",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "core_candidates": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "id": { "type": "string" },
            "source": { "type": "string", "enum": ["tourapi"] },
            "content_id": { "type": "string" },
            "content_type_id": { "type": "string" },
            "title": { "type": "string" },
            "address": { "type": "string" },
            "map_x": { "type": "string" },
            "map_y": { "type": "string" },
            "ldong_regn_cd": { "type": "string" },
            "ldong_signgu_cd": { "type": "string" },
            "collection_sources": { "type": "array", "items": { "type": "string" } },
            "overview": { "type": "string" },
            "image_url": { "type": "string" },
            "area_code": { "type": "string" },
            "sigungu_code": { "type": "string" },
            "event_start_date": { "type": "string" },
            "event_end_date": { "type": "string" }
          },
          "required": ["id", "source", "content_id", "content_type_id", "title", "address", "map_x", "map_y", "ldong_regn_cd", "ldong_signgu_cd", "collection_sources", "overview", "image_url", "area_code", "sigungu_code", "event_start_date", "event_end_date"],
          "additionalProperties": false
        }
      }
    },
    "required": ["core_candidates"],
    "additionalProperties": false
  }
}
```

A05B SupplementalTourApiCollectorAgent schema는 위 `A05B SupplementalTourApiCollectorAgent schema` 섹션의 `supplemental_tourapi_collector`를 사용한다.
A05D CandidateMergeDedupeAgent schema는 위 `A05D CandidateMergeDedupeAgent schema` 섹션의 `candidate_merge_dedupe`를 사용한다.

### A07 ApiCapabilityRouterAgent

A07 라우팅 규칙:
- `gap_type`뿐 아니라 `related_gap_types`도 lane 분배 기준으로 사용한다.
- `missing_detail_info`는 `tourapi_detail`로 보낸다.
- `missing_operating_hours`, `missing_booking_info`, `missing_image_asset` 중 소개정보/이미지정보가 필요한 gap은 `tourapi_intro_image`로 보낼 수 있다.
- `missing_image_asset` 또는 `missing_visual_reference`는 `visual_data`로 보낸다.
- `gap_type`이 `missing_detail_info`이고 `related_gap_types`에 `missing_image_asset`이 있으면 같은 gap을 `tourapi_detail`과 `visual_data` 양쪽 route에 포함한다.
- `related_gap_types`에 `missing_image_asset`이 있으면 visual 의도가 명시되지 않았더라도 `VisualDataEnrichmentAgent` 또는 `TourApiIntroImageEnrichmentAgent`를 `orchestrator_instruction.call_agents`에 포함한다.
- `missing_image_asset` 때문에 `visual_data`로 보낼 때 route의 `source_families`에는 `kto_tourism_photo`를 포함한다.
- `orchestrator_instruction.api_calls`는 Agent별 실제 호출 커넥터를 지정한다.

```json
{
  "name": "api_capability_router",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "capability_routing": {
        "type": "object",
        "properties": {
          "routes": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "lane": { "type": "string", "enum": ["tourapi_detail", "tourapi_intro_image", "visual_data", "route_signal", "theme_data"] },
                "enabled": { "type": "boolean" },
                "gap_ids": { "type": "array", "items": { "type": "string" } },
                "source_item_ids": { "type": "array", "items": { "type": "string" } },
                "source_families": { "type": "array", "items": { "type": "string" } },
                "reason": { "type": "string" }
              },
              "required": ["lane", "enabled", "gap_ids", "source_item_ids", "source_families", "reason"],
              "additionalProperties": false
            }
          },
          "skipped_routes": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "lane": { "type": "string", "enum": ["tourapi_detail", "tourapi_intro_image", "visual_data", "route_signal", "theme_data"] },
                "reason": { "type": "string" }
              },
              "required": ["lane", "reason"],
              "additionalProperties": false
            }
          },
          "routing_summary": {
            "type": "object",
            "properties": {
              "enabled_lanes": { "type": "array", "items": { "type": "string" } },
              "gap_count": { "type": "integer" }
            },
            "required": ["enabled_lanes", "gap_count"],
            "additionalProperties": false
          },
          "orchestrator_instruction": {
            "type": "object",
            "properties": {
              "call_agents": { "type": "array", "items": { "type": "string" } },
              "api_calls": {
                "type": "array",
                "items": {
                  "type": "object",
                  "properties": {
                    "agent": { "type": "string" },
                    "lane": { "type": "string" },
                    "connectors": { "type": "array", "items": { "type": "string" } },
                    "gap_ids": { "type": "array", "items": { "type": "string" } },
                    "source_item_ids": { "type": "array", "items": { "type": "string" } }
                  },
                  "required": ["agent", "lane", "connectors", "gap_ids", "source_item_ids"],
                  "additionalProperties": false
                }
              },
              "do_not_call_agents": { "type": "array", "items": { "type": "string" } },
              "brief": { "type": "string" }
            },
            "required": ["call_agents", "api_calls", "do_not_call_agents", "brief"],
            "additionalProperties": false
          }
        },
        "required": ["routes", "skipped_routes", "routing_summary", "orchestrator_instruction"],
        "additionalProperties": false
      }
    },
    "required": ["capability_routing"],
    "additionalProperties": false
  }
}
```

### A07A, A07A2, A07B~A07D 비활성 lane 원칙

A07A, A07A2, A07B~A07D는 Orchestrator가 아니라 순차 실행되는 일반 Agent 노드다.
각 Agent는 `capability_routing.orchestrator_instruction.call_agents`에 자기 이름이 있으면 API를 호출하고, 없으면 API 호출 없이 같은 schema의 빈 `lane_enrichment`를 출력한다.
call_agents에 자기 이름이 있더라도 실제 호출 API는 `capability_routing.orchestrator_instruction.api_calls[].connectors`를 우선한다.

비활성 lane이라고 해서 schema를 별도로 만들거나 required field를 제거하지 않는다.
A08이 다섯 lane 출력을 항상 병합할 수 있어야 하므로 required key는 유지하고, lane별 결과 배열만 `[]`로 둔다.

예:
- A07A 비활성: `{"lane_enrichment":{"lane":"tourapi_detail","failed_calls":[],"enriched_items":[],"skipped_calls":[]}}`
- A07A2 비활성: `{"lane_enrichment":{"lane":"tourapi_intro_image","failed_calls":[],"enriched_items":[],"skipped_calls":[]}}`
- A07B 비활성: `{"lane_enrichment":{"lane":"visual_data","failed_calls":[],"visual_assets":[],"skipped_calls":[]}}`
- A07C 비활성: `{"lane_enrichment":{"lane":"route_signal","failed_calls":[],"route_signals":[],"skipped_calls":[]}}`
- A07D 비활성: `{"lane_enrichment":{"lane":"theme_data","failed_calls":[],"skipped_calls":[],"theme_candidates":[]}}`

### A07A TourApiDetailEnrichmentAgent

```json
{
  "name": "tourapi_detail_enrichment",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "lane_enrichment": {
        "type": "object",
        "properties": {
          "lane": { "type": "string", "enum": ["tourapi_detail"] },
          "failed_calls": { "type": "array", "items": { "type": "string" } },
          "enriched_items": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "source_item_id": { "type": "string" },
                "content_id": { "type": "string" },
                "fields_added": { "type": "array", "items": { "type": "string" } },
                "images": { "type": "array", "maxItems": 6, "items": { "type": "string" } },
                "evidence_snippets": { "type": "array", "items": { "type": "string" } },
                "remaining_gaps": { "type": "array", "items": { "type": "string" } }
              },
              "required": ["source_item_id", "content_id", "fields_added", "images", "evidence_snippets", "remaining_gaps"],
              "additionalProperties": false
            }
          },
          "skipped_calls": { "type": "array", "items": { "type": "string" } }
        },
        "required": ["lane", "failed_calls", "enriched_items", "skipped_calls"],
        "additionalProperties": false
      }
    },
    "required": ["lane_enrichment"],
    "additionalProperties": false
  }
}
```

주의:
- `fields_added`는 반드시 문자열 배열이다. `{ "detail_info": [...] }` 같은 object를 출력하면 structured output 파싱이 실패한다.
- 추가된 값이 없으면 `fields_added: []`로 둔다. 빈 object `{}`를 쓰지 않는다.
- 예: `"fields_added": ["detail_info=입장료: 무료", "detail_info=화장실: 있음"]`
- A05D CandidateMergeDedupeAgent가 이미 후보 수를 줄였으므로 A07A에는 별도 후보 개수 제한을 두지 않는다.
- A07A의 각 `enriched_items[].images`는 최대 6개만 출력한다.
- A07A는 `관광정보 공통상세`, `관광정보 반복정보`만 담당한다.
- A07A 상세 커넥터의 `numOfRows`는 후보 개수 제한이 아니라 해당 `contentId` 내부 응답 row 수 제한이다. 기준은 `detailCommon2=10`, `detailInfo2=5`다.
- `missing_detail_info` 또는 overview 누락 gap이 있으면 `관광정보 공통상세`를 1순위로 호출한다.
- 공통상세 응답에 `homepage`가 있으면 `fields_added`에 `detail_common=homepage: URL` 형식으로 남긴다.
- API 값이 HTML anchor이면 `href` URL만 추출하고, 설명 문구와 URL이 섞인 값이면 실제 URL만 추출한다. `www.`로 시작하면 `https://`를 붙여 저장한다.
- A07A의 `failed_calls`에는 `reason=call_failed`만 단독으로 남기지 않는다. 구체 오류가 없으면 `connector_invocation_unverified` 또는 `connector_mapping_suspect`처럼 커넥터 설정 확인이 필요한 상태로 남긴다.
- `관광정보 반복정보`만 성공한 경우 요금/시설 보조 정보는 생길 수 있지만 overview gap은 해소된 것으로 보지 않는다.
- 처리하지 못한 contentId 또는 호출하지 못한 API는 `skipped_calls` 또는 `failed_calls`에 반드시 기록한다.
- `failed_calls`에는 가능하면 `resultCode`, `resultMsg`, invalid parameter 이름을 포함한다. 단순 `reason=call_failed`만 있으면 커넥터 디버깅이 어렵다.
- `executed_calls`는 출력하지 않는다. 호출 성공 목록은 Ennoia 실행 로그에서 확인하고, JSON에는 실패/스킵/보강 결과만 남긴다.

### A07A2 TourApiIntroImageEnrichmentAgent

```json
{
  "name": "tourapi_intro_image_enrichment",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "lane_enrichment": {
        "type": "object",
        "properties": {
          "lane": { "type": "string", "enum": ["tourapi_intro_image"] },
          "failed_calls": { "type": "array", "items": { "type": "string" } },
          "enriched_items": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "source_item_id": { "type": "string" },
                "content_id": { "type": "string" },
                "fields_added": { "type": "array", "items": { "type": "string" } },
                "images": { "type": "array", "maxItems": 6, "items": { "type": "string" } },
                "evidence_snippets": { "type": "array", "items": { "type": "string" } },
                "remaining_gaps": { "type": "array", "items": { "type": "string" } }
              },
              "required": ["source_item_id", "content_id", "fields_added", "images", "evidence_snippets", "remaining_gaps"],
              "additionalProperties": false
            }
          },
          "skipped_calls": { "type": "array", "items": { "type": "string" } }
        },
        "required": ["lane", "failed_calls", "enriched_items", "skipped_calls"],
        "additionalProperties": false
      }
    },
    "required": ["lane_enrichment"],
    "additionalProperties": false
  }
}
```

주의:
- A07A2는 `관광정보 소개정보`, `관광정보 이미지정보`만 담당한다.
- A07A2 상세 커넥터의 `numOfRows` 기준은 `detailIntro2=5`, `detailImage2=10`이다.
- 소개정보 응답의 URL성 필드는 기존 `fields_added` 문자열로 남긴다. 특히 `eventhomepage`, `bookingplace`, `reservationurl`, `reservationlodging`, `reservation`, `reservationfood`는 값이 있으면 누락하지 않는다.
- 이미지정보 결과는 `images`에 최대 6개 URL만 남긴다.
- 소개정보/이미지정보만으로 overview gap을 해결했다고 판단하지 않는다.
- 처리하지 못한 contentId 또는 호출하지 못한 API는 `skipped_calls` 또는 `failed_calls`에 반드시 기록한다.

### A07B VisualDataEnrichmentAgent

주의:
- 관광사진 키워드 검색 결과가 0건이면 API 실패가 아니다.
- 결과 0건은 `failed_calls`가 아니라 `skipped_calls`에 `관광사진 키워드 검색:keyword=...:reason=no_items`로 남긴다.
- `failed_calls`에는 커넥터 호출 실패, 인증 오류, 요청 파라미터 오류, 응답 파싱 실패처럼 실제 실패만 넣는다.
- `visual_assets`는 전체 최대 6개만 출력한다.
- A07B의 `관광사진 키워드 검색(gallerySearchList1)` 호출은 keyword별 사진 목록을 `numOfRows=6&pageNo=1`로 요청한다. 여러 keyword 호출 후에도 최종 `visual_assets`는 최대 6개만 남긴다.

```json
{
  "name": "visual_data_enrichment",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "lane_enrichment": {
        "type": "object",
        "properties": {
          "lane": { "type": "string", "enum": ["visual_data"] },
          "failed_calls": { "type": "array", "items": { "type": "string" } },
          "visual_assets": {
            "type": "array",
            "maxItems": 6,
            "items": {
              "type": "object",
              "properties": {
                "source_item_id": { "type": "string" },
                "keyword": { "type": "string" },
                "title": { "type": "string" },
                "image_url": { "type": "string" },
                "source_connector": { "type": "string" },
                "license_note": { "type": "string" }
              },
              "required": ["source_item_id", "keyword", "title", "image_url", "source_connector", "license_note"],
              "additionalProperties": false
            }
          },
          "skipped_calls": { "type": "array", "items": { "type": "string" } }
        },
        "required": ["lane", "failed_calls", "visual_assets", "skipped_calls"],
        "additionalProperties": false
      }
    },
    "required": ["lane_enrichment"],
    "additionalProperties": false
  }
}
```

### A07C RouteSignalEnrichmentAgent

```json
{
  "name": "route_signal_enrichment",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "lane_enrichment": {
        "type": "object",
        "properties": {
          "lane": { "type": "string", "enum": ["route_signal"] },
          "failed_calls": { "type": "array", "items": { "type": "string" } },
          "route_signals": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "source_item_id": { "type": "string" },
                "keyword": { "type": "string" },
                "signal_type": { "type": "string" },
                "title": { "type": "string" },
                "value": { "type": "string" },
                "source_connector": { "type": "string" },
                "notes": { "type": "string" }
              },
              "required": ["source_item_id", "keyword", "signal_type", "title", "value", "source_connector", "notes"],
              "additionalProperties": false
            }
          },
          "skipped_calls": { "type": "array", "items": { "type": "string" } }
        },
        "required": ["lane", "failed_calls", "route_signals", "skipped_calls"],
        "additionalProperties": false
      }
    },
    "required": ["lane_enrichment"],
    "additionalProperties": false
  }
}
```

### A07D ThemeDataEnrichmentAgent

```json
{
  "name": "theme_data_enrichment",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "lane_enrichment": {
        "type": "object",
        "properties": {
          "lane": { "type": "string", "enum": ["theme_data"] },
          "failed_calls": { "type": "array", "items": { "type": "string" } },
          "skipped_calls": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "connector": { "type": "string" },
                "reason": { "type": "string" }
              },
              "required": ["connector", "reason"],
              "additionalProperties": false
            }
          },
          "theme_candidates": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "id": { "type": "string" },
                "source": { "type": "string" },
                "source_category": { "type": "string" },
                "content_id": { "type": "string" },
                "title": { "type": "string" },
                "address": { "type": "string" },
                "map_x": { "type": "string" },
                "map_y": { "type": "string" },
                "image_url": { "type": "string" },
                "overview": { "type": "string" },
                "matched_keyword": { "type": "string" },
                "related_source_item_ids": { "type": "array", "items": { "type": "string" } },
                "raw_reference": { "type": "string" }
              },
              "required": ["id", "source", "source_category", "content_id", "title", "address", "map_x", "map_y", "image_url", "overview", "matched_keyword", "related_source_item_ids", "raw_reference"],
              "additionalProperties": false
            }
          }
        },
        "required": ["lane", "failed_calls", "skipped_calls", "theme_candidates"],
        "additionalProperties": false
      }
    },
    "required": ["lane_enrichment"],
    "additionalProperties": false
  }
}
```

주의:
- 웰니스 API 응답 item에 `homepage`가 있으면 `theme_candidates[].raw_reference`에 `homepage: URL` 형식으로 보존한다.
- 반려동물 동반 상세/공통 상세 응답에 `homepage`가 있으면 `theme_candidates[].raw_reference`에 `homepage: URL` 형식으로 보존한다.
- 테마 계열 응답의 `eventhomepage`, `reservationurl` 같은 URL성 필드도 `raw_reference`에 원래 필드명으로 보존한다.
- URL 값이 HTML anchor 형태이면 `href`만 사용하고, 설명 문구와 URL이 섞인 값이면 실제 URL만 추출한다. `www.`로 시작하면 `https://`를 붙인다.
- 홈페이지나 예약 URL이 없어도 theme 후보를 제외하지 않는다.

### A08 EnrichmentResultMergeAgent

```json
{
  "name": "enrichment_result_merge",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "enrichment_summary": {
        "type": "object",
        "properties": {
          "enriched_items": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "source_item_id": { "type": "string" },
                "content_id": { "type": "string" },
                "fields_added": { "type": "array", "items": { "type": "string" } },
                "images": { "type": "array", "maxItems": 6, "items": { "type": "string" } },
                "evidence_snippets": { "type": "array", "items": { "type": "string" } },
                "remaining_gaps": { "type": "array", "items": { "type": "string" } },
                "supporting_lanes": { "type": "array", "items": { "type": "string" } }
              },
              "required": ["source_item_id", "content_id", "fields_added", "images", "evidence_snippets", "remaining_gaps", "supporting_lanes"],
              "additionalProperties": false
            }
          },
          "visual_assets": { "type": "array", "maxItems": 6, "items": { "type": "string" } },
          "route_signals": { "type": "array", "items": { "type": "string" } },
          "theme_candidates": {
            "type": "array",
            "maxItems": 30,
            "items": {
              "type": "object",
              "properties": {
                "id": { "type": "string" },
                "source": { "type": "string" },
                "source_category": { "type": "string" },
                "content_id": { "type": "string" },
                "title": { "type": "string" },
                "address": { "type": "string" },
                "map_x": { "type": "string" },
                "map_y": { "type": "string" },
                "image_url": { "type": "string" },
                "overview": { "type": "string" },
                "matched_keyword": { "type": "string" },
                "related_source_item_ids": { "type": "array", "items": { "type": "string" } },
                "raw_reference": { "type": "string" }
              },
              "required": ["id", "source", "source_category", "content_id", "title", "address", "map_x", "map_y", "image_url", "overview", "matched_keyword", "related_source_item_ids", "raw_reference"],
              "additionalProperties": false
            }
          },
          "failed_calls": { "type": "array", "items": { "type": "string" } },
          "skipped_calls": { "type": "array", "items": { "type": "string" } },
          "coverage_by_lane": {
            "type": "object",
            "properties": {
              "tourapi_detail": { "type": "string", "enum": ["enriched", "partial", "empty", "not_run", "failed"] },
              "tourapi_intro_image": { "type": "string", "enum": ["enriched", "partial", "empty", "not_run", "failed"] },
              "visual_data": { "type": "string", "enum": ["enriched", "partial", "empty", "not_run", "failed"] },
              "route_signal": { "type": "string", "enum": ["enriched", "partial", "empty", "not_run", "failed"] },
              "theme_data": { "type": "string", "enum": ["enriched", "partial", "empty", "not_run", "failed"] }
            },
            "required": ["tourapi_detail", "tourapi_intro_image", "visual_data", "route_signal", "theme_data"],
            "additionalProperties": false
          },
          "notes_for_evidence_fusion": { "type": "array", "items": { "type": "string" } }
        },
        "required": ["enriched_items", "visual_assets", "route_signals", "theme_candidates", "failed_calls", "skipped_calls", "coverage_by_lane", "notes_for_evidence_fusion"],
        "additionalProperties": false
      }
    },
    "required": ["enrichment_summary"],
    "additionalProperties": false
  }
}
```

주의:
- A08의 `enriched_items`는 object 배열이다. JSON 객체를 문자열로 감싼 값은 쓰지 않는다.
- `coverage_by_lane`은 일부 API만 성공하거나 remaining_gaps가 남으면 `partial`을 사용할 수 있다.
- A08의 `failed_calls`, `skipped_calls`는 문자열 배열이다. A07D처럼 입력 lane에 object 형태의 skipped call이 있으면 `connector=...:reason=...` 형식의 문자열로 정규화한다.
- A08은 A07A/A07A2/A07B 입력에 이미지가 더 많아도 `enriched_items[].images`와 `visual_assets`를 각각 최대 6개로 잘라 출력한다.

### A09 DataAnalystAgent

```json
{
  "name": "data_analyst",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "evidence_profile": {
        "type": "object",
        "properties": {
          "evidence_cards": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "id": { "type": "string" },
                "claim": { "type": "string" },
                "supporting_sources": { "type": "array", "items": { "type": "string" } },
                "confidence": { "type": "string", "enum": ["low", "medium", "high"] },
                "usable_for_marketing": { "type": "boolean" },
                "notes": { "type": "string" }
              },
              "required": ["id", "claim", "supporting_sources", "confidence", "usable_for_marketing", "notes"],
              "additionalProperties": false
            }
          }
        },
        "required": ["evidence_cards"],
        "additionalProperties": false
      },
      "productization_advice": { "type": "array", "items": { "type": "string" } },
      "data_coverage": {
        "type": "object",
        "properties": {
          "coverage_level": { "type": "string", "enum": ["low", "medium", "high"] },
          "covered": { "type": "array", "items": { "type": "string" } },
          "weak": { "type": "array", "items": { "type": "string" } },
          "missing": { "type": "array", "items": { "type": "string" } }
        },
        "required": ["coverage_level", "covered", "weak", "missing"],
        "additionalProperties": false
      },
      "unresolved_gaps": { "type": "array", "items": { "type": "string" } },
      "source_confidence": {
        "type": "object",
        "properties": {
          "overall": { "type": "string", "enum": ["low", "medium", "high"] },
          "reason": { "type": "string" }
        },
        "required": ["overall", "reason"],
        "additionalProperties": false
      },
      "do_not_claim": { "type": "array", "items": { "type": "string" } }
    },
    "required": ["evidence_profile", "productization_advice", "data_coverage", "unresolved_gaps", "source_confidence", "do_not_claim"],
    "additionalProperties": false
  }
}
```

### A10 ResearchAnalystAgent

```json
{
  "name": "research_analyst",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "research_summary": {
        "type": "object",
        "properties": {
          "regional_context": { "type": "string" },
          "target_insights": { "type": "array", "items": { "type": "string" } },
          "seasonality": { "type": "array", "items": { "type": "string" } },
          "opportunity_areas": { "type": "array", "items": { "type": "string" } },
          "constraints": { "type": "array", "items": { "type": "string" } },
          "evidence_refs": { "type": "array", "items": { "type": "string" } }
        },
        "required": ["regional_context", "target_insights", "seasonality", "opportunity_areas", "constraints", "evidence_refs"],
        "additionalProperties": false
      }
    },
    "required": ["research_summary"],
    "additionalProperties": false
  }
}
```

### A11 ProductManagerAgent

`product_ideas` 배열 길이는 PlannerAgent의 `normalized_request.product_count`와 같아야 한다.
JSON Schema는 동적 값 기반 `minItems/maxItems`를 강제할 수 없으므로, 프롬프트에서 개수 준수를 강제한다.
`evidence_cards`가 상품 수보다 적어도 상품 수를 줄이지 않고, 확인된 장소명과 `productization_advice`, `opportunity_areas`, `target_insights`를 사용해 서로 다른 콘셉트의 상품을 보수적으로 만든다.
홈페이지 URL 또는 예약 URL이 없다는 이유로 상품 후보를 제외하거나 상품 수를 줄이지 않는다.
상품 수를 줄일 수 있는 경우는 근거 카드가 완전히 비어 있거나 확인된 장소/동선 후보가 요청 수보다 적어 상품 자체를 구성할 수 없는 경우로 제한한다.

```json
{
  "name": "product_manager",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "product_ideas": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "name": { "type": "string" },
            "one_liner": { "type": "string" },
            "target": { "type": "string" },
            "concept": { "type": "string" },
            "itinerary": { "type": "array", "items": { "type": "string" } },
            "included_places": { "type": "array", "items": { "type": "string" } },
            "differentiators": { "type": "array", "items": { "type": "string" } },
            "evidence_refs": { "type": "array", "items": { "type": "string" } },
            "operational_risks": { "type": "array", "items": { "type": "string" } },
            "do_not_claim": { "type": "array", "items": { "type": "string" } }
          },
          "required": ["name", "one_liner", "target", "concept", "itinerary", "included_places", "differentiators", "evidence_refs", "operational_risks", "do_not_claim"],
          "additionalProperties": false
        }
      }
    },
    "required": ["product_ideas"],
    "additionalProperties": false
  }
}
```

### A12 BrandMarketingLeadAgent

```json
{
  "name": "brand_marketing_lead",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "marketing_assets": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "product_name": { "type": "string" },
            "marketing_strategy": {
              "type": "object",
              "properties": {
                "positioning": { "type": "string" },
                "target_message": { "type": "string" },
                "channels": { "type": "array", "items": { "type": "string" } },
                "conversion_goal": { "type": "string" }
              },
              "required": ["positioning", "target_message", "channels", "conversion_goal"],
              "additionalProperties": false
            },
            "landing_page_outline": { "type": "array", "items": { "type": "string" } },
            "faq_strategy": { "type": "array", "items": { "type": "string" } },
            "sns_campaign": { "type": "array", "items": { "type": "string" } },
            "claim_strategy": {
              "type": "object",
              "properties": {
                "allowed_claims": { "type": "array", "items": { "type": "string" } },
                "claims_requiring_verification": { "type": "array", "items": { "type": "string" } },
                "prohibited_claims": { "type": "array", "items": { "type": "string" } }
              },
              "required": ["allowed_claims", "claims_requiring_verification", "prohibited_claims"],
              "additionalProperties": false
            },
            "sales_copy": {
              "type": "object",
              "properties": {
                "headline": { "type": "string" },
                "subcopy": { "type": "string" },
                "cta": { "type": "string" }
              },
              "required": ["headline", "subcopy", "cta"],
              "additionalProperties": false
            },
            "evidence_refs": { "type": "array", "items": { "type": "string" } }
          },
          "required": ["product_name", "marketing_strategy", "landing_page_outline", "faq_strategy", "sns_campaign", "claim_strategy", "sales_copy", "evidence_refs"],
          "additionalProperties": false
        }
      }
    },
    "required": ["marketing_assets"],
    "additionalProperties": false
  }
}
```

### A12B GrowthMarketingLeadAgent

```json
{
  "name": "growth_marketing_lead",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "growth_marketing_assets": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "product_name": { "type": "string" },
            "growth_goal": { "type": "string" },
            "acquisition_channels": { "type": "array", "items": { "type": "string" } },
            "experiments": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "hypothesis": { "type": "string" },
                  "execution": { "type": "string" },
                  "success_metric": { "type": "string" }
                },
                "required": ["hypothesis", "execution", "success_metric"],
                "additionalProperties": false
              }
            },
            "landing_tests": { "type": "array", "items": { "type": "string" } },
            "metrics": { "type": "array", "items": { "type": "string" } },
            "verification_needed": { "type": "array", "items": { "type": "string" } },
            "risk_controls": { "type": "array", "items": { "type": "string" } },
            "evidence_refs": { "type": "array", "items": { "type": "string" } }
          },
          "required": ["product_name", "growth_goal", "acquisition_channels", "experiments", "landing_tests", "metrics", "verification_needed", "risk_controls", "evidence_refs"],
          "additionalProperties": false
        }
      }
    },
    "required": ["growth_marketing_assets"],
    "additionalProperties": false
  }
}
```

### A13 QAComplianceManagerAgent

```json
{
  "name": "qa_compliance_manager",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "qa_report": {
        "type": "object",
        "properties": {
          "overall_status": { "type": "string", "enum": ["approved", "review_required", "blocked"] },
          "issues": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "severity": { "type": "string", "enum": ["low", "medium", "high"] },
                "category": { "type": "string" },
                "description": { "type": "string" },
                "affected_section": { "type": "string" },
                "recommendation": { "type": "string" }
              },
              "required": ["severity", "category", "description", "affected_section", "recommendation"],
              "additionalProperties": false
            }
          },
          "approved_claims": { "type": "array", "items": { "type": "string" } },
          "requires_human_check": { "type": "array", "items": { "type": "string" } },
          "prohibited_claims": { "type": "array", "items": { "type": "string" } },
          "pre_publish_checklist": { "type": "array", "items": { "type": "string" } },
          "final_recommendation": { "type": "string" }
        },
        "required": ["overall_status", "issues", "approved_claims", "requires_human_check", "prohibited_claims", "pre_publish_checklist", "final_recommendation"],
        "additionalProperties": false
      }
    },
    "required": ["qa_report"],
    "additionalProperties": false
  }
}
```

## A14A CustomerSuccessManagerAgent schema

응답 포맷: `json_schema`

조기 종료 경로에서 사용자에게 보여줄 안내를 Markdown으로 직접 만들지 않고, A14 ProposalEditorAgent가 최종 Markdown으로 편집할 수 있는 구조화 안내 데이터만 출력한다.

```json
{
  "name": "customer_success_manager",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "status": {
        "type": "string",
        "enum": ["needs_request_revision"]
      },
      "reason_code": {
        "type": "string",
        "enum": [
          "empty_request",
          "product_count_exceeds_limit",
          "unsupported_scope",
          "geo_unresolved",
          "unknown"
        ]
      },
      "title": { "type": "string" },
      "message": { "type": "string" },
      "examples": {
        "type": "array",
        "maxItems": 3,
        "items": { "type": "string" }
      },
      "region_candidates": {
        "type": "array",
        "maxItems": 5,
        "items": { "type": "string" }
      },
      "next_action": { "type": "string" }
    },
    "required": ["status", "reason_code", "title", "message", "examples", "region_candidates", "next_action"],
    "additionalProperties": false
  }
}
```

A14는 `${customer_success_manager.last_output.status} == "needs_request_revision"`이면 이 JSON을 Markdown 안내로 변환한다.
이때 `reason_code`, status, schema명, Agent명은 출력하지 않는다.
`examples`는 `## 다시 입력해볼 예시`, `region_candidates`는 `## 후보 지역`으로 보여준다.
조기 종료 응답에는 포스터 안내를 붙이지 않는다.
`unsupported_scope`에서는 A14A title을 “지원 범위 밖의 요청입니다” 또는 “현재 지원하지 않는 요청입니다”처럼 작성한다.
`unsupported_scope`에서 “요청하신 내용을 이해하기 어렵습니다”라는 제목은 사용하지 않는다.
PreflightValidationAgent의 `reason_code`가 `unsupported_scope`, `product_count_exceeds_limit`, `empty_request` 중 하나이면 A14A의 `reason_code`도 같은 값을 유지한다.

## A15 PosterBriefAgent schema

응답 포맷: `json_schema`

아래 schema를 사용한다.

```json
{
  "name": "poster_brief",
  "schema": {
    "type": "object",
    "properties": {
      "status": {
        "type": "string",
        "enum": ["ready", "needs_source_product", "needs_product_selection", "blocked"]
      },
      "user_message": { "type": "string" },
      "selected_product_number": { "type": "integer" },
      "selected_product_name": { "type": "string" },
      "style_preset": {
        "type": "string",
        "enum": ["editorial_travel", "night_city", "minimal_event"]
      },
      "selected_sections": {
        "type": "array",
        "items": { "type": "string" }
      },
      "poster_content": {
        "type": "object",
        "properties": {
          "headline": { "type": "string" },
          "subheadline": { "type": "string" },
          "target": { "type": "string" },
          "places": {
            "type": "array",
            "items": { "type": "string" }
          },
          "itinerary": {
            "type": "array",
            "items": { "type": "string" }
          },
          "sales_points": {
            "type": "array",
            "items": { "type": "string" }
          },
          "promo_copy": { "type": "string" },
          "sns_copy": { "type": "string" },
          "hashtags": {
            "type": "array",
            "items": { "type": "string" }
          },
          "faq": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "question": { "type": "string" },
                "answer": { "type": "string" }
              },
              "required": ["question", "answer"],
              "additionalProperties": false
            }
          },
          "must_check": {
            "type": "array",
            "items": { "type": "string" }
          }
        },
        "required": ["headline", "subheadline", "target", "places", "itinerary", "sales_points", "promo_copy", "sns_copy", "hashtags", "faq", "must_check"],
        "additionalProperties": false
      },
      "input_image_urls": {
        "type": "array",
        "items": { "type": "string" },
        "maxItems": 3
      },
      "reference_image_note": { "type": "string" },
      "visual_direction": { "type": "string" },
      "source_summary": { "type": "string" },
      "warnings": {
        "type": "array",
        "items": { "type": "string" }
      }
    },
    "required": ["status", "user_message", "selected_product_number", "selected_product_name", "style_preset", "selected_sections", "poster_content", "input_image_urls", "reference_image_note", "visual_direction", "source_summary", "warnings"],
    "additionalProperties": false
  }
}
```

## A16 PosterPromptBuilderAgent schema

응답 포맷: `json_schema`

아래 schema를 사용한다.
`quality`는 Ennoia에 걸려 있는 기본 타임아웃을 고려해 `"low"`만 허용한다.

```json
{
  "name": "poster_prompt",
  "schema": {
    "type": "object",
    "properties": {
      "status": {
        "type": "string",
        "enum": ["ready", "needs_source_product", "needs_product_selection", "blocked"]
      },
      "user_message": { "type": "string" },
      "prompt": { "type": "string" },
      "visible_text": {
        "type": "array",
        "items": { "type": "string" },
        "maxItems": 7
      },
      "constraints": {
        "type": "array",
        "items": { "type": "string" }
      },
      "input_image_urls": {
        "type": "array",
        "items": { "type": "string" },
        "maxItems": 3
      },
      "size": { "type": "string" },
      "quality": {
        "type": "string",
        "enum": ["low"]
      },
      "style_preset": {
        "type": "string",
        "enum": ["editorial_travel", "night_city", "minimal_event"]
      },
      "included_sections": {
        "type": "array",
        "items": { "type": "string" }
      },
      "source_summary": {
        "type": "object",
        "properties": {
          "selected_product_number": { "type": "integer" },
          "selected_product_name": { "type": "string" },
          "input_image_count": { "type": "integer" },
          "visible_text_count": { "type": "integer" },
          "constraint_count": { "type": "integer" },
          "specific_place_hints": {
            "type": "array",
            "items": { "type": "string" }
          }
        },
        "required": ["selected_product_number", "selected_product_name", "input_image_count", "visible_text_count", "constraint_count", "specific_place_hints"],
        "additionalProperties": false
      },
      "warnings": {
        "type": "array",
        "items": { "type": "string" }
      }
    },
    "required": ["status", "user_message", "prompt", "visible_text", "constraints", "input_image_urls", "size", "quality", "style_preset", "included_sections", "source_summary", "warnings"],
    "additionalProperties": false
  }
}
```

A17 PosterImageGeneratorAgent는 text 응답 Agent다.
`${poster_prompt.last_output.status} == "ready"`일 때만 이미지 생성 API 커넥터를 호출하고, API 응답의 `image_url`을 HTML `img` 태그와 링크 버튼으로 출력한다.

## State 기준

아래 state는 캔버스에 만들지 않는다.

| state | 기준 |
|---|---|
| `keyword_candidates_output` | A05B가 keyword/festival/stay를 `supplemental_candidates`로 통합 출력 |
| `optional_candidates_output` | A05C를 만들지 않음 |
| `merged_candidates_output` | A05D가 병합/중복 제거와 shortlist 선정을 한 번에 수행 |
| `preflight_output`, `geo_output`, `search_plan_output`, `core_candidates_output`, `baseline_output`, `gap_output` | json_schema Agent 출력은 `${schema_name.last_output}`으로 직접 참조 |
| `capability_routing_output`, `detail_enrichment_output`, `visual_enrichment_output`, `route_signal_enrichment_output`, `theme_enrichment_output` | 보강 lane 결과는 `${schema_name.last_output}`으로 직접 참조 |
| `evidence_output`, `research_output`, `product_output`, `brand_marketing_output`, `growth_marketing_output` | 최종 A14와 포스터 branch는 각 Agent의 `${schema_name.last_output}`을 직접 참조 |
| `final_markdown` | A14 출력은 포스터 branch 재사용을 위해 `proposal_output`으로 저장. 별도 `final_markdown` 이름은 만들지 않음 |

아래 state만 캔버스에 유지한다.

| state | 기준 |
|---|---|
| `enrichment_output` | A08 EnrichmentResultMergeAgent `last_message` 저장용. Agent 프롬프트 입력에는 `${enrichment_result_merge.last_output}` 사용 |
| `qa_output` | A13 QAComplianceManagerAgent `last_message` 저장용. Agent 프롬프트 입력에는 `${qa_compliance_manager.last_output}` 사용 |
| `customer_message_output` | A14A CustomerSuccessManagerAgent `last_message` 저장용. Agent 프롬프트 입력에는 `${customer_success_manager.last_output}` 사용 |
| `proposal_output` | A14 최종 추천 Markdown을 저장해 포스터 branch에서 상품 번호와 사용자-facing 문구 확인 |
| `poster_output` | A17 최종 AI 포스터 생성 Markdown 저장용 |
| `product_planner_proposal_output` | A21 최종 판매용 상품 기획서 Markdown 저장용 |
| `operations_manager_proposal_output` | A24 최종 운영 체크리스트 Markdown 저장용 |
| `marketing_strategist_proposal_output` | A27 최종 마케팅 패키지 Markdown 저장용 |

NO_ENRICHMENT_NEEDED 경로에서는 `${enrichment_result_merge.last_output}`이 없거나 빈 값이어도 정상 경로로 취급한다.
A14는 내부 리포트가 아니라 사용자가 요청한 여행 상품 추천 답변을 작성한다.
A14는 `${customer_success_manager.last_output.status} == "needs_request_revision"`이면 A14A의 구조화 안내 데이터를 Markdown으로 변환해 최종 응답으로 출력한다.
상품별 이미지 URL이 있으면 Markdown 본문 안에 HTML `img` 태그를 넣어 앱에서 이미지가 렌더링되도록 한다.
상품별 이미지 `img`는 같은 원본 이미지 URL의 HTML `a` 태그로 감싸서 클릭 시 새 탭에서 원본 이미지를 볼 수 있게 한다.
상품별 공식 홈페이지, 예약 페이지, 안내 페이지 등 실제 URL이 있으면 Markdown 본문 안에 HTML `a` 태그 버튼을 넣어 클릭할 수 있게 한다. 실제 URL이 없으면 링크를 추측해 만들지 않는다.
A14는 별도 `links` 배열을 기대하지 않고, `fields_added`의 `detail_common=homepage:`, `detail_intro=eventhomepage:`, `detail_intro=bookingplace:`, `detail_intro=reservationurl:`, `detail_intro=reservationlodging:`, `detail_intro=reservation:`, `detail_intro=reservationfood:` 및 `field=홈페이지; value=...; source=detailCommon2` 같은 근거 문자열에서 URL을 추출한다.
테마 계열 상품은 `theme_candidates[].raw_reference`의 `homepage:`, `eventhomepage:`, `reservationurl:`, `audioUrl=` 문자열에서도 URL을 추출한다.
A14는 사용자가 요청한 특별 테마와 연결되는 `theme_candidates`가 있는 상품에만 `### 오디오 해설 활용 정보` 같은 테마별 상세 섹션을 추가한다. 연결 데이터가 없는 상품에는 해당 섹션과 데이터 부재 설명을 모두 생략한다.
`www.`로 시작하는 URL은 버튼 href 생성 시 `https://`를 붙이고, HTML anchor 값은 `href`만 사용한다. 설명 문구와 URL이 섞인 값은 문자열 안의 실제 URL만 추출한다.
홈페이지나 관련 URL이 없는 상품도 최종 추천에서 제외하지 않는다. URL이 없으면 해당 상품의 “관련 링크” 섹션만 생략한다.
A14는 사용자가 요청한 상품 개수, 즉 `normalized_request.product_count`를 유지한다. ProductManagerAgent 출력이 부족하면 확인된 후보와 보강 정보를 사용해 보수적으로 부족분을 채우고, 데이터 공백은 확인 필요 사항으로 표시한다.
A14 성공 응답은 단순 코스 추천이 아니라 여행 상품 제안서로 작성한다. 상품별 세일즈 포인트, FAQ, SNS 문구, 해시태그, 판매/홍보 실험, 게시 전 확인사항을 포함한다.
A14 성공 응답 마지막에는 `AI 포스터 만들기` 안내와 예시 입력을 붙인다.
A15는 홈페이지 URL이나 이미지 URL이 없다는 이유로 상품을 제외하지 않는다.
A17은 이미지 생성 API 응답에 실제 `image_url`이 있을 때만 이미지 HTML을 만든다.
