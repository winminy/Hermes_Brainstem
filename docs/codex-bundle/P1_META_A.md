# P1_META_A — 엔트리 메타문서 3종

## Phase 목표

A 그룹 엔트리 메타문서 3종(`vault_spec.md`, `TAGS.md`, `notion_datasource_map.md`)의 완성형 초안을 `vault_meta/_system/`에 작성. 이후 Phase의 schema_builder·hook_router·pipeline이 참조할 SSoT를 확정.

## 진입 선행조건

- Phase 0 RECON·QUESTIONS 회수 완료
- 00_CORE 상시 첨부

## 수용 기준

- [ ]  `vault_meta/_system/vault_spec.md` — frontmatter 9필드 SSoT, type enum 7종, area=knowledge 단일, 옵시디언 문법 규칙 명시, vault root 실측값 /root/obsidian/Remy's brain/Remy's brain 반영
- [ ]  `vault_meta/_system/TAGS.md` — registry enum 정의, 계층 구조, LLM 가시 필드
- [ ]  `vault_meta/_system/notion_datasource_map.md` — 노션 DB → type·tags·area 매핑 (Sub-task DB, User Info DB 포함; GDrive 파일 DB는 out-of-scope: 외부 파일 카탈로그)
- [ ]  세 문서 상호 참조 일관성 검증

## 교차참조

| 이 Phase | 동시 참조 | 이유 |
| --- | --- | --- |
| P1 → P2 | vault_spec의 file_type enum → data_ops/file_[policy.md](http://policy.md) | SSoT 연결 |
| P1 → P3 | vault_spec frontmatter → core.frontmatter | 파서 규격 근거 |
| P1 → P5 | vault_spec·TAGS → schema_builder | structured output 스키마 빌드 입력 |
| P1 → P11 | notion_datasource_map → notion_sync 훅 | 하루 1회 변환 대상 범위 |

## SPEC 발췌 대상

[헤르메스 커스텀 메모리 프로바이더 — 전체 사양](https://www.notion.so/be5d21bbad5046bbada8c72195b8c64a?pvs=21)

- §8 _system 메타문서 세트
- §8-1 vault_[spec.md](http://spec.md)
- §8-2 [TAGS.md](http://TAGS.md)
- §8-4 notion_datasource_[map.md](http://map.md)
- §4-6 Reduce 출력 스키마
- §13 frontmatter 스키마 (9필드)

## IMPL 발췌 대상

[헤르메스 메모리 프로바이더 구현 요청문 — 코드 구현 상세 설계](https://www.notion.so/a3cc456c55fb43689c7a13f4007ee9f4?pvs=21)

- §4-4 9필드 강제 경로
- §7 interpreter·schema_builder
- §14 notion MCP 어댑터 (datasource_map 소비처)
- §16 core/ 전체 (참조)

## 구현 포인트

- 세 문서 모두 **완성형** (프로바이더 로드 직후 동작 가능한 수준)
- type enum은 정확히 7종 (person, knowledge, tool, schedule, preference, project, memo)
- [TAGS.md](http://TAGS.md)는 계층 표기(상위/하위) + LLM 가시 필드 명시
- notion_datasource_map은 DB ID·유형 조건·매핑 표로 기계 가독 가능한 포맷

## 리포트 템플릿 (PHASE_1_[REPORT.md](http://REPORT.md))

[7절 스켈레톤 — 00_CORE 규격 사용]