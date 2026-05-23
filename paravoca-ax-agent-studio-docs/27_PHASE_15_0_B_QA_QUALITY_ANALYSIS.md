# Phase 15.0-B QA Quality Analysis

Scope: this section analyzes only the nine Phase 15.0 target runs, excluding revision runs and poster data. It uses the 15.0-A inventory plus `backend/data/paravoca.db` workflow output data.

Central question: is QA evaluating only the user-specified `avoid` items?

Initial answer: no. Across the runs with available QA reports, most QA issues are not directly matched to the user-provided `avoid` list. QA currently mixes evidence wiring, missing detail, operational gaps, marketing polish, and claim risk in `general` issues.

Classification note: `matched_avoid` is intentionally conservative. Generic words such as “확인”, “필요”, “표현”, and “단정” are not treated as matches by themselves.

### Run-level QA Issue Table

| run_id | avoid | product_id | severity | type | message | suggested_fix | category | matched_avoid | cites_problem_phrase | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| run_0f3679c894d84215 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_001 | medium | general | 상품에 연결할 근거 id가 부족해 서버가 사용 가능한 근거를 보정했습니다. | 상품에 연결할 근거 id가 부족하여 서버에서 사용 가능한 근거를 보정했습니다. 관련 근거 id를 확인하여 상품에 연결해주세요. | 모호한 issue | - | no | problem |
| run_0f3679c894d84215 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_001 | medium | general | 상세 정보 부족으로 상품의 매력도를 높이기 어렵습니다. | 상품의 매력도를 높이기 위해 상세 정보를 보강해주세요. | 품질 평가 issue | - | no | problem |
| run_0f3679c894d84215 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_001 | medium | general | 상세 설명 근거가 부족해 운영자 확인이 필요합니다. | 상세 설명에 대한 근거를 보강하고 운영자 확인을 진행해주세요. | 품질 평가 issue | - | no | problem |
| run_0f3679c894d84215 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_002 | medium | general | 상품에 연결할 근거 id가 부족해 서버가 사용 가능한 근거를 보정했습니다. | 상품에 연결할 근거 id가 부족하여 서버에서 사용 가능한 근거를 보정했습니다. 관련 근거 id를 확인하여 상품에 연결해주세요. | 모호한 issue | - | no | problem |
| run_0f3679c894d84215 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_002 | medium | general | 상세 정보 부족으로 상품의 매력도를 높이기 어렵습니다. | 상품의 매력도를 높이기 위해 상세 정보를 보강해주세요. | 품질 평가 issue | - | no | problem |
| run_0f3679c894d84215 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_002 | medium | general | 상세 설명 근거가 부족해 운영자 확인이 필요합니다. | 상세 설명에 대한 근거를 보강하고 운영자 확인을 진행해주세요. | 품질 평가 issue | - | no | problem |
| run_0f3679c894d84215 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_003 | medium | general | 상세 정보 부족으로 상품의 매력도를 높이기 어렵습니다. | 상품의 매력도를 높이기 위해 상세 정보를 보강해주세요. | 품질 평가 issue | - | no | problem |
| run_0f3679c894d84215 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_003 | medium | general | 상세 설명 근거가 부족해 운영자 확인이 필요합니다. | 상세 설명에 대한 근거를 보강하고 운영자 확인을 진행해주세요. | 품질 평가 issue | - | no | problem |
| run_331348e02b064d28 | 수요/혼잡 단정 금지, 가격 단정 표현 | product_001 | medium | general | 상품에 연결할 근거 ID가 부족하여 서버에서 제외된 ID가 있습니다. 이는 상품 정보의 완전성을 저해할 수 있습니다. | 상품에 연결할 수 있는 근거 ID를 추가하거나, 현재 근거 ID를 보정해야 합니다. | 모호한 issue | - | no | problem |
| run_331348e02b064d28 | 수요/혼잡 단정 금지, 가격 단정 표현 | product_001 | medium | general | 요트 투어의 경험과 안전 관련 정보가 부족하여 상품 신뢰도를 확보하기 어렵습니다. | 요트 투어의 경험과 안전 관련 정보를 상세하게 제공해야 합니다. | 모호한 issue | - | no | problem |
| run_331348e02b064d28 | 수요/혼잡 단정 금지, 가격 단정 표현 | product_001 | medium | general | 운영 시간 정보가 부족하여 관광객의 일정 계획에 혼란을 줄 수 있으며, 상품의 신뢰도를 저하시킬 수 있습니다. | 정확한 운영 시간을 명시해야 합니다. | 과잉 issue | - | no | problem |
| run_331348e02b064d28 | 수요/혼잡 단정 금지, 가격 단정 표현 | product_001 | medium | general | 아쿠아리움의 전시 내용과 특별 프로그램 등 상세 정보가 부족하여 상품 매력도를 높이기 어렵습니다. | 아쿠아리움의 전시 내용과 특별 프로그램 등 상세 정보를 제공해야 합니다. | 품질 평가 issue | - | no | problem |
| run_331348e02b064d28 | 수요/혼잡 단정 금지, 가격 단정 표현 | product_001 | medium | general | 상세 설명 근거가 부족하여 운영자 확인이 필요합니다. | 상세 설명에 대한 근거 자료를 보강해야 합니다. | 품질 평가 issue | - | no | problem |
| run_331348e02b064d28 | 수요/혼잡 단정 금지, 가격 단정 표현 | product_002 | medium | general | 상세 운영 시간 및 예약 정보가 부족하여 상품 매력도를 제고하기 어렵습니다. | 상세 운영 시간 및 예약 정보를 제공해야 합니다. | 품질 평가 issue | - | no | problem |
| run_331348e02b064d28 | 수요/혼잡 단정 금지, 가격 단정 표현 | product_002 | medium | general | 상품에 연결할 근거 ID가 부족하여 서버에서 제외된 ID가 있습니다. 이는 상품 정보의 완전성을 저해할 수 있습니다. | 상품에 연결할 수 있는 근거 ID를 추가하거나, 현재 근거 ID를 보정해야 합니다. | 모호한 issue | - | no | problem |
| run_331348e02b064d28 | 수요/혼잡 단정 금지, 가격 단정 표현 | product_002 | medium | general | 요트 투어의 경험과 안전 관련 정보가 부족하여 상품 신뢰도를 확보하기 어렵습니다. | 요트 투어의 경험과 안전 관련 정보를 상세하게 제공해야 합니다. | 모호한 issue | - | no | problem |
| run_331348e02b064d28 | 수요/혼잡 단정 금지, 가격 단정 표현 | product_002 | medium | general | 운영 시간 정보가 부족하여 관광객의 일정 계획에 혼란을 줄 수 있으며, 상품의 신뢰도를 저하시킬 수 있습니다. | 정확한 운영 시간을 명시해야 합니다. | 과잉 issue | - | no | problem |
| run_331348e02b064d28 | 수요/혼잡 단정 금지, 가격 단정 표현 | product_002 | medium | general | 아쿠아리움의 전시 내용과 특별 프로그램 등 상세 정보가 부족하여 상품 매력도를 높이기 어렵습니다. | 아쿠아리움의 전시 내용과 특별 프로그램 등 상세 정보를 제공해야 합니다. | 품질 평가 issue | - | no | problem |
| run_331348e02b064d28 | 수요/혼잡 단정 금지, 가격 단정 표현 | product_002 | medium | general | 상세 설명 근거가 부족하여 운영자 확인이 필요합니다. | 상세 설명에 대한 근거 자료를 보강해야 합니다. | 품질 평가 issue | - | no | problem |
| run_331348e02b064d28 | 수요/혼잡 단정 금지, 가격 단정 표현 | product_003 | medium | general | 상세 정보 부족으로 인한 코스 계획 어려움 및 체력 소모 고려 필요성에 대한 안내가 필요합니다. | 상세 정보 부족으로 인한 코스 계획 어려움과 중급 난이도로 인한 체력 소모 고려 필요성을 명확하게 안내해야 합니다. | 품질 평가 issue | - | no | problem |
| run_331348e02b064d28 | 수요/혼잡 단정 금지, 가격 단정 표현 | product_003 | medium | general | 상품에 연결할 근거 ID가 부족하여 서버에서 제외된 ID가 있습니다. 이는 상품 정보의 완전성을 저해할 수 있습니다. | 상품에 연결할 수 있는 근거 ID를 추가하거나, 현재 근거 ID를 보정해야 합니다. | 모호한 issue | - | no | problem |
| run_331348e02b064d28 | 수요/혼잡 단정 금지, 가격 단정 표현 | product_003 | medium | general | 요트 투어의 경험과 안전 관련 정보가 부족하여 상품 신뢰도를 확보하기 어렵습니다. | 요트 투어의 경험과 안전 관련 정보를 상세하게 제공해야 합니다. | 모호한 issue | - | no | problem |
| run_331348e02b064d28 | 수요/혼잡 단정 금지, 가격 단정 표현 | product_003 | medium | general | 운영 시간 정보가 부족하여 관광객의 일정 계획에 혼란을 줄 수 있으며, 상품의 신뢰도를 저하시킬 수 있습니다. | 정확한 운영 시간을 명시해야 합니다. | 과잉 issue | - | no | problem |
| run_331348e02b064d28 | 수요/혼잡 단정 금지, 가격 단정 표현 | product_003 | medium | general | 아쿠아리움의 전시 내용과 특별 프로그램 등 상세 정보가 부족하여 상품 매력도를 높이기 어렵습니다. | 아쿠아리움의 전시 내용과 특별 프로그램 등 상세 정보를 제공해야 합니다. | 품질 평가 issue | - | no | problem |
| run_331348e02b064d28 | 수요/혼잡 단정 금지, 가격 단정 표현 | product_003 | medium | general | 상세 설명 근거가 부족하여 운영자 확인이 필요합니다. | 상세 설명에 대한 근거 자료를 보강해야 합니다. | 품질 평가 issue | - | no | problem |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_001 | medium | general | 상품 설명에 '환상적인 빛의 향연'과 같은 홍보성 문구가 포함되어 있으나, 이에 대한 구체적인 근거가 부족합니다. 또한, '잊지 못할 밤 산책'이라는 표현은 고객에게 과도한 기대를 줄 수 있습니다. | 홍보성 문구를 구체적인 정보나 근거에 기반한 설명으로 수정하고, 과장된 표현을 완화하세요. | 정상 issue | - | yes | normal |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_001 | medium | general | FAQ 답변에 '정확한 조명 점등 시간 및 운영 여부는 방문 전 반드시 확인이 필요합니다.'라고 명시되어 있으나, 이는 상품 설명에서 이미 언급된 내용으로 중복됩니다. 또한, '반드시'라는 단정적인 표현은 고객에게 부담을 줄 수 있습니다. | 중복되는 정보는 제거하고, '반드시'와 같은 단정적인 표현을 완화하여 고객에게 명확하고 간결한 정보를 제공하세요. | 품질 평가 issue | - | yes | problem |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_001 | medium | general | 상품 설명에 '빛의 꽃길, 별빛길, 바다물결 빛길, 녹색빛길'과 같은 테마 구간이 언급되었으나, 이에 대한 구체적인 설명이나 근거가 부족합니다. | 각 테마 구간에 대한 간략한 설명이나 특징을 추가하여 고객의 이해를 돕고 상품의 매력도를 높이세요. | 품질 평가 issue | - | yes | problem |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_001 | medium | general | 상품 설명에 '외국인 관광객, 커플, 사진 애호가에게 추천하는 이곳에서 잊지 못할 밤 산책과 인생샷을 남겨보세요.'라는 문구가 포함되어 있으나, '인생샷'이라는 표현은 고객에게 과도한 기대를 줄 수 있으며, 이에 대한 구체적인 근거가 부족합니다. | '인생샷'과 같은 과장된 표현을 완화하고, 사진 촬영에 적합한 장소임을 명확히 설명하세요. | 정상 issue | - | yes | normal |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_001 | medium | general | SNS 게시물에 '인생샷 명소'라는 표현이 포함되어 있어 고객에게 과도한 기대를 줄 수 있습니다. | '인생샷 명소'와 같은 과장된 표현을 완화하고, 사진 촬영에 좋은 장소임을 명확히 전달하세요. | 정상 issue | - | yes | normal |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_001 | medium | general | 검색 키워드에 '부산 산책로'가 포함되어 있으나, 상품의 핵심 가치인 '별빛 야경'과 직접적인 연관성이 낮습니다. | 상품의 특징을 더 잘 나타내는 키워드로 교체하거나, '부산 야경 산책로'와 같이 구체적인 키워드를 추가하세요. | 품질 평가 issue | - | yes | problem |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_001 | medium | general | 검색 키워드에 '별빛 산책'이 포함되어 있으나, 상품명과 중복됩니다. | 상품명과 중복되는 키워드는 제거하거나, 더 구체적인 관련 키워드로 대체하세요. | 품질 평가 issue | - | yes | problem |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_001 | medium | general | 검색 키워드에 '야간 조명'이 포함되어 있으나, 상품의 핵심 가치인 '별빛 야경'과 직접적인 연관성이 낮습니다. | 상품의 특징을 더 잘 나타내는 키워드로 교체하거나, '부산 야간 조명'과 같이 구체적인 키워드를 추가하세요. | 품질 평가 issue | - | yes | problem |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_001 | medium | general | 검색 키워드에 '인생샷 스팟'이 포함되어 있으나, '인생샷'이라는 표현은 고객에게 과도한 기대를 줄 수 있습니다. | '인생샷 스팟'과 같은 과장된 표현을 완화하고, 사진 촬영에 좋은 장소임을 명확히 전달하세요. | 정상 issue | - | yes | normal |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_001 | medium | general | 근거 문서에 기반한 정보 제공을 명시하고 있으나, '운영 시간, 요금, 상세 프로그램 등 일부 정보는 현장 확인이 필요할 수 있습니다.'라는 문구는 고객에게 불확실성을 전달합니다. 또한, '특히 야간 이용 시 안전에 유의하시기 바랍니다.'라는 문구는 상품 설명과 FAQ에서 이미 언급된 내용으로 중복됩니다. | 불확실한 정보에 대한 안내를 명확하고 간결하게 통합하고, 중복되는 내용은 제거하여 고객에게 명확한 정보를 제공하세요. | 정상 issue | 가격 단정 표현 | yes | normal |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_002 | medium | general | 상품 설명에 '도심 속 여유로운 휴식, 다양한 야외 문화 행사 참여, 역사적 의미를 되새기는 공간'이라는 핵심 가치가 언급되었으나, 이에 대한 구체적인 설명이나 근거가 부족합니다. | 각 핵심 가치에 대한 간략한 설명이나 예시를 추가하여 고객의 이해를 돕고 상품의 매력도를 높이세요. | 품질 평가 issue | - | yes | problem |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_002 | medium | general | 상품 설명에 '넓은 공간을 활용한 모임, 야외 공연, 전시 등 다채로운 활동을 경험하세요.'라고 언급되었으나, 구체적인 행사 정보나 프로그램에 대한 근거가 부족합니다. | 현재 진행 중이거나 예정된 주요 행사 또는 프로그램에 대한 간략한 정보를 추가하여 고객의 흥미를 유발하세요. | 모호한 issue | - | yes | needs_followup |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_002 | medium | general | FAQ 답변에 '행사 일정은 사전 확인이 필수적입니다. 송상현광장 홈페이지에서 자세한 정보를 확인하실 수 있습니다.'라고 명시되어 있으나, 이는 상품 설명에서 이미 언급된 내용으로 중복됩니다. | 중복되는 정보는 제거하고, 고객에게 필요한 정보를 간결하게 제공하세요. | 품질 평가 issue | - | yes | problem |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_002 | medium | general | FAQ 답변에 '주차 공간이 협소할 수 있으므로, 대중교통 이용을 권장합니다.'라고 명시되어 있으나, 이는 상품 설명에서도 언급된 내용으로 중복됩니다. | 중복되는 정보는 제거하고, 고객에게 필요한 정보를 간결하게 제공하세요. | 품질 평가 issue | - | yes | problem |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_002 | medium | general | FAQ 답변에 '야간 조명 및 편의시설에 대한 상세 정보는 추가 확인이 필요합니다.'라고 명시되어 있으나, 이는 상품 설명에서 이미 언급된 내용으로 중복됩니다. | 중복되는 정보는 제거하고, 고객에게 필요한 정보를 간결하게 제공하세요. | 품질 평가 issue | - | yes | problem |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_002 | medium | general | 근거 문서에 기반한 정보 제공을 명시하고 있으나, '행사 일정, 운영 시간, 요금 등 일부 정보는 현장 확인이 필요할 수 있습니다.'라는 문구는 고객에게 불확실성을 전달합니다. 또한, '주차 공간이 협소하므로 대중교통 이용을 권장합니다.'라는 문구는 상품 설명과 FAQ에서 이미 언급된 내용으로 중복됩니다. | 불확실한 정보에 대한 안내를 명확하고 간결하게 통합하고, 중복되는 내용은 제거하여 고객에게 명확한 정보를 제공하세요. | 정상 issue | 가격 단정 표현 | yes | normal |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_003 | medium | general | 상품 설명에 '청정한 자연 속 힐링, 부산 국가지질공원의 지질학적 가치 체험, 정상에서의 탁 트인 조망'이라는 핵심 가치가 언급되었으나, 이에 대한 구체적인 설명이나 근거가 부족합니다. | 각 핵심 가치에 대한 간략한 설명이나 예시를 추가하여 고객의 이해를 돕고 상품의 매력도를 높이세요. | 품질 평가 issue | - | yes | problem |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_003 | medium | general | 상품 설명에 '부산 국가지질공원으로 지정된 백양산의 독특한 지질학적 특징을 탐험하며 청정한 자연 속에서 힐링하는 시간을 가져보세요.'라고 언급되었으나, 구체적인 지질학적 특징이나 힐링 프로그램에 대한 근거가 부족합니다. | 백양산의 주요 지질학적 특징이나 자연 속에서 힐링할 수 있는 요소에 대한 간략한 정보를 추가하세요. | 모호한 issue | - | yes | needs_followup |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_003 | medium | general | 상품 설명에 '외국인, 자연 애호가, 트레킹 애호가에게 추천하는 백양산 트레킹으로 정상에서의 탁 트인 조망과 함께 성취감을 느껴보세요.'라는 문구가 포함되어 있으나, '성취감'이라는 표현은 고객에게 과도한 기대를 줄 수 있습니다. | '성취감'과 같은 추상적인 표현을 완화하고, 정상에서의 조망이 뛰어나다는 점을 강조하세요. | 정상 issue | - | yes | normal |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_003 | medium | general | FAQ 답변에 '백양산의 정확한 등산 코스 및 난이도 정보는 추가 확인이 필요합니다.'라고 명시되어 있으나, 이는 상품 설명에서 이미 언급된 내용으로 중복됩니다. | 중복되는 정보는 제거하고, 고객에게 필요한 정보를 간결하게 제공하세요. | 품질 평가 issue | - | yes | problem |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_003 | medium | general | FAQ 답변에 '이미지 자료 확보가 상품의 매력도를 높이는 데 중요합니다. 관련 이미지 자료는 별도 확인이 필요합니다.'라고 명시되어 있으나, 이는 상품 설명에서 이미 언급된 내용으로 중복됩니다. | 중복되는 정보는 제거하고, 고객에게 필요한 정보를 간결하게 제공하세요. | 정상 issue | 이미지 사용권 확인 필요 | yes | normal |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_003 | medium | general | 근거 문서에 기반한 정보 제공을 명시하고 있으나, '추천 등산 코스, 난이도, 안전 정보 등 일부 정보는 현장 확인이 필요합니다.'라는 문구는 고객에게 불확실성을 전달합니다. 또한, '이미지 자료 확보가 상품 매력도 향상에 중요합니다.'라는 문구는 상품 설명과 FAQ에서 이미 언급된 내용으로 중복됩니다. | 불확실한 정보에 대한 안내를 명확하고 간결하게 통합하고, 중복되는 내용은 제거하여 고객에게 명확한 정보를 제공하세요. | 정상 issue | 이미지 사용권 확인 필요 | yes | normal |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_001 | medium | general | 상품에 연결된 근거 문서 ID 중 'doc:tourapi:content:2760809', 'doc:tourapi:content:3112467'는 해당 상품의 내용과 직접적인 관련성이 낮습니다. 또한, 'doc:tourapi:content:126119'만으로는 상품의 모든 내용을 뒷받침하기에 부족합니다. | 상품 내용과 직접적인 관련성이 높은 근거 문서 ID를 우선적으로 사용하고, 부족한 정보는 관련성이 높은 다른 근거 문서를 추가하여 보강하세요. | 모호한 issue | - | yes | needs_followup |
| run_1241212633404670 | 이미지 사용권 확인 필요, 가격 단정 표현 | product_003 | medium | general | 상품에 연결된 근거 문서 ID 중 'doc:tourapi:content:2760809', 'doc:tourapi:content:3112467'는 해당 상품의 내용과 직접적인 관련성이 낮습니다. 또한, 'doc:tourapi:content:126119'만으로는 상품의 모든 내용을 뒷받침하기에 부족합니다. | 상품 내용과 직접적인 관련성이 높은 근거 문서 ID를 우선적으로 사용하고, 부족한 정보는 관련성이 높은 다른 근거 문서를 추가하여 보강하세요. | 모호한 issue | - | yes | needs_followup |
| run_01e6aa86a21f499f | 수요/혼잡 단정 금지, 가격 단정 표현 | product_001 | medium | general | 상품 제목에 근거 문서에 명시되지 않은 '마린시티와 광안대교 야경 감상'이라는 내용이 포함되어 있습니다. | 상품 제목을 근거 문서의 내용에 맞게 수정하거나, 해당 내용에 대한 근거를 추가해야 합니다. | 정상 issue | - | yes | normal |
| run_01e6aa86a21f499f | 수요/혼잡 단정 금지, 가격 단정 표현 | product_001 | medium | general | 상품 설명에 '혼잡한 관광지를 피해 여유롭게 부산의 밤을 만끽할 수 있습니다.'라는 문구가 포함되어 있으나, 이는 근거 문서에 명시되지 않은 내용입니다. | 상품 설명 문구를 근거 문서의 내용에 맞게 수정하거나, 해당 내용에 대한 근거를 추가해야 합니다. | 정상 issue | 수요/혼잡 단정 금지 | yes | normal |
| run_01e6aa86a21f499f | 수요/혼잡 단정 금지, 가격 단정 표현 | product_001 | medium | general | 상품 설명에 '아름다운 해안선을 따라 펼쳐지는 황홀한 야경을 감상하며 잊지 못할 추억을 만들어 보세요.'라는 문구가 포함되어 있으나, 이는 근거 문서에 명시되지 않은 내용입니다. | 상품 설명 문구를 근거 문서의 내용에 맞게 수정하거나, 해당 내용에 대한 근거를 추가해야 합니다. | 정상 issue | - | yes | normal |
| run_01e6aa86a21f499f | 수요/혼잡 단정 금지, 가격 단정 표현 | product_001 | medium | general | 상품 설명에 '전문적인 서비스를 통해 안전하고 편안한 요트 투어를 제공합니다.'라는 문구가 포함되어 있으나, 이는 근거 문서에 명시되지 않은 내용입니다. | 상품 설명 문구를 근거 문서의 내용에 맞게 수정하거나, 해당 내용에 대한 근거를 추가해야 합니다. | 정상 issue | - | yes | normal |
| run_01e6aa86a21f499f | 수요/혼잡 단정 금지, 가격 단정 표현 | product_001 | medium | general | 근거 문서 기반 정보 안내에 '일부 정보(운영 시간, 상세 프로그램, 요금 등)는 확인이 필요합니다.'라고 명시되어 있으나, 이는 상품의 신뢰도를 낮출 수 있습니다. | 운영 시간, 상세 프로그램, 요금 등 확인이 필요한 정보에 대한 구체적인 안내를 추가하거나, FAQ 섹션에서 해당 내용을 명확히 안내해야 합니다. | 정상 issue | 가격 단정 표현 | yes | normal |
| run_01e6aa86a21f499f | 수요/혼잡 단정 금지, 가격 단정 표현 | product_002 | medium | general | 상품 제목에 근거 문서에 명시되지 않은 '고흐의 길 산책과 미포항의 여유'라는 내용이 포함되어 있습니다. | 상품 제목을 근거 문서의 내용에 맞게 수정하거나, 해당 내용에 대한 근거를 추가해야 합니다. | 정상 issue | - | yes | normal |
| run_01e6aa86a21f499f | 수요/혼잡 단정 금지, 가격 단정 표현 | product_002 | medium | general | 상품 설명에 '메타세쿼이아길이 아름다운 고흐의 길에서 한적한 산책을 즐기고, 활기찬 미포항에서 여유로운 시간을 보내세요.'라는 문구가 포함되어 있으나, 이는 근거 문서에 명시되지 않은 내용입니다. | 상품 설명 문구를 근거 문서의 내용에 맞게 수정하거나, 해당 내용에 대한 근거를 추가해야 합니다. | 정상 issue | - | yes | normal |
| run_01e6aa86a21f499f | 수요/혼잡 단정 금지, 가격 단정 표현 | product_002 | medium | general | 상품 설명에 '울창한 나무 그늘 아래 산책하며 도심의 번잡함을 잊고 평화로운 휴식을 경험하세요.'라는 문구가 포함되어 있으나, 이는 근거 문서에 명시되지 않은 내용입니다. | 상품 설명 문구를 근거 문서의 내용에 맞게 수정하거나, 해당 내용에 대한 근거를 추가해야 합니다. | 정상 issue | - | yes | normal |
| run_01e6aa86a21f499f | 수요/혼잡 단정 금지, 가격 단정 표현 | product_002 | medium | general | 상품 설명에 '혼잡함을 피해 자연 속에서 여유를 즐기고 싶은 외국인 관광객에게 최적의 코스입니다.'라는 문구가 포함되어 있으나, 이는 근거 문서에 명시되지 않은 내용입니다. | 상품 설명 문구를 근거 문서의 내용에 맞게 수정하거나, 해당 내용에 대한 근거를 추가해야 합니다. | 정상 issue | 수요/혼잡 단정 금지 | yes | normal |
| run_01e6aa86a21f499f | 수요/혼잡 단정 금지, 가격 단정 표현 | product_002 | medium | general | 근거 문서 기반 정보 안내에 '상세 코스 정보, 편의시설 운영 시간, 요금 등은 확인이 필요합니다.'라고 명시되어 있으나, 이는 상품의 신뢰도를 낮출 수 있습니다. | 상세 코스 정보, 편의시설 운영 시간, 요금 등 확인이 필요한 정보에 대한 구체적인 안내를 추가하거나, FAQ 섹션에서 해당 내용을 명확히 안내해야 합니다. | 정상 issue | 가격 단정 표현 | yes | normal |
| run_01e6aa86a21f499f | 수요/혼잡 단정 금지, 가격 단정 표현 | product_003 | medium | general | 상품 제목에 근거 문서에 명시되지 않은 '해운대 해안 트레킹: 부산 갈맷길 2코스 2구간 걷기'라는 내용이 포함되어 있습니다. | 상품 제목을 근거 문서의 내용에 맞게 수정하거나, 해당 내용에 대한 근거를 추가해야 합니다. | 정상 issue | - | yes | normal |
| run_01e6aa86a21f499f | 수요/혼잡 단정 금지, 가격 단정 표현 | product_003 | medium | general | 상품 설명에 '이기대와 오륙도의 아름다운 해안 절경을 감상하며 걷는 힐링 트레킹 코스입니다.'라는 문구가 포함되어 있으나, 이는 근거 문서에 명시되지 않은 내용입니다. | 상품 설명 문구를 근거 문서의 내용에 맞게 수정하거나, 해당 내용에 대한 근거를 추가해야 합니다. | 정상 issue | - | yes | normal |
| run_01e6aa86a21f499f | 수요/혼잡 단정 금지, 가격 단정 표현 | product_003 | medium | general | 상품 설명에 '복잡한 도심을 벗어나 자연 속에서 재충전의 시간을 가질 수 있습니다.'라는 문구가 포함되어 있으나, 이는 근거 문서에 명시되지 않은 내용입니다. | 상품 설명 문구를 근거 문서의 내용에 맞게 수정하거나, 해당 내용에 대한 근거를 추가해야 합니다. | 정상 issue | - | yes | normal |
| run_01e6aa86a21f499f | 수요/혼잡 단정 금지, 가격 단정 표현 | product_003 | medium | general | 상품 설명에 '부산의 아름다운 해안 절경을 만끽하며 걷고 싶은 외국인 관광객에게 이상적인 코스입니다.'라는 문구가 포함되어 있으나, 이는 근거 문서에 명시되지 않은 내용입니다. | 상품 설명 문구를 근거 문서의 내용에 맞게 수정하거나, 해당 내용에 대한 근거를 추가해야 합니다. | 정상 issue | - | yes | normal |
| run_b25b5f6c9ec24e1b | 가격 단정 표현 | daecheongdo-desert-photo-tour-001 | medium | general | 상품 제목에 대한 근거 문서가 부족합니다. | 상품 제목과 관련된 근거 문서를 추가하거나, 상품 제목을 근거 문서 내용에 맞게 수정하세요. | 모호한 issue | - | partial | needs_followup |
| run_b25b5f6c9ec24e1b | 가격 단정 표현 | daecheongdo-desert-photo-tour-001 | medium | general | 상품 상세 설명에 대한 근거 문서가 부족합니다. | 상품 상세 설명에 대한 근거 문서를 추가하거나, 상품 상세 설명을 근거 문서 내용에 맞게 수정하세요. | 모호한 issue | - | no | problem |
| run_b25b5f6c9ec24e1b | 가격 단정 표현 | daecheongdo-beach-fishing-healing-002 | medium | general | 상품 제목에 대한 근거 문서가 부족합니다. | 상품 제목과 관련된 근거 문서를 추가하거나, 상품 제목을 근거 문서 내용에 맞게 수정하세요. | 모호한 issue | - | partial | needs_followup |
| run_b25b5f6c9ec24e1b | 가격 단정 표현 | daecheongdo-beach-fishing-healing-002 | medium | general | 상품 상세 설명에 대한 근거 문서가 부족합니다. | 상품 상세 설명에 대한 근거 문서를 추가하거나, 상품 상세 설명을 근거 문서 내용에 맞게 수정하세요. | 모호한 issue | - | no | problem |
| run_b25b5f6c9ec24e1b | 가격 단정 표현 | daecheongdo-desert-photo-tour-001 | medium | general | 주변 연계 관광지 정보 보강 필요 | 주변 연계 관광지 정보를 근거 문서에서 확인하거나, 관련 정보를 추가하세요. | 품질 평가 issue | - | no | problem |
| run_b25b5f6c9ec24e1b | 가격 단정 표현 | daecheongdo-beach-fishing-healing-002 | medium | general | 주변 연계 관광지 정보 보강 필요 | 주변 연계 관광지 정보를 근거 문서에서 확인하거나, 관련 정보를 추가하세요. | 품질 평가 issue | - | no | problem |
| run_f9182c6a30814cab | 가격 단정 표현 | daecheongdo-desert-photo-tour | medium | general | 상품 제목에 '인생샷 투어'라는 표현이 포함되어 있으나, 인생샷을 보장한다는 근거가 부족합니다. | 상품 제목에서 '인생샷'이라는 단어를 제외하거나, 인생샷 촬영을 보장한다는 명확한 근거를 제시해야 합니다. | 정상 issue | - | yes | normal |
| run_f9182c6a30814cab | 가격 단정 표현 | daecheongdo-desert-photo-tour | medium | general | 상품 상세 설명에 '특별한 추억을 만들어보세요'라는 표현이 포함되어 있으나, 특별한 추억을 보장한다는 근거가 부족합니다. | 해당 문구를 '특별한 추억을 만들 수 있는 기회를 제공합니다'와 같이 가능성을 나타내는 표현으로 수정하거나, 특별한 추억을 만들 수 있는 구체적인 경험 요소를 강조해야 합니다. | 정상 issue | - | yes | normal |
| run_f9182c6a30814cab | 가격 단정 표현 | daecheongdo-desert-photo-tour | medium | general | 상품 상세 설명에 '다른 세상에 온 듯한 착각을 불러일으킵니다'라는 표현이 포함되어 있으나, 이러한 경험을 보장한다는 근거가 부족합니다. | 해당 문구를 '다른 세상에 온 듯한 이국적인 분위기를 느낄 수 있습니다'와 같이 경험의 가능성을 나타내는 표현으로 수정해야 합니다. | 정상 issue | - | yes | normal |
| run_f9182c6a30814cab | 가격 단정 표현 | daecheongdo-desert-photo-tour | medium | general | 상품 상세 설명에 '대청도의 매력에 흠뻑 빠져보세요'라는 표현이 포함되어 있으나, 매력에 대한 구체적인 근거가 부족합니다. | 해당 문구를 '대청도의 매력을 경험할 수 있습니다'와 같이 가능성을 나타내는 표현으로 수정하거나, 대청도의 구체적인 매력 포인트를 추가해야 합니다. | 모호한 issue | - | yes | needs_followup |
| run_f9182c6a30814cab | 가격 단정 표현 | daecheongdo-desert-photo-tour | medium | general | 우천 시 투어 진행 여부에 대한 답변이 '별도 확인이 필요합니다'로 되어 있어, 운영 가능성에 대한 정보가 부족합니다. | 우천 시 운영 여부에 대한 일반적인 정책(예: '기상 상황에 따라 운영 여부가 결정되며, 취소 시 별도 안내됩니다.')을 추가하거나, 운영자 확인이 필요함을 명확히 안내해야 합니다. | 과잉 issue | - | yes | problem |
| run_f9182c6a30814cab | 가격 단정 표현 | daecheongdo-fishing-and-relaxation-tour | medium | general | 상품 제목에 '힐링 낚시 투어'라는 표현이 포함되어 있으나, 힐링과 낚시 경험을 보장한다는 근거가 부족합니다. | 상품 제목에서 '힐링'이라는 단어를 제외하거나, 힐링과 낚시 경험을 제공한다는 명확한 근거를 제시해야 합니다. | 정상 issue | - | yes | normal |
| run_f9182c6a30814cab | 가격 단정 표현 | daecheongdo-fishing-and-relaxation-tour | medium | general | 상품 상세 설명에 '완벽한 휴식을 선사합니다'라는 표현이 포함되어 있으나, 완벽한 휴식을 보장한다는 근거가 부족합니다. | 해당 문구를 '완벽한 휴식을 경험할 수 있는 기회를 제공합니다'와 같이 가능성을 나타내는 표현으로 수정하거나, 휴식을 위한 구체적인 요소(예: 조용한 환경, 아름다운 경관)를 강조해야 합니다. | 정상 issue | - | yes | normal |
| run_f9182c6a30814cab | 가격 단정 표현 | daecheongdo-fishing-and-relaxation-tour | medium | general | 상품 상세 설명에 '진정한 휴식을 선사합니다'라는 표현이 포함되어 있으나, 진정한 휴식을 보장한다는 근거가 부족합니다. | 해당 문구를 '진정한 휴식을 경험할 수 있습니다'와 같이 가능성을 나타내는 표현으로 수정해야 합니다. | 정상 issue | - | yes | normal |
| run_f9182c6a30814cab | 가격 단정 표현 | daecheongdo-fishing-and-relaxation-tour | medium | general | 상품 상세 설명에 '최고의 명소가 될 것입니다'라는 표현이 포함되어 있으나, 최고의 명소임을 보장한다는 근거가 부족합니다. | 해당 문구를 '인기 있는 낚시 명소입니다'와 같이 사실에 기반한 표현으로 수정하거나, 낚시 명소로서의 장점을 구체적으로 설명해야 합니다. | 정상 issue | - | yes | normal |
| run_f9182c6a30814cab | 가격 단정 표현 | daecheongdo-fishing-and-relaxation-tour | medium | general | 우천 시 투어 진행 여부에 대한 답변이 '별도 확인이 필요합니다'로 되어 있어, 운영 가능성에 대한 정보가 부족합니다. | 우천 시 운영 여부에 대한 일반적인 정책(예: '기상 상황에 따라 운영 여부가 결정되며, 취소 시 별도 안내됩니다.')을 추가하거나, 운영자 확인이 필요함을 명확히 안내해야 합니다. | 과잉 issue | - | yes | problem |
| run_87d306e83f1549c3 | 가격 단정 표현 | product_001 | medium | general | 상품 설명에 '축제는 매일 운영됩니다.'라는 근거 없는 주장이 포함되어 있습니다. 제공된 근거 문서에 따르면 축제는 특정 날짜에만 운영됩니다. | 해당 문구를 '축제는 2026년 5월 23일에만 운영됩니다.'로 수정하거나, 운영자 확인이 필요한 정보임을 명시하세요. | 정상 issue | - | yes | normal |
| run_87d306e83f1549c3 | 가격 단정 표현 | product_001 | medium | general | 상품 설명에 '모든 체험 프로그램은 무료로 참여 가능합니다.'라는 근거 없는 주장이 포함되어 있습니다. 제공된 근거 문서에 따르면 일부 프로그램은 유료이거나 사전 예약이 필요할 수 있습니다. | 해당 문구를 '일부 체험 프로그램은 유료이거나 사전 예약이 필요할 수 있습니다. 자세한 내용은 현장에서 확인해 주세요.'로 수정하세요. | 정상 issue | 가격 단정 표현 | yes | normal |
| run_87d306e83f1549c3 | 가격 단정 표현 | product_001 | medium | general | 상품 설명에 상세 정보 부족으로 인해 상품 설명 및 이용 안내 구성에 제약이 발생합니다. | 운영자 확인이 필요한 정보임을 명시하세요. | 품질 평가 issue | - | partial | problem |
| run_87d306e83f1549c3 | 가격 단정 표현 | product_001 | medium | general | 상품 설명에 상세 정보 부족으로 인해 상품 설명, 이용 안내, 테마 연계 등 상품의 완성도를 높이는 데 제약이 있습니다. | 운영자 확인이 필요한 정보임을 명시하세요. | 품질 평가 issue | - | partial | problem |
| run_87d306e83f1549c3 | 가격 단정 표현 | product_001 | medium | general | 상품 설명에 상세 설명 근거가 부족해 운영자 확인이 필요합니다. | 운영자 확인이 필요한 정보임을 명시하세요. | 품질 평가 issue | - | partial | problem |
| run_87d306e83f1549c3 | 가격 단정 표현 | product_002 | medium | general | 상품 설명에 상세 정보 부족으로 인해 상품 설명 및 이용 안내 구성에 제약이 발생합니다. | 운영자 확인이 필요한 정보임을 명시하세요. | 품질 평가 issue | - | partial | problem |
| run_87d306e83f1549c3 | 가격 단정 표현 | product_002 | medium | general | 상품 설명에 상세 정보 부족으로 인해 상품 설명, 이용 안내, 테마 연계 등 상품의 완성도를 높이는 데 제약이 있습니다. | 운영자 확인이 필요한 정보임을 명시하세요. | 품질 평가 issue | - | partial | problem |
| run_87d306e83f1549c3 | 가격 단정 표현 | product_002 | medium | general | 상품 설명에 상세 설명 근거가 부족해 운영자 확인이 필요합니다. | 운영자 확인이 필요한 정보임을 명시하세요. | 품질 평가 issue | - | partial | problem |
| run_87d306e83f1549c3 | 가격 단정 표현 | product_003 | medium | general | 상품 설명에 상세 정보 부족으로 인해 상품 설명 및 이용 안내 구성에 제약이 발생합니다. | 운영자 확인이 필요한 정보임을 명시하세요. | 품질 평가 issue | - | partial | problem |
| run_87d306e83f1549c3 | 가격 단정 표현 | product_003 | medium | general | 상품 설명에 상세 정보 부족으로 인해 상품 설명, 이용 안내, 테마 연계 등 상품의 완성도를 높이는 데 제약이 있습니다. | 운영자 확인이 필요한 정보임을 명시하세요. | 품질 평가 issue | - | partial | problem |
| run_87d306e83f1549c3 | 가격 단정 표현 | product_003 | medium | general | 상품 설명에 상세 설명 근거가 부족해 운영자 확인이 필요합니다. | 운영자 확인이 필요한 정보임을 명시하세요. | 품질 평가 issue | - | partial | problem |
| run_bec1f1b99da44fe5 | 가격 단정 표현 | 1 | medium | general | 덕수궁 돌담길과 정동길의 야간 조명 및 안전 시설 현황에 대한 정보가 부족하여 운영자 확인이 필요합니다. | 야간 산책 시 조명 및 안전 시설에 대한 추가 확인이 필요합니다. | 과잉 issue | - | no | problem |
| run_bec1f1b99da44fe5 | 가격 단정 표현 | 1 | medium | general | 상품에 연결할 근거 ID가 부족하여 서버에서 제외되었으며, 운영 시간 정보 부족은 상품화에 부정적인 영향을 미칩니다. | 상품에 연결할 근거 ID를 보강하고, 운영 시간 정보를 명확히 해야 합니다. | 모호한 issue | - | no | problem |
| run_bec1f1b99da44fe5 | 가격 단정 표현 | 2 | medium | general | 상품에 연결할 근거 ID가 부족하여 서버에서 제외되었으며, 운영 시간 정보 부족은 상품화에 부정적인 영향을 미칩니다. | 상품에 연결할 근거 ID를 보강하고, 운영 시간 정보를 명확히 해야 합니다. | 모호한 issue | - | no | problem |
| run_bec1f1b99da44fe5 | 가격 단정 표현 | 3 | medium | general | 상품에 연결할 근거 ID가 부족하여 서버에서 제외되었으며, 운영 시간 정보 부족은 상품화에 부정적인 영향을 미칩니다. | 상품에 연결할 근거 ID를 보강하고, 운영 시간 정보를 명확히 해야 합니다. | 모호한 issue | - | no | problem |

