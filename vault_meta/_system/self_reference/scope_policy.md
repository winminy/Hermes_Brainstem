---
uuid: obs:20260423T0942-5
area: knowledge
type: knowledge
tags:
  - PKM
  - 개발
date: 2026-04-23
updated: 2026-04-23
source:
  - multi:phase2-meta-bcd-scope-policy
source_type: ""
file_type: md
---

# scope_policy
- 이 문서는 `persist.attach`의 `scope` 해석 규칙을 정의한다
- ingress 분기는 [[persist_policy]], skill 디렉터리 구조는 [[skill_spec]], skill 목록은 [[skill_registry]]를 따른다

## Scope enum
```yaml
version: 1
scope_enum:
  - knowledge
  - skill
beta_policy:
  skill_scope_status: draft_beta
```

## Scope semantics
| scope | 의미 | 저장 위치 | inbox 경유 | indexing |
| --- | --- | --- | --- | --- |
| `knowledge` | 볼트 정본으로 관리할 첨부 | `<vault>/attachments/YYYY/MM/` + 필요 시 `inbox/` note | 예 | note만 대상 |
| `skill` | 특정 skill의 reference asset | `~/.hermes/skills/{name}/references/` | 아니오 | 아니오 |

## Rules for `scope=knowledge`
- attachment는 vault 관리 자산이다
- raw file은 attachment root로 가고, 장기기억 note가 필요하면 `inbox/` companion note를 만든다
- companion note는 Phase 7 dedup와 graduator의 대상이 된다
- attachment 단독 저장이어도 `source`에는 `attach:` prefix를 남긴다

## Rules for `scope=skill`
- `skill_name`이 명시되어야 한다
- skill root 아래 `references/` 디렉터리에 직접 배치한다
- vault inbox, graduator, LightRAG, session_close audit 대상에서 제외한다
- frontmatter 9필드가 필요한 경우에도 note는 skill scope 내부에만 둔다

## Guardrails
- scope 기본값은 추측하지 않는다. 사용자가 skill 귀속을 명시하지 않으면 `knowledge`로만 해석한다
- registry에 없는 skill name을 임의 생성하지 않는다. 존재 확인이 필요하면 [[skill_registry]]를 먼저 본다
- `scope=skill`은 β 정책이므로, 반복 사용 전 사용자 검수를 우선한다
