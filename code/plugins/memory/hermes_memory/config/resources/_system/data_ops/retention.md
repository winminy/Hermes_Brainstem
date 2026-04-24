---
uuid: obs:20260423T0942-2
area: knowledge
type: knowledge
tags:
  - PKM
  - 개발
date: 2026-04-23
updated: 2026-04-23
source:
  - multi:phase2-meta-bcd-retention
source_type: ""
file_type: md
---

# retention
- 이 문서는 provider가 만드는 note, attachment, skill reference, quarantine artifact, audit hash의 보관 원칙을 정의한다
- 원문 비저장 원칙은 [[vault_spec]], ingress 분기는 [[persist_policy]], hook별 해시 사용은 [[hook_registry]]를 따른다

## Retention classes
```yaml
version: 1
retention:
  vault_note:
    scope: inbox/ and knowledge/
    retention: until_explicit_delete_or_user_curated_change
    raw_conversation_allowed: false
  vault_attachment:
    scope: attachments/YYYY/MM/
    retention: until_parent_note_or_user_action_removes_it
    raw_conversation_allowed: false
  skill_reference:
    scope: ~/.hermes/skills/{name}/references/
    retention: until_skill_owner_removes_it
    raw_conversation_allowed: false
  quarantine_artifact:
    scope: <vault>/_quarantine/YYYY-MM/
    retention: until_operator_resolves_or_removes_it
    raw_conversation_allowed: false
  audit_hash:
    scope: operational logs and idempotency records
    retention: lifecycle_bound_only
    raw_conversation_allowed: false
```

## Audit hash policy
- 감사 로그에는 평문 대화, 평문 본문, 바이너리 원본을 저장하지 않는다
- 감사 단위는 `sha256` 해시와 최소 운영 메타데이터만 허용한다
- 해시 대상은 source string, file identifier, session-close idempotency key처럼 재실행 방지에 필요한 최소 문자열만 사용한다
- `scope=skill` 첨부는 [[hook_registry]]의 `session_close` 감사 대상에서 제외한다
- 동일 source 판정은 prefix를 포함한 전체 문자열 기준이다. `session:`과 `attach:`는 서로 다른 source로 간주한다

## Lifecycle rules
- `inbox/` note는 장기 보존 대상이 아니며, [[persist_policy]]와 Phase 7 graduator에 따라 `knowledge/`로 졸업하거나 폐기된다
- `knowledge/` note는 사용자가 정본으로 간주하므로 자동 만료하지 않는다
- vault attachment는 parent note 또는 명시적 정리 작업이 제거를 결정한다. provider가 독자적으로 TTL 삭제하지 않는다
- skill reference는 skill 운영 자산이므로 provider의 자동 정리 대상이 아니다
- quarantine artifact는 해결 전까지 read-only 보존을 우선한다

## Idempotency retention
- source dedup용 해시는 대응 note 또는 quarantine artifact가 존재하는 동안 유지한다
- `session_close` idempotency 해시는 동일 세션의 중복 정리 방지 목적이 사라질 때까지 유지한다
- 정확한 물리 저장소와 prune 구현은 Phase 3 이후 코드 단계에서 정해지더라도, 평문 비저장과 hash-only 원칙은 바뀌지 않는다

## Operational notes
- retention의 기본 단위는 “시간 기반 자동 삭제”가 아니라 “artifact lifecycle”이다
- 사용자 요청 없는 자동 purge는 note와 attachment 정본에 적용하지 않는다
- hash retention이 필요 이상 길어져도 raw content 저장으로 확장해서는 안 된다
