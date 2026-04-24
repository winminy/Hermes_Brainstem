---
uuid: obs:20260423T0942-10
area: knowledge
type: knowledge
tags:
  - PKM
  - 개발
date: 2026-04-23
updated: 2026-04-23
source:
  - multi:phase2-meta-bcd-default-skill-session-close
source_type: ""
file_type: md
---

# session_close
- 상태: provisional default skill draft
- 역할: 세션 종료 시 inbox 정리, hash-only idempotency, `scope=skill` attach exclude 규칙을 설명하는 메타 스킬
- authoritative hook binding은 [[hook_registry]]를 따른다

## Responsibilities
- 종료 경계에서 중복 실행을 막기 위한 hash-only key 사용
- `scope=knowledge` artifact만 정리 대상으로 유지
- `scope=skill` attach의 file_id hash는 감사 대상에서 제외
- raw conversation transcript 저장을 금지한 채 inbox 상태만 정리

## Inputs and outputs
- 입력: `session_id`, `conversation_history`, `model`, `platform` 등 평탄 kwargs
- 출력: 정리된 inbox 상태, dedup reconciliation 기록, hash-only audit record
- 금지: 원문 대화 평문 저장, skill reference 경로 스캔
