---
uuid: obs:20260423T0835-3
area: knowledge
type: knowledge
tags:
  - PKM
  - 개발
date: 2026-04-23
updated: 2026-04-23
source:
  - multi:phase1-notion-datasource-reconstruction
source_type: ""
file_type: md
---

# notion_datasource_map
- 이 문서는 live evidence로 확인된 Notion datasource만 기록한다
- 확인되지 않은 URL, enum, DB title은 추측하지 않는다
- frontmatter 규격은 [[vault_spec]], 태그 registry는 [[TAGS]]를 따른다

## Machine-readable map
```yaml
version: 1
references:
  vault_spec: [[vault_spec]]
  tags: [[TAGS]]
datasources:
  - name: Sub-task DB
    kind: notion_database
    db_id: ${SUB_TASK_DB_ID}
    db_url: https://www.notion.so/${SUB_TASK_DB_ID}
    evidence:
      - live_notion_search_query: Sub-task
      - live_database_meta_title: Sub-task
      - core_policy: daily_auto_only_when_유형_in_[메모/_리소스,_Project_Backlogs]
    scan_mode: daily_auto
    include_when:
      property: 유형
      in:
        - 메모/ 리소스
        - Project Backlogs
    exclude_when:
      property: 유형
      in:
        - to do (일정)
        - 하위 수행사항
        - 휴지통
        - inbox
        - 회의록
    mapping:
      area: knowledge
      source_prefix: "notion:"
      source_type: notion
      file_type: md
      rules:
        - when:
            유형: 메모/ 리소스
          type: memo
          required_tags: []
          optional_tags:
            - project_relation_registry_match_only
        - when:
            유형: Project Backlogs
          type: memo
          required_tags: []
          optional_tags:
            - project_relation_registry_match_only
  - name: User Info DB
    kind: notion_database
    db_id: ${USER_INFO_DB_ID}
    db_url: https://www.notion.so/${USER_INFO_DB_ID}
    evidence:
      - live_notion_search_query: User Info
      - live_database_meta_title: User Info
      - live_database_property: 유형
    scan_mode: daily_auto
    include_when:
      all_rows: true
    mapping:
      area: knowledge
      source_prefix: "notion:"
      source_type: notion
      file_type: md
      rules:
        - when:
            유형_in:
              - 기본 정보
              - 인간관계
              - 성격
          type: person
          required_tags:
            - 사용자정보
        - when:
            유형_in:
              - 선호분야
              - 프로토콜 발동 습관
              - 스케줄링 습관
              - 작업 스타일
              - 질문스타일
              - 말투
              - 프롬포트 설계
          type: preference
          required_tags:
            - 사용자정보
```

## Notes
- `project_relation_registry_match_only`는 Sub-task row의 `프로젝트` relation title이 [[TAGS]]의 canonical project tag와 정확히 일치할 때만 태그를 부여한다는 뜻이다
- 현재 live Project DB title은 TAGS registry보다 넓어서, 미일치 relation title은 태그를 새로 만들지 않고 무태그로 둔다
