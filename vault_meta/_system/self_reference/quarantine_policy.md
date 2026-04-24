---
uuid: obs:20260423T0942-7
area: knowledge
type: knowledge
tags:
  - PKM
  - 개발
date: 2026-04-23
updated: 2026-04-23
source:
  - multi:phase2-meta-bcd-quarantine-policy
source_type: ""
file_type: md
---

# quarantine_policy
- 이 문서는 invariant 위반 문서의 격리 기준과 이동 규칙을 정의한다
- invariant 목록은 [[vault_spec]], 자동 실행 훅은 [[hook_registry]]를 따른다

## Quarantine triggers
- `uuid`, `date`, `source` 불변 필드가 생성 후 변경된 경우
- `area`가 `knowledge`, `inbox` enum 밖인 경우
- `type`이 [[vault_spec]] enum 밖인 경우
- `tags`에 [[TAGS]] registry 밖 값이 있는 경우
- raw conversation transcript를 본문에 직접 저장하려는 시도가 감지된 경우
- provider 관리 note가 허용 루트(`inbox/`, `knowledge/`) 밖에 생성된 경우

## Quarantine action
```yaml
version: 1
quarantine:
  destination: <vault>/_quarantine/YYYY-MM/
  mode: move_read_only_first
  preserves:
    - original file bytes
    - original basename when possible
    - hash-only audit trail
  forbids:
    - source mutation to explain the move
    - silent field rewriting in place
```

## Operational rules
- 격리는 “수정 후 계속 사용”보다 “원본 보존 후 격리”가 우선이다
- quarantine 이동은 note를 자동 정정하지 않는다. 수정은 별도 승인 또는 후속 파이프라인에서 처리한다
- 격리된 artifact는 검색 결과와 normal graduation 대상에서 제외한다
- Phase 1의 frontmatter 9필드는 closed schema이므로, 격리 상태 표시는 추가 frontmatter가 아니라 경로 이동을 authoritative signal로 사용한다

## Cross-phase caution
- P9 문서에는 `frontmatter quarantine: true` 표현이 있으나, Phase 1 SSoT의 9필드 닫힌 스키마와 충돌한다
- 본 Phase에서는 경로 기반 격리를 우선 정책으로 채택하고, schema 확장 여부는 `docs/QUESTIONS.md`에서 확인이 필요하다
