# P6_PIPELINE — Map-Reduce·dispatcher·commit

## Phase 목표

엔드-투-엔드 파이프라인 구현: source 입력 → Map(조각화·태깅) → Reduce(LLM structured output으로 9필드 생성) → dispatcher(저장 경로 결정) → commit(파일 쓰기·LightRAG 인덱싱).

## 진입 선행조건

- Phase 3·4·5 통과

## 수용 기준

- [ ]  `pipeline/map.py` — source → chunk + tag 후보 (LLM 미사용; 규칙 기반)
- [ ]  `pipeline/reduce.py` — chunks → frontmatter 9필드 + 본문, LLM structured output, `jsonschema.validate` 재검증
- [ ]  `pipeline/dispatcher.py` — SPEC §4에 따라 저장 경로 결정
- [ ]  `pipeline/commit.py` — α 정책(graduator → LightRAG 순서), filelock, 원자적 쓰기
- [ ]  `pipeline/persist_process.py` — persist.process tool 진입점
- [ ]  `pipeline/inline_llm.py` **생성 금지** (자동훅 사전 요약 금지)
- [ ]  pytest: 전 단계 mock 조합 + 실제 LLM 1회 골든 테스트

## 교차참조

| 이 Phase | 동시 참조 | 이유 |
| --- | --- | --- |
| P6 ↔ P2 | binary_policy·retention | dispatcher 분기 조건 |
| P6 ↔ P5 | schema_builder | Reduce 스키마 입력 |
| P6 → P7 | commit α 정책 | inbox graduator가 동일 커밋 경로 재사용 |
| P6 → P8 | dispatcher scope=skill 분기 | persist.attach 공유 |
| P6 → P12 | converter → map 진입 | notion_block·binary 파이프라인 진입점 |

## SPEC 발췌 대상

[헤르메스 커스텀 메모리 프로바이더 — 전체 사양](https://www.notion.so/SOURCE_DOC_ID?pvs=21)

- §4 end-to-end 전 범위
- §4-6 Reduce 출력 스키마
- §11-6 α 정책

## IMPL 발췌 대상

[헤르메스 메모리 프로바이더 구현 요청문 — 코드 구현 상세 설계](https://www.notion.so/SOURCE_DOC_ID?pvs=21)

- §4 단계 0–10
- §8 dispatcher
- §9 LLM 호출 규격

## 구현 포인트

- Reduce는 structured output **1회 호출** + `jsonschema.validate` 재검증 + invariant_guard 거침
- commit의 α 정책: 볼트 쓰기 성공 후에만 LightRAG upsert. LightRAG 실패는 재시도 큐로.
- dispatcher는 `_system/self_reference/persist_policy.md` 규칙을 해석하여 분기 (하드코딩 금지)

## 리포트 템플릿

[7절]