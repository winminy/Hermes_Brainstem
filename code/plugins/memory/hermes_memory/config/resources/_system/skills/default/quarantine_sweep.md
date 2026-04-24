---
uuid: obs:20260423T0942-12
area: knowledge
type: knowledge
tags:
  - PKM
  - 개발
date: 2026-04-23
updated: 2026-04-23
source:
  - multi:phase2-meta-bcd-default-skill-quarantine-sweep
source_type: ""
file_type: md
---

# quarantine_sweep
- 상태: provisional default skill draft
- 역할: invariant 위반 문서를 quarantine 영역으로 이동시키는 메타 스킬
- authoritative quarantine 기준은 [[quarantine_policy]]를 따른다

## Responsibilities
- closed 9-field schema 위반 note 식별
- 잘못된 note를 `<vault>/_quarantine/YYYY-MM/`로 이동
- hash-only audit trail만 남기고 silent rewrite는 금지
- 검색 및 normal graduation 경로에서 격리 artifact를 제외

## Inputs and outputs
- 입력: candidate note path, invariant 검사 결과
- 출력: quarantine destination path, hash-only audit record
- 금지: frontmatter 임의 확장, 원본 삭제 후 무기록 처리
