# P9_SEARCH — semantic·direct_file

## Phase 목표

검색 레이어 구현: `semantic.search` (LightRAG query 래퍼) + `direct_file.read` (볼트 직접 조회).

## 진입 선행조건

- Phase 3 (wikilink), Phase 4 (lightrag backend) 통과

## 수용 기준

- [ ]  `search/semantic.py` — LightRAG query 래퍼, type·tag 필터, 점수 잉계
- [ ]  `search/direct_file.py` — 볼트 경로로 직접 읽기 (frontmatter + 본문 조합)
- [ ]  격리 영역 (invariant 위반 문서)는 검색 결과에서 제외
- [ ]  pytest: mock LightRAG 응답 + 실파일 읽기 테스트

## 교차참조

| 이 Phase | 동시 참조 | 이유 | P9 ↔ P3 | wikilink.suggest_links | 동일 LightRAG query 규칙 재사용 |
| --- | --- | --- | --- | --- | --- |
| P9 ↔ P4 | lightrag backend | 직접 소비 | P9 → P10 | MCP tool | 검색은 MCP를 통해 노출 |

## SPEC 발췌 대상

[헤르메스 커스텀 메모리 프로바이더 — 전체 사양](https://www.notion.so/be5d21bbad5046bbada8c72195b8c64a?pvs=21) §6 검색 전 범위

## IMPL 발췌 대상

[헤르메스 메모리 프로바이더 구현 요청문 — 코드 구현 상세 설계](https://www.notion.so/a3cc456c55fb43689c7a13f4007ee9f4?pvs=21)

- §6-2 검색 tool 스키마
- §12 search 모듈

## 구현 포인트

- [semantic.search](http://semantic.search)는 query 유형(q, type, tags, top_k) 지원
- 격리 필터는 frontmatter `quarantine: true` 항목 기준
- direct_file은 절대경로 보호 (볼트 밖 접근 금지)

## 리포트 템플릿

[7절]