QA report unavailable:
- `run_ac68dfed2d5345e3 (status=failed, final_output is not an object)`

### Avoid-to-QA Matching Summary

| run_id | avoid items | directly matched QA issues | avoid-unmatched QA issues | context-mismatch issues | QA availability |
| --- | --- | ---: | ---: | ---: | --- |
| `run_0f3679c894d84215` | 이미지 사용권 확인 필요, 가격 단정 표현 | 0 | 8 | 0 | 8 issues |
| `run_331348e02b064d28` | 수요/혼잡 단정 금지, 가격 단정 표현 | 0 | 17 | 0 | 17 issues |
| `run_ac68dfed2d5345e3` | 오디오 지원 단정 표현, 가격 단정 표현 | 0 | 0 | 0 | qa_unavailable |
| `run_1241212633404670` | 이미지 사용권 확인 필요, 가격 단정 표현 | 4 | 20 | 0 | 24 issues |
| `run_01e6aa86a21f499f` | 수요/혼잡 단정 금지, 가격 단정 표현 | 4 | 10 | 0 | 14 issues |
| `run_b25b5f6c9ec24e1b` | 가격 단정 표현 | 0 | 6 | 0 | 6 issues |
| `run_f9182c6a30814cab` | 가격 단정 표현 | 0 | 10 | 0 | 10 issues |
| `run_87d306e83f1549c3` | 가격 단정 표현 | 1 | 10 | 0 | 11 issues |
| `run_bec1f1b99da44fe5` | 가격 단정 표현 | 0 | 4 | 0 | 4 issues |

