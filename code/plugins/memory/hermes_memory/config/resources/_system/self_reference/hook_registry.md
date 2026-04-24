---
uuid: obs:20260423T0942-6
area: knowledge
type: knowledge
tags:
  - PKM
  - 개발
date: 2026-04-23
updated: 2026-04-23
source:
  - multi:phase2-meta-bcd-hook-registry
source_type: ""
file_type: md
---

# hook_registry
- 이 문서는 Hermes Memory Provider가 자동 실행하는 훅 3종의 trigger, 입력, downstream handoff를 정의한다
- hook 대상 범위는 [[notion_datasource_map]], attach 제외 규칙은 [[scope_policy]], 격리 동작은 [[quarantine_policy]], skill 매핑은 [[skill_registry]]를 따른다

## Common contract
- 훅 입력은 중첩 `session.*`가 아니라 평탄 kwargs를 사용한다
- 공통 필수 후보는 `session_id`, `conversation_history`, `model`, `platform`이다
- 훅은 원문을 LLM 사전 요약 없이 그대로 파이프라인에 전달한다
- 훅은 idempotent해야 하며, 중복 실행 방지에는 hash-only audit를 사용한다

## Registry
```yaml
version: 1
hooks:
  - name: session_close
    trigger: end_of_session_or_finalize_boundary
    cadence: per_session
    downstream:
      - inbox_state_cleanup
      - dedup_reconciliation
    excludes:
      - scope=skill attach artifacts by file_id hash
    skill_binding: session_close
  - name: notion_sync
    trigger: scheduled_scan
    cadence: daily
    downstream:
      - notion datasource scan
      - persist.process for eligible rows only
    datasource_scope:
      - Sub-task DB with include_when rules
      - User Info DB all rows
    skill_binding: notion_sync
  - name: quarantine_sweep
    trigger: scheduled_or_manual_invariant_sweep
    cadence: scheduled
    downstream:
      - move invalid note to <vault>/_quarantine/YYYY-MM/
      - emit hash-only audit record
    skill_binding: quarantine_sweep
```

## Trigger notes
| hook | trigger | main action | exclusions |
| --- | --- | --- | --- |
| `session_close` | 세션 종료/초기화 경계 | inbox 상태 정리, 중복 정리용 hash 기록 | `scope=skill` attach |
| `notion_sync` | 하루 1회 scheduler | [[notion_datasource_map]]에 등재된 row만 `persist.process` 진입 | GDrive, 미등재 DB |
| `quarantine_sweep` | invariant 위반 탐지 | invalid note를 quarantine dir로 이동 | schema-valid note |

## Operational notes
- `notion_sync`는 Sub-task DB의 `유형 ∈ {메모/ 리소스, Project Backlogs}`와 User Info DB만 소비한다
- `session_close`는 별도 런타임 재실행을 감안해 file_id hash 기반 exclude를 사용한다
- `quarantine_sweep`의 authoritative 상태는 경로 이동이며, frontmatter 확장은 Phase 1의 9필드 스키마를 침범하지 않는다
