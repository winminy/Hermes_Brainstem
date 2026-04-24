# cross_refs — 교차참조 중앙 표

<aside>
🔗

Phase 문서를 원자화했을 때 잊히기 쉽은 **암묵적 교차의존**을 중앙에서 관리. Phase 파일 생성·갱신 시 반드시 여기를 먼저 갱신하고, 각 Phase 페이지 상단 "교차참조" 절에 자신 행만 복사.

</aside>

## 전체 교차참조

| 이 Phase | 동시 참조 Phase·섹션 | 이유 |  |  |  |
| --- | --- | --- | --- | --- | --- |
| P0 | 00_CORE 절대원칙 9 | 조사의 전제 (추측 금지) | P0 → P1 | P1 메타문서 A 3종 | RECON·QUESTIONS 통과 필수 |
| P0 → P4 | P4 backends 전반 | 엔드포인트·SDK 실측이 구현 근거 | P1 → P2 | P2 B data_ops/file_policy | vault_spec file_type enum SSoT 연결 |
| P1 → P3 | P3 core.frontmatter | 9필드 파서 규격 근거 | P1 → P5 | P5 schema_builder | structured output 입력 |
| P1 → P11 | P11 notion_sync | notion_datasource_map → 변환 대상 범위 | P2 → P6 | P6 dispatcher | binary_policy·retention 분기 조건 |
| P2 → P7 | P7 inbox dedup | file_policy·binary_policy | P2 → P8 | P8 persist.attach | scope_policy |
| P2 → P11 | P11 hook_router | hook_registry | P3 → P5 | schema_builder | frontmatter·invariant_guard 직접 사용 |
| P3 → P6 | Reduce·commit | uuid_gen·hasher | P3 → P9 | P9 search | wikilink.suggest_links |
| P3 → P12 | P12 converter | 9필드 채움 | P4 → P5 | llm backend | structured output 호출 |
| P4 → P6 | lightrag upsert | commit 단계 | P4 → P10 | notion_mcp | MCP 서버 소비 |
| P4 → P11 | gdrive_mcp·notion_mcp | 자동훅 notion_sync | P5 → P6 | Reduce LLM 호출 | schema_builder |
| P5 → P11 | 자동훅 3종 진입점 | hook_router | P6 → P7 | graduator commit | α 정책 공유 |
| P6 → P8 | persist.attach dispatcher | scope 분기 공유 | P6 → P12 | converter → map 진입 | 파이프라인 진입점 |
| P7 ↔ P8 | source 멱등성 (`attach:`) | 중복 방지 규칙 | P7 ↔ P12 | converter 전처리 | graduator 입력 계약 |
| P7 → P11 | session_close exclude | inbox 상태 읽기 | P8 → P11 | skill_attach audit exclude | file_id 해시 규칙 |
| P9 → P10 | MCP tool 노출 | search 토굄 | P10 ↔ P6·P8·P9 | tool 랜딩 허브 | 4 tool 진입점 |
| P11 ↔ P1·P2·P4·P5·P7·P8·P12 | 자동훅 주변 전체 | 3종 훅이 전 레이어 터치 | P12 ↔ P2 | binary_policy | 바이너리 분리 규칙 |
| P12 ↔ P11 | notion_sync | notion_block converter 소비자 | P13 ↔ 전 Phase | §22 Acceptance | 전체 기능 검증 |

## 사용법

1. **Phase 파일 작성 시**: 이 표에서 자신 Phase 행을 찾아 상단 "교차참조" 절에 복사
2. **사양·구현문 수정 시**: 변경이 낳는 교차의존 행을 먼저 업데이트 → 영향 받는 Phase 페이지들에 전파
3. **Codex 투입 시**: 해당 행의 "동시 참조" 컬럼에 적힌 Phase 페이지의 **지정 섹션만** 발췌하여 함께 첨부 (파일 전체 X)