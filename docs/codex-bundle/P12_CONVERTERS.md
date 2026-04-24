# P12_CONVERTERS — notion_block·conversation_binary (γ안)

## Phase 목표

입력 자료 변환기 구현: 노션 블록·바이너리·대화 로그 → 파이프라인 진입 경로. γ안: converter 전처리 경계 고정.

## 진입 선행조건

- Phase 3 core.uuid_gen·core.frontmatter, Phase 6 파이프라인 진입점 확정

## 수용 기준

- [ ]  `converters/notion_block.py` — 노션 블록 JSON → 옵시디언 마크다운 + frontmatter 9필드
- [ ]  `converters/conversation_binary.py` — 세션 대화 → .md + 첨부 바이너리 분리
- [ ]  `converters/common.py` — frontmatter 생성, uuid, source prefix 규칙
- [ ]  converter 출력은 **inbox 파일 또는 attach 경로** 중 하나로만 진입
- [ ]  pytest: 노션 block 샘플 (fixtures/notion_row_sample.json) + 세션 샘플 (fixtures/conversation_sample.json)

## 교차참조

| 이 Phase | 동시 참조 | 이유 |
| --- | --- | --- |
| P12 ↔ P7 | inbox 진입 | converter 출력 = inbox 입력 계약 |
| P12 ↔ P2 | binary_policy | 바이너리 분리 규칙 |

## SPEC 발췌 대상

[헤르메스 커스텀 메모리 프로바이더 — 전체 사양](https://www.notion.so/be5d21bbad5046bbada8c72195b8c64a?pvs=21)

- §5-3 converter 경계 (γ안)
- §4-0 converter 전처리

## IMPL 발췌 대상

[헤르메스 메모리 프로바이더 구현 요청문 — 코드 구현 상세 설계](https://www.notion.so/a3cc456c55fb43689c7a13f4007ee9f4?pvs=21)

- §15 converter 전 범위
- §15-B 대화 바이너리 처리 세부
- §4-0 converter 위치 (파이프라인 선행)

## 구현 포인트

- 옵시디언 문법 규칙 엄격 준수 (SPEC §11-12): `###` → `-`, **인용구 블록 금지**, `![[파일]]`, `[[노트명]]`
- 대화 binary는 session 내 첨부만 추출, 원문 대화 비저장 (원칙 2)
- converter 하나당 **단일 출력 경로** 보장 (inbox·attach 동시 배출 금지)

## 리포트 템플릿

[7절]