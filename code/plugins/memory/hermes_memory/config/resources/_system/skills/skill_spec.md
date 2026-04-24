---
uuid: obs:20260423T0942-8
area: knowledge
type: knowledge
tags:
  - PKM
  - 개발
date: 2026-04-23
updated: 2026-04-23
source:
  - multi:phase2-meta-bcd-skill-spec
source_type: ""
file_type: md
---

# skill_spec
- 이 문서는 Hermes skill 디렉터리 구조와 `references/` 규약을 정의한다
- scope 분기는 [[scope_policy]], 기본 스킬 초안은 [[skill_registry]]를 따른다

## Observed live structure
- 실측 skill root: `~/.hermes/skills/`
- 실측 skill 수: 24개 (`SKILL.md` 기준)
- 공통 필수 파일: `SKILL.md`
- 선택 하위 디렉터리 실측: `references/` 7개 skill, `assets/` 4개 skill, `scripts/` 4개 skill, `templates/` 4개 skill, `rules/` 1개 skill

## Canonical layout
```yaml
version: 1
skill_root: ~/.hermes/skills/
skill_layout:
  required:
    - SKILL.md
  optional:
    - references/
    - assets/
    - scripts/
    - templates/
    - rules/
references_contract:
  path: ~/.hermes/skills/{name}/references/
  managed_by: persist.attach with scope=skill
  indexing: disabled
```

## References rules
- `references/`는 skill이 직접 소비하는 raw asset 또는 markdown reference note 저장소다
- `scope=skill` 첨부만 `references/`에 쓸 수 있다
- `references/` 자산은 vault `inbox/`, `knowledge/`, `attachments/`와 혼용하지 않는다
- raw binary와 markdown reference note가 함께 있어도 모두 skill 소유 자산으로 취급한다

## SKILL.md expectations
- skill metadata note는 skill 이름, 설명, 사용 조건을 담아야 한다
- provider는 skill 내용을 수정하지 않고, `references/` 배치 규칙만 해석한다
- Phase 2의 기본 스킬 초안은 실제 `SKILL.md` 템플릿이 아니라 작업 폴더의 Hermes 에이전트 시스템 config 번들 초안(`vault_meta/_system/skills/default/*.md`)으로 유지한다

## Guardrails
- provider는 실제 `~/.hermes/skills/`에 직접 쓰지 않는다
- skill name은 폴더 basename 기준이며, registry에 없는 이름을 추측으로 추가하지 않는다
- `scope=skill` 자산은 vault 검색·graduation·LightRAG 인덱싱 대상이 아니다
