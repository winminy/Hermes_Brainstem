---
uuid: obs:20260423T0942-4
area: knowledge
type: knowledge
tags:
  - PKM
  - 개발
date: 2026-04-23
updated: 2026-04-23
source:
  - multi:phase2-meta-bcd-persist-policy
source_type: ""
file_type: md
---

# persist_policy
- 이 문서는 `persist.process`와 `persist.attach`의 분기 기준을 정의한다
- scope 상세는 [[scope_policy]], 파일 형식은 [[file_policy]], binary 저장은 [[binary_policy]], 노션 자동 범위는 [[notion_datasource_map]]를 따른다

## Entry decision
```yaml
version: 1
entrypoints:
  persist.process:
    intent: long_term_note_creation
    default_output: markdown note
    default_path: inbox/
    allowed_sources: [session, notion, web, multi]
  persist.attach:
    intent: explicit_user_attachment_placement
    default_output: raw attachment or skill reference
    allowed_scopes: [knowledge, skill]
    source_prefix: attach:
```

## Branch matrix
| entrypoint | 주 사용 상황 | 기본 산출물 | 저장 경로 | 후속 처리 |
| --- | --- | --- | --- | --- |
| `persist.process` | 대화·노션·웹에서 장기기억 note 생성 | `md` note | `inbox/` | Phase 7 dedup + graduator |
| `persist.attach` + `scope=knowledge` | 사용자가 파일 자체를 볼트에 보존하라고 명시 | raw attachment + 필요 시 companion note | `attachments/YYYY/MM/` + `inbox/` | note가 있을 때만 graduator |
| `persist.attach` + `scope=skill` | 사용자가 특정 skill의 reference asset로 첨부를 요청 | raw file 또는 raw md | `~/.hermes/skills/{name}/references/` | Reduce, graduator, vault indexing 제외 |

## Rules for persist.process
- 자동 저장의 기본 경로는 `inbox/` 단일이다
- Notion 자동 변환은 [[notion_datasource_map]]에 등재된 DB와 include 조건만 허용한다
- GDrive는 자동 변환 대상이 아니며 `persist.attach`에서만 다룬다
- 출력 note는 항상 frontmatter 9필드를 충족해야 한다

## Rules for persist.attach
- 호출 주체는 사용자의 명시적 첨부 요청이어야 한다
- `scope=knowledge`는 볼트 관리 자산으로 취급하고, `scope=skill`는 skill 운영 자산으로 취급한다
- binary는 scope에 맞는 raw 경로에 먼저 저장한다
- `scope=skill`는 vault의 `inbox/`와 `knowledge/`를 전혀 거치지 않는다
- attach 완료 후에는 사용자에게 실제 저장 경로를 반환해야 한다

## Non-negotiable exclusions
- `persist.process`가 `knowledge/`에 직접 쓰는 경로는 없다
- `persist.attach scope=skill`는 `attachments/YYYY/MM/`를 사용하지 않는다
- raw conversation transcript는 어느 경로로도 저장하지 않는다
- registry에 없는 새 tag나 type을 분기 조건에 추가하지 않는다
