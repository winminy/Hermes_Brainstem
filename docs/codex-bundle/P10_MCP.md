# P10_MCP — MCP 서버·tool 4종

## Phase 목표

MCP 서버 바인딩 + tool 4종 (`persist.process`, `persist.attach`, `semantic.search`, `direct_file.read`) 노출. tool call JSON 스키마 강제.

## 진입 선행조건

- Phase 6·7·8·9 통과

## 수용 기준

- [ ]  `mcp/server.py` — MCP 서버 엔트리포인트, tool 4종 등록
- [ ]  `mcp/tools/persist_process.py` — 입력 스키마 + pipeline/persist_process 로 위임
- [ ]  `mcp/tools/persist_attach.py` — 동일한 패턴, scope 파라미터 포함
- [ ]  `mcp/tools/semantic_search.py` — search/semantic을 노출
- [ ]  `mcp/tools/direct_file_read.py` — search/direct_file을 노출
- [ ]  스키마 위반 시 런타임 거부 (원칙 7)
- [ ]  pytest: 각 tool 계약 검증 + MCP 프로토콜 라운드트립

## 교차참조

| 이 Phase | 동시 참조 | 이유 | P10 ↔ P6 | persist_process 진입점 | tool 랜딩 위치 |
| --- | --- | --- | --- | --- | --- |
| P10 ↔ P8 | persist_attach 진입점 | 동상 | P10 ↔ P9 | semantic·direct_file | 검색 노출 |

## SPEC 발췌 대상

[헤르메스 커스텀 메모리 프로바이더 — 전체 사양](https://www.notion.so/be5d21bbad5046bbada8c72195b8c64a?pvs=21)

- §3 tool 계약 4종
- §11-7 JSON 스키마 강제

## IMPL 발췌 대상

[헤르메스 메모리 프로바이더 구현 요청문 — 코드 구현 상세 설계](https://www.notion.so/a3cc456c55fb43689c7a13f4007ee9f4?pvs=21)

- §6 tool 입력 스키마 4종
- §17 MCP 서버 바인딩

## 구현 포인트

- tool 스키마는 `schemas/*.json` 자산 폴더에서 SSoT로 명시 운용
- MCP 서버는 `~/.hermes/config/mcp.yaml` 등록 규약 RECON 결과 준수

## 리포트 템플릿

[7절]