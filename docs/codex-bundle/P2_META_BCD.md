# P2_META_BCD — 데이터·참조·스킬 기준 13종

## Phase 목표

B (data_ops 3종) + C (self_reference 4종) + D (skills 6종) 메타문서 완성형 초안을 `vault_meta/_system/`에 작성. 사용자 검수 후 volt로 이관.

## 진입 선행조건

- Phase 1 메타문서 A 3종 검수 통과

## 수용 기준

### B. data_ops (3종)

- [ ]  `_system/data_ops/file_policy.md` — file_type enum, 확장자별 저장 경로·converter 매핑
- [ ]  `_system/data_ops/retention.md` — 보관 기간·감사 해시 정책
- [ ]  `_system/data_ops/binary_policy.md` — 바이너리 임베딩 금지, `<vault>/attachments/YYYY/MM/` 규칙

### C. self_reference (4종)

- [ ]  `_system/self_reference/persist_policy.md` — persist.process vs persist.attach 분기
- [ ]  `_system/self_reference/scope_policy.md` — scope=skill β 정책
- [ ]  `_system/self_reference/hook_registry.md` — 자동훅 3종 트리거·기준 매핑
- [ ]  `_system/self_reference/quarantine_policy.md` — invariant 위반 격리 규칙

### D. skills (6종)

- [ ]  `_system/skills/skill_spec.md` — 스킬 디렉터리 구조, references/ 규약
- [ ]  `_system/skills/skill_registry.md` — 스킬 목록 + 훅↔스킬 매핑
- [ ]  `_system/skills/default/*.md` — 기본 스킬 4종 초안

## 교차참조

| 이 Phase | 동시 참조 | 이유 |
| --- | --- | --- |
| P2 ↔ P1 | vault_spec type·file_type enum | SSoT 연결 |
| P2 → P7 | file_policy·binary_policy | inbox 4단 dedup 조건 |
| P2 → P8 | scope_policy | persist.attach 분기 입력 |
| P2 → P11 | hook_registry | 자동훅 3종 라우팅 |

## SPEC 발췌 대상

[헤르메스 커스텀 메모리 프로바이더 — 전체 사양](https://www.notion.so/be5d21bbad5046bbada8c72195b8c64a?pvs=21) §8-4 전 범위 (B·C·D 정책)

## IMPL 발췌 대상

[헤르메스 메모리 프로바이더 구현 요청문 — 코드 구현 상세 설계](https://www.notion.so/a3cc456c55fb43689c7a13f4007ee9f4?pvs=21)

- §5 inbox 4단 dedup (file_policy·binary_policy 소비처)
- §6-4 persist.attach (scope_policy 소비처)
- §11 attach 파이프라인
- §13 자동훅 (hook_registry 소비처)

## 구현 포인트

- 체크리스트 16종 중 13종이 본 Phase 대상 (A 3종은 Phase 1, E `config.yaml`은 Phase 4·10에서)
- 완성형 초안은 [Hermes Memory Provider — 필요 메타문서 체크리스트](https://www.notion.so/Hermes-Memory-Provider-aaf29ba05b504304bfa52059bf20d0dc?pvs=21)의 각 항목 요구사항을 전부 충족해야 함
- 사용자 검수 통과가 Phase 3 이후의 **전면 게이트**

## 리포트 템플릿

[7절 스켈레톤]