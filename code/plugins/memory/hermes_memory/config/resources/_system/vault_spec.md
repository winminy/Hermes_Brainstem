---
uuid: obs:20260423T0835-1
area: knowledge
type: knowledge
tags:
  - PKM
  - 개발
date: 2026-04-23
updated: 2026-04-23
source:
  - multi:phase1-meta-reconstruction
source_type: ""
file_type: md
---

# vault_spec
- 이 문서는 Hermes Memory Provider가 해석하는 볼트 규격의 SSoT다
- 태그 해석은 [[TAGS]], 노션 소스 매핑은 [[notion_datasource_map]]를 따른다

## Vault constants
- vault_root: `<configured vault.root>`
- provider_managed_note_roots: `knowledge/`, `inbox/`
- provider_managed_attachment_root: `attachments/YYYY/MM/`
- provider_managed_quarantine_root: `<vault_root>/_quarantine/YYYY-MM/`
- Hermes agent system config bundle은 live vault 구조와 분리되어 배포된다

## Vault layout
- live vault의 provider-managed note area는 `knowledge/`와 `inbox/` 두 영역만 존재한다
- provider는 본문 note를 위 두 영역 밖에 만들지 않는다
- attachment는 `attachments/YYYY/MM/`, quarantine artifact는 `<vault_root>/_quarantine/YYYY-MM/`를 사용한다

## Frontmatter 9-field schema
| field | rule | notes |
| --- | --- | --- |
| `uuid` | string, pattern `^obs:[0-9]{8}T[0-9]{4}(-[0-9]+)?$` | 생성 후 불변 |
| `area` | enum `knowledge`, `inbox` | live vault note area는 두 값만 허용 |
| `type` | enum `person`, `knowledge`, `tool`, `schedule`, `preference`, `project`, `memo` | 정확히 7종만 허용 |
| `tags` | array of registry tags from [[TAGS]] | 미등록 태그 금지 |
| `date` | string, pattern `YYYY-MM-DD` | 생성 후 불변 |
| `updated` | string, pattern `YYYY-MM-DD` | 마지막 갱신일 |
| `source` | array of string with prefix `notion:`, `web:`, `session:`, `attach:`, `multi:` | 생성 후 불변 |
| `source_type` | enum `notion`, `gdrive`, `""` | 대화 유래는 빈 문자열 |
| `file_type` | string | 기본값은 `md`, 첨부 동반 문서는 원본 확장자 소문자 사용 |

## Type semantics
- `person`: 사람 자체의 프로필, 기본 정보, 관계 정보
- `knowledge`: 비교적 안정화된 설명형 지식
- `tool`: 도구 자체의 사용법, 운용 지식, 레퍼런스 메모
- `schedule`: 날짜나 마감이 핵심인 일정 기록
- `preference`: 성향, 취향, 작업 습관, 말투, 프로토콜 선호
- `project`: 프로젝트 허브, 프로젝트 개요, 프로젝트 단위 상태
- `memo`: 메모, 아이디어, 백로그, 리소스성 기록의 기본형

## Invariants
- `uuid`, `date`, `source`는 생성 후 수정하지 않는다
- `area`는 `knowledge` 또는 `inbox`만 허용한다
- 원문 대화 평문은 저장하지 않는다
- 바이너리는 frontmatter 본문에 직접 넣지 않고 `attachments/YYYY/MM/`에 두고 본문에서 참조한다
- source 멱등성 판정은 prefix 포함 문자열 전체를 기준으로 한다

## Markdown and Obsidian syntax
- 헤더 깊이는 `#`, `##`까지만 사용한다
- H3 이하의 세부 구획이 필요하면 헤더 대신 `-` 목록으로 표현한다
- 인용구 블록은 사용하지 않는다
- 내부 링크는 `[[노트명]]`을 사용한다
- 첨부 임베드는 `![[파일명.ext]]`를 사용한다
- 위키링크 대상은 파일 basename 기준이다
- 본문은 옵시디언 네이티브 마크다운만 사용하고, 규칙을 설명하기 위한 경우 외에는 HTML 의존을 피한다

## Save and naming rules
- provider가 생성하는 본문 노트는 `knowledge/` 또는 `inbox/`에만 놓는다
- 파일명은 위키링크 가능한 사람이 읽을 수 있는 제목을 유지한다
- 동일 basename 충돌 시 numeric suffix를 붙인다
- 첨부는 원본 확장자를 유지하고, 본문 노트에서 `![[파일]]`로 참조한다

## Source-specific notes
- Notion 유래 문서는 `source_type: notion`, `file_type: md`를 기본값으로 한다
- GDrive 유래 문서는 `source_type: gdrive`이며, 원본 확장자를 `file_type`에 기록한다
- 대화/수기 저장 문서는 `source_type: ""`, `file_type: md`를 사용한다

## Cross references
- 태그 enum과 의미는 [[TAGS]]를 따른다
- 노션 DB별 수집 조건과 type 매핑은 [[notion_datasource_map]]를 따른다
