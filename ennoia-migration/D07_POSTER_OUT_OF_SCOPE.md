# D07. Poster Out of Scope

이 문서는 이전 결정 기록이다.
현재 포스터 생성 테스트 branch는 `D12_POSTER_BRANCH_AND_IMAGE_API.md`를 따른다.

이전 결정에서는 Ennoia 멀티에이전트 구현에서 포스터와 `gpt-image-2` 호출을 제외했다.
이 결정은 Start 직후 Classify 분기와 외부 이미지 생성 API 커넥터 테스트 구조가 추가되면서 대체되었다.

이유:

- Ennoia API 커넥터에서 이미지 생성 API의 multipart/base64 응답 처리가 불확실하다.
- MCP 서버를 직접 만들어 붙이는 비용이 현재 run 마이그레이션보다 크다.
- 먼저 관광상품 기획 Markdown 워크플로우를 안정화하는 것이 우선이다.

나중에 추가할 경우 권장 구조:

```text
ProposalEditorAgent
→ PosterPromptAgent
→ 외부 Poster MCP 또는 별도 이미지 프록시
→ 이미지 URL을 최종 Markdown에 추가
```

현재 문서와 Agent 프롬프트에는 A15 PosterBriefAgent, A16 PosterPromptBuilderAgent, A17 PosterImageGeneratorAgent를 포함한다.
포스터 branch는 기존 여행 상품 추천 branch와 분리되어 있으며, A14 성공 응답 마지막의 안내 문구를 보고 사용자가 후속 요청을 입력하는 방식으로 진입한다.
