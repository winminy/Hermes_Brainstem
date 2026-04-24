# P7_INBOX — 4단 dedup·graduator

## Phase 목표

인박스 4단 dedup + graduator 구현. 순차 처리 (α 정책), inbox-to-inbox 경로 없음.

## 진입 선행조건

- Phase 6 파이프라인 통과
- P12 converter 전처리와 계약 정의 완료 (경계: converter 출력 = graduator 입력)

## 수용 기준

- [ ]  `inbox/dedup.py` 4단:
    1. **source 멱등성** — 동일 source 해시 존재 시 skip
    2. **frontmatter uuid 충돌** — 기존 파일 존재 시 updated만 갱신
    3. **의미 유사도** — LightRAG query top-K, threshold 초과 시 병합 후보
    4. **사용자 confirm** — 병합 후보는 queue로 보류
- [ ]  `inbox/graduator.py` — 통과 문서를 knowledge/ 하위로 이전, 원본 inbox 파일 제거
- [ ]  `inbox/runner.py` — 순차 처리, 동일 실행에서 병렬 금지
- [ ]  pytest: 4단 각각 + 순차 보장 + inbox-to-inbox 경로 부재

## 교차참조

| 이 Phase | 동시 참조 | 이유 |
| --- | --- | --- |
| P7 ↔ P6 | commit α 정책 | graduator 내부에서 동일 commit 재사용 |
| P7 ↔ P8 | `attach:` prefix source | source 멱등성 규칙 공유 |
| P7 ↔ P12 | converter 전처리 | 이진/노션블록은 converter 통과 후 inbox 진입 |
| P7 → P11 | session_close 훅 | exclude 규칙이 inbox 상태를 본다 |

## SPEC 발췌 대상

[헤르메스 커스텀 메모리 프로바이더 — 전체 사양](https://www.notion.so/be5d21bbad5046bbada8c72195b8c64a?pvs=21)

- §5 인박스 전 범위 (특히 §5-2 4단 dedup)
- §5-3 converter 경계 (γ안)
- §11-15 순차 보장

## IMPL 발췌 대상

[헤르메스 메모리 프로바이더 구현 요청문 — 코드 구현 상세 설계](https://www.notion.so/a3cc456c55fb43689c7a13f4007ee9f4?pvs=21)

- §5 inbox 4단 전 범위
- §10 graduator

## 구현 포인트

- 4단 중 1·2·3은 자동, 4는 사용자 개입. 3·4 사이에 embedding 재계산 금지 (LightRAG query 결과 재사용)
- source 해시는 prefix 구분 (`session:` vs `notion:` vs `attach:` vs `web:` vs `multi:`)
- inbox-to-inbox 경로가 절대 생기지 않도록 graduator는 **볼트 최종 경로까지 이동**한 뒤에만 inbox 파일 제거

## 리포트 템플릿

[7절]