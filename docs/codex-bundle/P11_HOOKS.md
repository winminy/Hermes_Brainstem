# P11_HOOKS — 자동훅 3종·APScheduler

## Phase 목표

자동훅 3종 (`session_close`, `notion_sync`, `quarantine_sweep`) + APScheduler 스케쥴링. LLM 사전 요약 금지.

## 진입 선행조건

- Phase 5 hook_router, Phase 4 notion_mcp·gdrive_mcp 통과
- IMPL §21 미결 hook point 11건 Phase 진입 시점에 확정

## 수용 기준

- [ ]  Hook signature (전체 공통): 평탄 kwargs (`session_id`, `conversation_history`, `model`, `platform`, ...) — RECON 확정. 중첩 `session.*` 경로 폐기.
- [ ]  `hooks/session_close.py` — 세션 종료 시 inbox 상태 정리, `skill_attach` exclude 규칙 적용 (file_id 해시 기준)
- [ ]  `hooks/notion_sync.py` — 하루 1회, 지정 DB(Sub-task·User Info) 스캔 → pipeline/persist_process 진입
- [ ]  `hooks/quarantine_sweep.py` — invariant 위반 문서 일괄 격리 영역 이동
- [ ]  `hooks/scheduler.py` — APScheduler 등록, tz-aware
- [ ]  **`pipeline/inline_llm.py` 생성 금지** 재확인
- [ ]  pytest: 각 훅 mock + 스케쥴라 등록·실행 검증

## 교차참조

| 이 Phase | 동시 참조 | 이유 | P11 ↔ P5 | hook_router | 진입점 랜딩 |
| --- | --- | --- | --- | --- | --- |
| P11 ↔ P7 | inbox 상태 | session_close의 exclude 규칙 | P11 ↔ P8 | skill_attach audit | file_id 해시 제외 |
| P11 ↔ P4 | notion_mcp·gdrive_mcp | notion_sync 실제 호출 | P11 ↔ P1 | notion_datasource_map | 변환 대상 범위 |

## SPEC 발췌 대상

[헤르메스 커스텀 메모리 프로바이더 — 전체 사양](https://www.notion.so/SOURCE_DOC_ID?pvs=21)

- §3-1 자동훅 3종
- §11-10 하루 1회 정책
- §11-14 자동훅 LLM 사전 요약 금지

## IMPL 발췌 대상

[헤르메스 메모리 프로바이더 구현 요청문 — 코드 구현 상세 설계](https://www.notion.so/SOURCE_DOC_ID?pvs=21)

- §13 자동훅 전 범위
- §13-1 session_close exclude
- §13-2 notion_sync 스케쥴
- §3 트리거 맵

## 구현 포인트

- notion_sync는 변경된 row만 감지하도로 diff 기반 (last_edited_time 혜리스틱)
- session_close는 **별개 런타임**에서 실행될 수 있으므로 idempotent 보장
- quarantine_sweep은 격리 영역 파일을 읽기 전용 디렉터리(`<vault>/_quarantine/YYYY-MM/`)으로 이동

## 리포트 템플릿

[7절]