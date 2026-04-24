# schemas/ — JSON 스키마 6종

<aside>
📁

tool call 입력 스키마·Reduce 출력 스키마 6종의 JSON 원본을 별도 파일로 유지. 프롬프트에 임베드하지 않고 **경로로만 지시**하여 Codex가 JSON 복붙 실수를 저지르지 않도록 차단.

</aside>

## 구성 (IMPL §6에서 추출)

- `persist_process.json` — persist.process tool 입력
- `persist_recall.json` — [semantic.search](http://semantic.search) tool 입력 (+ direct_[file.read](http://file.read))
- `persist_inbox_process.json` — inbox graduator 내부 잔류 (성제 결과 조회)
- `persist_attach.json` — persist.attach tool 입력
- `map_output.json` — Map 단계 출력 스키마
- `reduce_output.json` — Reduce 단계 출력 (frontmatter 9필드 + 본문)

## 파일 작성 대상 경로

`~/Desktop/hermes-memory-provider/code/plugins/memory/hermes_memory/schemas/`

## 작성 규칙

- JSON Schema 2020-12 드래프트 준수
- `$id` 필수, `$ref`로 공용 frontmatter 9필드 재사용
- `additionalProperties: false` 고정
- enum 값은 `_system/` SSoT와 일치 (vault_[spec.md](http://spec.md) type 7종, [TAGS.md](http://TAGS.md) registry)
- Anthropic tool_use·OpenAI json_schema 양쪽 호환이 가능한 최소공통집합 문법만 사용

## 참조되는 Phase

- P5 schema_builder가 본 스키마의 frontmatter 조각을 SSoT로 사용
- P6 Reduce가 `reduce_output.json` 기준으로 LLM structured output 호출
- P10 MCP tool이 나머지 4종을 입력 검증에 사용