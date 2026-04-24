---
uuid: obs:20260423T0942-11
area: knowledge
type: knowledge
tags:
  - PKM
  - 개발
date: 2026-04-23
updated: 2026-04-23
source:
  - multi:phase2-meta-bcd-default-skill-notion-sync
source_type: ""
file_type: md
---

# notion_sync
- 상태: provisional default skill draft
- 역할: 하루 1회 노션 datasource 스캔과 `persist.process` 진입 범위를 설명하는 메타 스킬
- authoritative datasource 범위는 [[notion_datasource_map]]를 따른다

## Responsibilities
- Sub-task DB는 `유형 ∈ {메모/ 리소스, Project Backlogs}`인 row만 수집
- User Info DB는 전체 row를 수집
- Project relation tag는 [[TAGS]] registry exact-match일 때만 부여
- GDrive는 notion_sync 범위에서 제외한다

## Inputs and outputs
- 입력: scheduler trigger, last edited cursor, datasource map
- 출력: eligible row batch, `persist.process` ingress request
- 금지: 미등재 DB 스캔, relation title 기반 신규 tag 생성
