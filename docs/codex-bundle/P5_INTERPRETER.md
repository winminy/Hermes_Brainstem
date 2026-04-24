# P5_INTERPRETER — 메타 로드·스키마 빌드

## Phase 목표

`_system/` 메타문서를 런타임 로드하여 structured output JSON 스키마를 빌드하고, 훅↔기준 라우팅 테이블을 구성.

## 진입 선행조건

- Phase 1·2 메타문서 전량 검수 통과
- Phase 3 core 유틸, Phase 4 llm 백엔드 통과

## 수용 기준

- [ ]  `interpreter/meta_loader.py` — `_system/` 16종 로드, 캐시, 변경 감지
- [ ]  `interpreter/schema_builder.py` — vault_spec·TAGS → Reduce용 JSON 스키마 빌드 (Anthropic tool_use·OpenAI json_schema 양쪽 호환)
- [ ]  `interpreter/hook_router.py` — `_system/self_reference/hook_registry.md`의 훅↔기준 매핑을 파서·라우터로 변환
- [ ]  메타문서 변경 시 `reload()` API로 캐시 갱신
- [ ]  pytest: 스키마 빌드 결과가 `jsonschema.validate` 통과 + 실제 LLM mock structured output 정상 생성

## 교차참조

| 이 Phase | 동시 참조 | 이유 |
| --- | --- | --- |
| P5 ↔ P1 | vault_spec·TAGS | SSoT 입력 |
| P5 ↔ P2 | hook_registry·scope_policy | 라우팅 규칙 |
| P5 → P6 | schema_builder | Reduce LLM 호출 시 사용 |
| P5 → P11 | hook_router | 자동훅 3종 진입점 |

## SPEC 발췌 대상

[헤르메스 커스텀 메모리 프로바이더 — 전체 사양](https://www.notion.so/SOURCE_DOC_ID?pvs=21)

- §8 메타문서 세트 전 범위
- §4-6 Reduce 출력 스키마

## IMPL 발췌 대상

[헤르메스 메모리 프로바이더 구현 요청문 — 코드 구현 상세 설계](https://www.notion.so/SOURCE_DOC_ID?pvs=21)

- §7 interpreter·schema_builder 전 범위
- §9 LLM 호출 규격

## 구현 포인트

- schema_builder는 **메타문서 → JSON 스키마** 단방향 컴파일. 메타문서가 변하면 재빌드.
- hook_router는 단순 딕셔너리가 아닌 **조건부 라우팅**(DB ID + 유형 + file_type 3튜플) 지원
- 메타문서 로드는 mistune + python-frontmatter 조합. 구조 위반 시 명시적 예외.

## 리포트 템플릿

[7절]