Aggregate category counts:
- 품질 평가 issue: 36
- 정상 issue: 32
- 모호한 issue: 20
- 과잉 issue: 6

Observed pattern:
- `가격 단정 표현` is present in many avoid lists, but only a small subset of QA issues directly address price, fee, free, or paid claims.
- `이미지 사용권 확인 필요` is not consistently treated as an image-rights issue. QA often flags source-id gaps, generic detail gaps, or promotional wording instead.
- `수요/혼잡 단정 금지` is only directly relevant when QA cites demand/crowding language. Many issues in those runs instead concern operating hours, safety, reservation, or detailed-description gaps.
- `run_ac68dfed2d5345e3` cannot be evaluated for QA quality because its `final_output` is JSON `null`; the workflow row status is `failed`.

### Issues QA Should Not Judge Without Explicit Scope

- copy 매력도/상세함/완성도: observed 28 time(s) as avoid-unmatched or user-scope-unclear QA output.
- 운영시간/예약/우천/안전 gap: observed 11 time(s) as avoid-unmatched or user-scope-unclear QA output.
- source id 보정/부족 자체를 사용자용 QA 문제로 판단: observed 8 time(s) as avoid-unmatched or user-scope-unclear QA output.
- 검색 키워드/FAQ 중복 같은 편집 품질: observed 5 time(s) as avoid-unmatched or user-scope-unclear QA output.

