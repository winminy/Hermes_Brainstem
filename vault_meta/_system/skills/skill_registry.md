---
uuid: obs:20260423T0942-9
area: knowledge
type: knowledge
tags:
  - PKM
  - 개발
date: 2026-04-23
updated: 2026-04-23
source:
  - multi:phase2-meta-bcd-skill-registry
source_type: ""
file_type: md
---

# skill_registry
- 이 문서는 Phase 2에서 정의한 기본 스킬 초안 목록과 훅↔스킬 매핑을 기록한다
- 디렉터리 구조는 [[skill_spec]], hook contract는 [[hook_registry]], scope 규칙은 [[scope_policy]]를 따른다

## Registry status
- bundled sources에는 `skills/default/*.md` 패턴만 있고 개별 basename SSoT는 없었다
- 본 Phase는 hook/tool 이름과 직접 대응하는 provisional basenames로 4종 초안을 작성한다
- canonical 여부는 `docs/QUESTIONS.md`의 확인 전까지 provisional 상태다

## Default skill drafts
```yaml
version: 1
default_skills:
  - id: session_close
    file: [[session_close]]
    status: provisional_draft
    entrypoint: hook
  - id: notion_sync
    file: [[notion_sync]]
    status: provisional_draft
    entrypoint: hook
  - id: quarantine_sweep
    file: [[quarantine_sweep]]
    status: provisional_draft
    entrypoint: hook
  - id: persist_attach
    file: [[persist_attach]]
    status: provisional_draft
    entrypoint: manual_attach
```

## Hook bindings
| hook | bound skill draft | reason |
| --- | --- | --- |
| `session_close` | [[session_close]] | session 종료 정리와 hash-only audit exclude 규칙 설명이 필요 |
| `notion_sync` | [[notion_sync]] | 하루 1회 노션 동기화 범위를 skill 관점에서 고정 |
| `quarantine_sweep` | [[quarantine_sweep]] | invariant 위반 정리 규칙을 독립 skill로 문서화 |

## Non-hook binding
| entrypoint | bound skill draft | reason |
| --- | --- | --- |
| `persist.attach` with `scope=skill` | [[persist_attach]] | skill reference asset 수집 규칙을 별도 문서로 유지 |

## Operational notes
- registry는 Phase 2 메타 초안 목록이지, live `~/.hermes/skills/`의 설치 목록이 아니다
- project relation tag crosswalk는 skill registry가 아니라 [[TAGS]]와 [[notion_datasource_map]]의 exact-match 규칙이 authoritative다
- 추후 upstream checklist가 basename을 명시하면 이 registry를 그 이름으로 맞춘다
