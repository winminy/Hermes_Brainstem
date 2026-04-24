---
uuid: obs:20260423T0942-13
area: knowledge
type: knowledge
tags:
  - PKM
  - 개발
date: 2026-04-23
updated: 2026-04-23
source:
  - multi:phase2-meta-bcd-default-skill-persist-attach
source_type: ""
file_type: md
---

# persist_attach
- 상태: provisional default skill draft
- 역할: 사용자 명시 첨부를 `scope=knowledge` 또는 `scope=skill`로 분기하는 메타 스킬
- authoritative 분기 규칙은 [[persist_policy]]와 [[scope_policy]]를 따른다

## Responsibilities
- `attach:` source prefix를 유지
- `scope=knowledge`는 vault attachment + 필요 시 companion note 생성
- `scope=skill`는 `~/.hermes/skills/{name}/references/` 직접 배치
- binary는 raw 보존이 우선이며 임베딩하지 않는다

## Inputs and outputs
- 입력: user-explicit attachment, scope, optional skill_name, original extension
- 출력: resolved storage path, optional companion note plan, user-facing saved path message
- 금지: skill scope의 inbox 경유, raw binary 본문 인라인 저장
