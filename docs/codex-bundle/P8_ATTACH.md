# P8_ATTACH — persist.attach·scope 분기

## Phase 목표

사용자 명시 첨부 경로(`persist.attach`) 구현. scope(`knowledge` | `skill`)에 따라 볼트 또는 스킬 references/로 직접 배치. β 정책.

## 진입 선행조건

- Phase 6 dispatcher, Phase 7 inbox 통과
- `_system/self_reference/scope_policy.md` 확정

## 수용 기준

- [ ]  `pipeline/persist_attach.py` — scope 분기 구현
- [ ]  `scope=knowledge` → 볼트 inbox/ 경유 (normal)
- [ ]  `scope=skill` → `<hermes-home>/skills/{name}/references/` 직접 배치, inbox 건너뜀
- [ ]  바이너리는 `<vault>/attachments/YYYY/MM/` 또는 skills references/ (scope 따라)
- [ ]  source prefix = `attach:` 규칙
- [ ]  pytest: scope 2종 × 파일 유형(.md, 바이너리) 매트릭스

## 교차참조

| 이 Phase | 동시 참조 | 이유 |
| --- | --- | --- |
| P8 ↔ P7 | source 멱등성 (`attach:`) | 중복 방지 |
| P8 ↔ P6 | dispatcher scope 분기 | 공유 규칙 |
| P8 ↔ P2 | scope_policy·binary_policy | SSoT 입력 |
| P8 → P11 | session_close exclude | scope=skill은 audit에서 제외 규칙 |

## SPEC 발췌 대상

[헤르메스 커스텀 메모리 프로바이더 — 전체 사양](https://www.notion.so/SOURCE_DOC_ID?pvs=21)

- §3-4 persist.attach
- §4-2 attach 경로
- §11-3·11-11 scope 정책

## IMPL 발췌 대상

[헤르메스 메모리 프로바이더 구현 요청문 — 코드 구현 상세 설계](https://www.notion.so/SOURCE_DOC_ID?pvs=21)

- §6-4 persist.attach
- §11 attach 파이프라인
- §13-1 session_close의 exclude 로직 (file_id 해시)

## 구현 포인트

- scope=skill은 Reduce도 거치지 않음(볼트 인덱싱 대상 아님). 단, frontmatter는 생성.
- GDrive MCP 호출은 **persist.attach 시에만** (SPEC §11-10)
- attach 완료 후 사용자에게 저장 경로 회신 필수

## 리포트 템플릿

[7절]