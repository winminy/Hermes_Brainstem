# P3_CORE — core 유틸

## Phase 목표

`core/` 하위 공용 유틸 구현. uuid 생성, frontmatter 파서/라이터, invariant_guard, wikilink suggester, 해시·시계·로깅.

## 진입 선행조건

- Phase 2 메타문서 B·C·D 사용자 검수 통과
- vault_[spec.md](http://spec.md) frontmatter 9필드 정의 확정

## 수용 기준

- [ ]  `core/uuid_gen.py` — `obs:YYYYMMDDTHHMM[-N]` 생성, 분 해상도 충돌 시 `-N` 접미사
- [ ]  `core/frontmatter.py` — python-frontmatter 래퍼, 9필드 dump/load, 순서 보존
- [ ]  `core/invariant_guard.py` — `uuid`·`date`·`source` 변경 시도 시 런타임 거부
- [ ]  `core/wikilink.py` — `suggest_links()` LightRAG 후보 호출, 파일당 최대 2개, LLM 미사용
- [ ]  `core/hasher.py` — sha256, 감사 로그 전용
- [ ]  `core/clock.py` — tz-aware, 테스트용 주입 가능
- [ ]  `core/logger.py` — structlog 설정, `print` 금지
- [ ]  pytest: 각 모듈 단위 테스트 통과

## 교차참조

| 이 Phase | 동시 참조 | 이유 |
| --- | --- | --- |
| P3 ↔ P1 | vault_spec 9필드 | 파서 규격 SSoT |
| P3 → P5 | frontmatter·invariant_guard | schema_builder가 직접 사용 |
| P3 → P6 | uuid_gen·hasher | Reduce·commit 단계 |
| P3 → P9 | wikilink.suggest_links | search 후보 생성 |
| P3 → P12 | uuid_gen·frontmatter | converter가 9필드 채움 |

## SPEC 발췌 대상

[헤르메스 커스텀 메모리 프로바이더 — 전체 사양](https://www.notion.so/SOURCE_DOC_ID?pvs=21)

- §11 불변 원칙 (특히 4·13)
- §13 frontmatter

## IMPL 발췌 대상

[헤르메스 메모리 프로바이더 구현 요청문 — 코드 구현 상세 설계](https://www.notion.so/SOURCE_DOC_ID?pvs=21)

- §16 core/ 전체
- §4-4 9필드 강제 경로

## 구현 포인트

- invariant_guard는 dict diff 기반이 아닌 **쓰기 경로 래핑**으로 차단 (commit 직전 hook)
- wikilink.suggest_links는 LightRAG query 결과 top-K를 점수·type 기반 필터 → LLM 호출 없이 결정
- uuid_gen 분 해상도 충돌 테스트: 동일 분에 5회 생성 → `-1`…`-4` 접미

## 리포트 템플릿

[7절]