Concrete examples from the nine-run sample:
- Pet policy or unrelated wellness topics did not appear in these nine QA reports, but the same guard should block them unless requested by the user or explicitly present in product claims.
- “상세 정보 부족”, “상품 매력도”, “상품의 완성도”, FAQ duplication, and search keyword relevance are editorial quality concerns, not avoid-centered claim QA unless a separate copy-quality rubric is intentionally enabled.
- Source-id correction messages such as “상품에 연결할 근거 id가 부족해 서버가 사용 가능한 근거를 보정했습니다” expose internal evidence wiring to QA. That may be useful for developer diagnostics, but it is not a user-facing claim violation by itself.
- Operational gaps such as operating hours, reservation, weather, lighting, and safety should be judged only when the product copy makes a concrete unsupported claim, or when the user explicitly asks QA to verify that dimension.

### Prompt / Schema / Validator Improvement Criteria

QA scope rules:
- QA must separate `avoid_violation`, `unsupported_claim`, `evidence_gap`, and `copy_quality` instead of collapsing everything into `general`.
- Avoid-centered QA should first map each issue to a specific user `avoid` item. If no avoid item matches, the issue should be emitted only when there is a concrete unsupported claim in product or marketing text.
- Request-context topics such as pet policy, wellness, medical effects, safety, reservation, weather, and operating hours must not appear as gaps unless they are user-requested, present in the product concept, or asserted in visible copy.
- Internal data problems such as source-id correction, evidence fallback, or server-side source filtering should be routed to a developer diagnostic channel, not normal user QA, unless they caused a visible unsupported claim.

