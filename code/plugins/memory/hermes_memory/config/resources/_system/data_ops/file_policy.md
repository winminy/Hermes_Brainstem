---
uuid: obs:20260423T0942-1
area: knowledge
type: knowledge
tags:
  - PKM
  - 개발
date: 2026-04-23
updated: 2026-04-23
source:
  - multi:phase2-meta-bcd-file-policy
source_type: ""
file_type: md
---

# file_policy
- 이 문서는 [[vault_spec]]의 `file_type` 해석, 확장자별 저장 경로, converter 진입 조건의 SSoT다
- binary 저장 규칙은 [[binary_policy]], ingress 분기 규칙은 [[persist_policy]], 노션 자동 수집 범위는 [[notion_datasource_map]]를 따른다

## Canonical rules
- `file_type` 값은 원본 확장자의 소문자 문자열이며 점(`.`)을 포함하지 않는다
- provider가 직접 관리하는 본문 노트의 기본값은 `md`다
- `source_type: notion` 자동 변환 문서는 항상 `file_type: md`를 사용한다
- `source_type: gdrive` 또는 `source prefix = attach:` 경로의 원본 바이너리는 원본 확장자를 그대로 `file_type`에 기록한다
- 아래 registry 밖의 새 확장자는 추측으로 추가하지 않고, 원본 파일은 raw 보존하되 정책 확장은 별도 승인으로 처리한다

## Managed file_type registry
```yaml
version: 1
canonical_file_types:
  - md
  - pdf
  - ppt
  - pptx
  - docx
  - hwp
  - png
  - jpg
  - svg
routing:
  md:
    class: note
    default_path: inbox/ or knowledge/
    converter: none
    indexing: vault_as_source_of_truth
    notes:
      - frontmatter 9필드 필수
      - notion 자동 변환 기본형
  pdf:
    class: binary
    default_path: attachments/YYYY/MM/
    converter: companion_note_optional; raw file preserved
    indexing: no_binary_embedding
  ppt:
    class: binary
    default_path: attachments/YYYY/MM/
    converter: companion_note_optional; raw file preserved
    indexing: no_binary_embedding
  pptx:
    class: binary
    default_path: attachments/YYYY/MM/
    converter: companion_note_optional; raw file preserved
    indexing: no_binary_embedding
  docx:
    class: binary
    default_path: attachments/YYYY/MM/
    converter: companion_note_optional; raw file preserved
    indexing: no_binary_embedding
  hwp:
    class: binary
    default_path: attachments/YYYY/MM/
    converter: companion_note_optional; raw file preserved
    indexing: no_binary_embedding
  png:
    class: binary_image
    default_path: attachments/YYYY/MM/
    converter: companion_note_optional; raw file preserved
    indexing: no_binary_embedding
  jpg:
    class: binary_image
    default_path: attachments/YYYY/MM/
    converter: companion_note_optional; raw file preserved
    indexing: no_binary_embedding
  svg:
    class: binary_image
    default_path: attachments/YYYY/MM/
    converter: companion_note_optional; raw file preserved
    indexing: no_binary_embedding
```

## Path and converter matrix
| file_type | 저장 주체 | scope=knowledge | scope=skill | converter 메모 |
| --- | --- | --- | --- | --- |
| `md` | provider note | `inbox/` 경유 후 `knowledge/` 졸업 | 허용하지 않음 | 이미 마크다운이므로 추가 변환 없음 |
| `pdf`, `ppt`, `pptx`, `docx`, `hwp` | raw binary | `attachments/YYYY/MM/` + 필요 시 동반 note | `~/.hermes/skills/{name}/references/` 직접 배치 | raw 보존이 우선이며, 본문 note가 필요할 때만 별도 markdown 생성 |
| `png`, `jpg`, `svg` | raw image | `attachments/YYYY/MM/` + 필요 시 동반 note | `~/.hermes/skills/{name}/references/` 직접 배치 | 이미지도 바이너리로 취급하며 임베딩 대상이 아니다 |

## Operational notes
- `persist.process`는 `md`만 생성한다. binary는 [[binary_policy]]에 따라 raw 파일 경로를 먼저 확정한다
- `persist.attach`는 source prefix를 `attach:`로 기록하고, scope에 따라 vault attachment 또는 skill references로 직접 라우팅한다
- Phase 1 기준 볼트 실측 frontmatter `file_type`는 전부 `md`였다. binary registry는 legacy system-config backup 문서의 확장자 근거와 Phase 2 정책 초안으로 유지한다
- Project relation 태그 부여는 파일 형식과 무관하며, [[TAGS]]와 [[notion_datasource_map]]의 exact-match 규칙만 따른다
