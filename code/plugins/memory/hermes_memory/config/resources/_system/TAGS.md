---
uuid: obs:20260423T0835-2
area: knowledge
type: knowledge
tags:
  - PKM
  - 개발
date: 2026-04-23
updated: 2026-04-23
source:
  - multi:phase1-tag-registry-reconstruction
source_type: ""
file_type: md
---

# TAGS
- 이 문서는 Hermes Memory Provider가 허용하는 태그 registry enum의 SSoT다
- 새 태그를 추측으로 추가하지 않는다
- live vault note에 보이는 변형 표기보다 이 문서의 canonical key가 우선한다

## Registry contract
- 실제 태그 값은 아래 `registry[].tag`만 허용한다
- parent는 계층 설명용 메타필드이며, 실제 태그로 쓰지 않는다
- description은 LLM이 태그 의미를 해석할 때 읽는 설명 필드다
- llm_visible이 `true`인 항목만 schema_builder의 enum 설명 입력으로 노출한다

## LLM-visible fields
- `tag`
- `parent`
- `description`

## Registry
```yaml
llm_visible_fields:
  - tag
  - parent
  - description
registry:
  - tag: AI
    parent: topic/technology
    description: 인공지능, 에이전트, LLM, 프롬프트 엔지니어링
    llm_visible: true
  - tag: 개발
    parent: topic/technology
    description: 코딩, 시스템 설계, 인프라, DevOps
    llm_visible: true
  - tag: 건축
    parent: topic/domain
    description: 건축 설계, 시공, 구조, 환경
    llm_visible: true
  - tag: 한양대
    parent: topic/domain
    description: 한양대학교 관련 정보, 학교 시스템
    llm_visible: true
  - tag: 학업
    parent: topic/domain
    description: 수업, 과제, 시험, 학점
    llm_visible: true
  - tag: 자기개발
    parent: topic/life
    description: 습관, 루틴, 성장, 커리어 개발
    llm_visible: true
  - tag: PKM
    parent: topic/knowledge-management
    description: 개인 지식 관리, 노트 전략, 옵시디언, 세컨드 브레인
    llm_visible: true
  - tag: 경제/재무
    parent: topic/life
    description: 투자, 재무, 경제 뉴스, 자산관리
    llm_visible: true
  - tag: 취미
    parent: topic/life
    description: 여가, 관심사, 엔터테인먼트
    llm_visible: true
  - tag: 요리
    parent: topic/life
    description: 레시피, 식재료, 조리법, 식단
    llm_visible: true
  - tag: 인간관계
    parent: topic/persona
    description: 네트워킹, 소셜, 커뮤니케이션
    llm_visible: true
  - tag: 사용자정보
    parent: topic/persona
    description: 사용자의 기본 정보, 성향, 선호, 일상 기록
    llm_visible: true
  - tag: 생활
    parent: topic/life
    description: 일상, 생활 팁, 환경 세팅
    llm_visible: true
  - tag: brainstemV2아키텍쳐수정
    parent: project
    description: BrainStem v2 UX 개선 및 인터페이스 고도화 프로젝트
    llm_visible: true
  - tag: 1차AI-deaChallenge
    parent: project
    description: Hanyang AI-dea 챌린지 프로젝트
    llm_visible: true
  - tag: 3차다이닝
    parent: project
    description: SONDER 소셜 다이닝 파티 3차 프로젝트
    llm_visible: true
  - tag: project
    parent: project
    description: 프로젝트 메인 허브 노트용 공통 태그
    llm_visible: true
```

## Canonicalization notes
- `사용자정보`는 [[notion_datasource_map]]의 User Info DB 매핑에서 required tag로 사용한다
- project relation이 있어도 registry에 없는 새 태그는 생성하지 않는다
- live vault에는 `3차다이닝파티`, `3차 다이닝 파티`처럼 canonical key와 다른 표기가 관찰되지만, Phase 1의 canonical enum은 `3차다이닝`으로 고정한다

## Operational rules
- 신규 태그 제안은 별도 거버넌스 문서를 통해 승인한다
- 한 문서에 복수 태그 부여는 가능하지만, registry 외 값은 허용하지 않는다
- project relation이 있는 Notion row는 registry에 동일 canonical key가 있을 때만 project tag를 붙인다
