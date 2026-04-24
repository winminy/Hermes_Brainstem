---
uuid: obs:20260423T0942-3
area: knowledge
type: knowledge
tags:
  - PKM
  - 개발
date: 2026-04-23
updated: 2026-04-23
source:
  - multi:phase2-meta-bcd-binary-policy
source_type: ""
file_type: md
---

# binary_policy
- 이 문서는 바이너리의 저장 위치, note 동반 규칙, 임베딩 금지 원칙을 정의한다
- 확장자 해석은 [[file_policy]], scope 분기는 [[scope_policy]], 볼트 경로 규격은 [[vault_spec]]를 따른다

## Core rules
- 이미지와 일반 바이너리는 본문 frontmatter나 markdown 본문 안에 raw payload로 넣지 않는다
- binary는 LightRAG 임베딩 대상이 아니다
- `scope=knowledge` binary는 항상 `<vault>/attachments/YYYY/MM/` 아래에 raw 파일을 둔다
- `scope=skill` binary는 항상 `~/.hermes/skills/{name}/references/` 아래에 raw 파일을 둔다
- binary가 장기 기억 본문과 함께 저장되어야 할 때만 동반 note를 별도로 만든다

## Binary classes
```yaml
version: 1
classes:
  document_binary:
    file_types: [pdf, ppt, pptx, docx, hwp]
    vault_path: attachments/YYYY/MM/
    skill_path: ~/.hermes/skills/{name}/references/
    embedding: prohibited
  image_binary:
    file_types: [png, jpg, svg]
    vault_path: attachments/YYYY/MM/
    skill_path: ~/.hermes/skills/{name}/references/
    embedding: prohibited
```

## Companion note rules
- 동반 note는 `file_type`에 원본 확장자를 기록하고, raw binary 경로를 본문에서 참조한다
- 이미지의 경우 본문 참조는 `![[파일명.ext]]`를 우선 사용한다
- 문서형 binary는 raw 파일 링크와 함께 요약 note를 둘 수 있으나, raw binary 자체를 markdown으로 재인코딩하지 않는다
- 동반 note가 없더라도 raw binary 배치 자체는 유효하다

## Path policy
| scope | raw binary path | inbox 경유 | indexing |
| --- | --- | --- | --- |
| `knowledge` | `<vault>/attachments/YYYY/MM/` | companion note가 필요할 때만 `inbox/` note 생성 | raw binary는 비임베딩 |
| `skill` | `~/.hermes/skills/{name}/references/` | 아니오 | raw binary는 비임베딩 |

## Operational notes
- `persist.attach scope=knowledge`는 raw binary를 attachment root에 놓고, 필요 시 companion note를 normal path처럼 `inbox/`로 보낸다
- `persist.attach scope=skill`는 Reduce와 graduator를 건너뛰며, skill reference asset로만 관리한다
- attachment 경로의 연/월 폴더는 저장 시점 기준으로 계산한다
- 실제 볼트에는 직접 쓰지 않고, 본 문서는 작업 폴더 초안으로만 유지한다
