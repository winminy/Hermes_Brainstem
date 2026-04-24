# vault_meta_drafts/ — 메타문서 16종 완성형 초안

<aside>
📁

[Hermes Memory Provider — 필요 메타문서 체크리스트](https://www.notion.so/Hermes-Memory-Provider-aaf29ba05b504304bfa52059bf20d0dc?pvs=21)의 16종 체크리스트를 그대로 완성형 파일로 작성. 프롬프트에 임베드하지 않고 **경로 지시 + "읽고 보강"** 환경으로 Codex에 전달.

</aside>

## 구성 16종

### A. 엔트리 (3종) — Phase 1 대상

- `vault_spec.md`
- `TAGS.md`
- `notion_datasource_map.md`

### B. data_ops (3종) — Phase 2 대상

- `data_ops/file_policy.md`
- `data_ops/retention.md`
- `data_ops/binary_policy.md`

### C. self_reference (4종) — Phase 2 대상

- `self_reference/persist_policy.md`
- `self_reference/scope_policy.md`
- `self_reference/hook_registry.md`
- `self_reference/quarantine_policy.md`

### D. skills (6종) — Phase 2 대상

- `skills/skill_spec.md`
- `skills/skill_registry.md`
- `skills/default/*.md` (기본 스킬 4종 초안)

## 파일 작성 대상 경로

`~/Desktop/hermes-memory-provider/vault_meta/_system/`

(검수 통과 후 실제 볼트 `<vault>/_system/`으로 이관)

## 작성 규칙

- 모두 **완성형** (프로바이더 로드 직후 동작 가능한 수준)
- 옵시디언 문법만 (SPEC §11-12)
- frontmatter 9필드 생략 금지 — 시스템 파일도 frontmatter 존재
- 상호 참조는 `[[노트명]]` 위키링크로

## 투입 패턴

Codex 세션에 본 폴더는 **가상 경로**로 명시하고, 구체적인 파일 내용은 [Hermes Memory Provider — 필요 메타문서 체크리스트](https://www.notion.so/Hermes-Memory-Provider-aaf29ba05b504304bfa52059bf20d0dc?pvs=21) 체크리스트 항목을 직접 첨부

## 참조되는 Phase

- P1 A 3종 작성
- P2 B·C·D 13종 작성
- P5 meta_loader가 본 폴더 구조를 대상으로 로드