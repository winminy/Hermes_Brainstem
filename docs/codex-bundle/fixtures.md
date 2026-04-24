# fixtures/ — 테스트 픽스쳐

<aside>
📁

Phase 12 converter·Phase 13 E2E에서 사용할 샘플 데이터 자산 폴더. 실제 LightRAG·실제 LLM·실제 Notion 독립적인 **결정적(deterministic)** 테스트 입력.

</aside>

## 구성

- `conversation_sample.json` — Hermes 세션 대화 샘플 (텍스트 + 첨부 바이너리 참조)
- `notion_row_sample.json` — Notion MCP `query_datasource` 응답 샘플 (Sub-task DB·User Info DB 각 1건)
- `notion_block_sample.json` — Notion block JSON 샘플 (converter 입력)
- `binary_sample/` — 테스트용 이미지·PDF·주요 확장자 샘플 (임베딩 미대상 검증)
- `lightrag_response_sample.json` — LightRAG query 응답 mock (top-K 결과)
- `llm_structured_output_sample.json` — Reduce 단계 mock 출력 (frontmatter 9필드 + 본문)

## 파일 작성 대상 경로

`~/Desktop/hermes-memory-provider/tests/fixtures/`

## 작성 규칙

- 원문 대화가 아닌 **샘플성 푸머용 문자열**만 (원칙 2)
- 바이너리는 최소 크기 (KB 단위), 검증되는 해시가 고정되도록 고정 파일
- PII 포함 금지 (테스트 전용 플레이스홈더만)

## 참조되는 Phase

- P12 converter 단위 테스트 (conversation_sample·notion_block_sample)
- P13 E2E 15항 시나리오 입력 (전체 픽스쳐)
- P6 Reduce mock 테스트 (llm_structured_output_sample)
- P7 inbox dedup 유사도 테스트 (lightrag_response_sample)