Message quality rules:
- Every QA issue must quote the exact problematic phrase from product, sales copy, FAQ, SNS, or claims. Generic messages such as “상세 정보 부족” should fail validation unless they cite the affected text field and phrase.
- `suggested_fix` should tell the user what to change in the visible copy, not mention internal source-id repair unless the user is in a developer/debug view.
- If the issue is about missing evidence, the message should say which visible claim lacks evidence and which evidence dimension is missing.

Validator criteria:
- Reject QA issues with `type=general` when a more specific category is available.
- Require `matched_avoid_item` for avoid violations. If absent, require `quoted_problem_phrase` and `evidence_risk_reason`.
- Add a schema distinction between `user_visible_issue=true` and `developer_diagnostic=true`.
- Add a validator check that prevents out-of-context gap types such as `missing_pet_policy` unless that topic appears in the input request, avoid list, product copy, or selected evidence.

### 15.0-B Summary

- Runs with QA issues: `run_0f3679c894d84215`, `run_331348e02b064d28`, `run_1241212633404670`, `run_01e6aa86a21f499f`, `run_b25b5f6c9ec24e1b`, `run_f9182c6a30814cab`, `run_87d306e83f1549c3`, `run_bec1f1b99da44fe5`.
- Runs with no QA issues: none.
- Runs whose QA report could not be analyzed: `run_ac68dfed2d5345e3 (status=failed, final_output is not an object)`.
- Top problematic issue types in this sample:
  - copy/detail richness judged as QA risk: 28
  - operational gap judged without explicit avoid scope: 11
  - source_id/evidence wiring issue exposed to QA: 8

---

Back to index: [27_PHASE_15_QUALITY_AUDIT.md](27_PHASE_15_QUALITY_AUDIT.md)
