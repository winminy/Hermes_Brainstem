# P4_BACKENDS — 외부 어댑터

## Phase 목표

외부 시스템 어댑터 구현: LightRAG HTTP (필수), Notion 직접 API (notion-client), 임베딩 백엔드 (API / 로컬 pluggable), Obsidian 쓰기(fs | advanced-uri), LLM provider(Anthropic·OpenAI·호환), GDrive MCP.

## 진입 선행조건

- Phase 0 RECON 실측치 반영
- Phase 3 core 유틸 통과
- `config.yaml` 기본값은 RECON 결과로 확정된 것만

## 수용 기준

- [ ]  `backends/lightrag.py` — upsert·query·delete (RECON openapi.json 스키마 준거)
- [ ]  `backends/notion.py` — notion-client 래퍼 (query_datasource·페이징), API key는 secrets 계층에서 주입. MCP 서버 설치 불필요.
- [ ]  `backends/embedding/__init__.py` — EmbeddingBackend Protocol
- [ ]  `backends/embedding/api.py` — 원격 임베딩 (OpenAI·호환)
- [ ]  `backends/embedding/local.py` — 로컬 임베딩 (sentence-transformers)
- [ ]  `config embedding.backend: api | local` 로 런타임 선택, LightRAG upsert/query에 주입
- [ ]  `backends/obsidian_writer.py` — fs 기본, advanced-uri 선택지원, filelock 경유
- [ ]  `backends/llm/__init__.py` — Anthropic tool_use + OpenAI json_schema 표준화 인터페이스
- [ ]  `backends/gdrive_mcp.py` — persist.attach 시에만 호출
- [ ]  재시도 정책: 동일 방식 2회 → 대체 방식 2회 → 총 4회 실패 시 사용자 보고 (SPEC §11-8)
- [ ]  pytest: 각 backend mock 기반 단위 테스트 + 연계 테스트

## 교차참조

| 이 Phase | 동시 참조 | 이유 |
| --- | --- | --- |
| P4 ↔ P0 | RECON 실측 | 엔드포인트·SDK 버전 근거 |
| P4 → P5 | llm 인터페이스 | structured output 호출 |
| P4 → P6 | lightrag upsert | Reduce 후 인덱스 반영 |
| P4 → P10 | notion_mcp | MCP 서버가 소비 |
| P4 → P11 | gdrive_mcp·notion_mcp | 자동훅 notion_sync |

## SPEC 발췌 대상

[헤르메스 커스텀 메모리 프로바이더 — 전체 사양](https://www.notion.so/SOURCE_DOC_ID?pvs=21)

- §1-2 외부 접점 표
- §11-8 재시도 정책

## IMPL 발췌 대상

[헤르메스 메모리 프로바이더 구현 요청문 — 코드 구현 상세 설계](https://www.notion.so/SOURCE_DOC_ID?pvs=21)

- §14 backends 전 범위
- §1-2 외부 접점 (다시)
- §2 의존성 표

## 구현 포인트

- 모든 백엔드는 **인터페이스(Protocol) → 구현 클래스** 2단 구조로 테스트 주입 용이하게
- LightRAG upsert 멱등성은 source 해시 기반, Phase 9 search에서 동일 규칙 재사용
- LLM 백엔드는 structured output 실패 시 텍스트 재파싱 경로를 거치지 않고 재시도로 넘김 (원칙 4)

## 리포트 템플릿

[7절]