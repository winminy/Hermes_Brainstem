# PHASE_11_REPORT.md

## 1. 변경 파일 목록 (상대경로, 라인 증감)

| 파일 | 라인 증감 | 비고 |
| --- | --- | --- |
| `code/plugins/memory/hermes_memory/hooks/__init__.py` | `+13 / -0` | Hook package export 추가 |
| `code/plugins/memory/hermes_memory/hooks/common.py` | `+173 / -0` | flat kwargs parsing, hash-only audit/JSONL helpers, file-id hash exclude helper |
| `code/plugins/memory/hermes_memory/hooks/session_close.py` | `+205 / -0` | session_close orchestration, queue consumer, inbox review, hash-only audit |
| `code/plugins/memory/hermes_memory/hooks/notion_sync.py` | `+57 / -0` | daily_auto datasource incremental sync hook |
| `code/plugins/memory/hermes_memory/hooks/quarantine_sweep.py` | `+170 / -0` | invalid note quarantine sweep + audit |
| `code/plugins/memory/hermes_memory/hooks/scheduler.py` | `+108 / -0` | APScheduler registration only, tz-aware, no start |
| `code/plugins/memory/hermes_memory/inbox/runner.py` | `+77 / -0` | `review_existing_entry()` 추가로 existing inbox note 재분류/승격 위임 |
| `code/plugins/memory/hermes_memory/backends/notion.py` | `+4 / -0` | datasource `scan_mode` 파싱 노출 |
| `tests/hooks/test_session_close.py` | `+161 / -0` | session_close sync+queue consumer+hash exclude 시나리오 |
| `tests/hooks/test_hook_notion_sync.py` | `+132 / -0` | notion_sync incremental datasource selection + scheduler registration |
| `tests/hooks/test_quarantine_sweep.py` | `+77 / -0` | invalid/expired-style entry quarantine sweep 시나리오 |
| `docs/QUESTIONS.md` | `+8 / -3` | Q13 resolved, Q16 신규 추가 |
| `docs/PHASE_11_REPORT.md` | `+57 / -0` | Phase 11 보고서 신규 작성 |

## 2. 테스트 결과 (실행 명령, 통과/실패 카운트)

| 명령 | 결과 |
| --- | --- |
| `PYTHONPATH=code uv run --with pytest --with pydantic --with pydantic-settings --with PyYAML --with filelock --with httpx --with notion-client --with openai --with anthropic --with jsonschema --with python-frontmatter --with structlog --with mcp --with anyio --with apscheduler python -m pytest -q` | `59 passed, 0 failed` |
| `PYTHONPATH=code uv run --with ruff ruff check code tests` | `All checks passed` |
| `PYTHONPATH=code uv run --with mypy --with pytest --with types-PyYAML --with types-jsonschema --with pydantic --with pydantic-settings --with PyYAML --with filelock --with httpx --with notion-client --with openai --with anthropic --with jsonschema --with python-frontmatter --with structlog --with mcp --with anyio --with apscheduler mypy --strict code tests` | `Success: no issues found in 92 source files` |

- Phase 3~10 interface 수정 사항: `InboxRunner.review_existing_entry()`와 `NotionDatasourceSpec.scan_mode`를 추가했다.
- 둘 다 Phase 11 hook orchestration을 위한 확장이고 기존 ingress path(`ingest`, pipeline sync)는 유지된다.

## 3. Acceptance 체크 (항목명, 검증 경로)

| 항목명 | 검증 경로 |
| --- | --- |
| flat kwargs hook signature 유지 | `code/plugins/memory/hermes_memory/hooks/common.py`, `code/plugins/memory/hermes_memory/hooks/{session_close,notion_sync,quarantine_sweep}.py` |
| `session_close`가 inbox 상태 정리 + merge-confirm queue consumer 수행 | `code/plugins/memory/hermes_memory/hooks/session_close.py`, `code/plugins/memory/hermes_memory/inbox/runner.py`, `tests/hooks/test_session_close.py::test_session_close_runs_incremental_sync_and_consumes_merge_queue` |
| `skill_attach` file-id hash exclude 적용 | `code/plugins/memory/hermes_memory/hooks/common.py::collect_non_skill_file_hashes`, `tests/hooks/test_session_close.py` |
| `notion_sync`가 daily_auto datasource만 incremental pipeline 진입 | `code/plugins/memory/hermes_memory/hooks/notion_sync.py`, `code/plugins/memory/hermes_memory/backends/notion.py`, `tests/hooks/test_hook_notion_sync.py::test_notion_sync_uses_incremental_pipeline_for_daily_datasources` |
| `quarantine_sweep`가 invalid note를 `_quarantine/YYYY-MM/`로 이동 | `code/plugins/memory/hermes_memory/hooks/quarantine_sweep.py`, `tests/hooks/test_quarantine_sweep.py::test_quarantine_sweep_moves_invalid_entry_into_quarantine_bucket` |
| APScheduler 등록만 수행하고 실제 기동하지 않음 | `code/plugins/memory/hermes_memory/hooks/scheduler.py`, `tests/hooks/test_hook_notion_sync.py::test_scheduler_registers_tz_aware_jobs_without_starting` |
| `pipeline/inline_llm.py` 미생성 유지 | repository tree inspection, `code/plugins/memory/hermes_memory/pipeline/` |
| Q13 resolved 처리 | `docs/QUESTIONS.md` Q13 |

## 4. RECON.md 보강 사항

- 없음.
- 이번 Phase는 저장소 내부 hook orchestration만 추가했고 live runtime wiring이나 외부 scheduler host discovery는 하지 않았다.

## 5. 질문 보류 신규 항목

- Q16 추가: APScheduler 실제 start/stop lifecycle의 상위 소유자 미확정.
- 실제 scheduler host가 확정되면 Phase 14 배포 래퍼 또는 상위 bootstrap에서 `build_scheduler()`를 연결하면 된다.

## 6. 다음 Phase 선행조건

1. 상위 Hermes 런타임이 hook entrypoint와 scheduler lifecycle ownership을 결정해야 한다.
2. live Notion/LightRAG endpoint smoke test가 필요하면 현재 mock-based hook tests 위에 integration layer만 추가하면 된다.
3. queue consumer UI/ack가 필요하면 `inbox/.hermes-inbox-merge-queue.jsonl` 위에 표시 계층만 얹으면 된다.

## 7. 간략한 회고 한 단락

Phase 11의 핵심은 새 hook 파일을 만드는 것보다 기존 Phase 6~10 컴포넌트를 다시 조합해 문서 규칙을 깨지 않는 orchestration 계층을 세우는 일이었다. `session_close`는 raw conversation을 저장하지 않고도 hash-only audit와 merge-confirm queue draining을 수행해야 했고, 이를 위해 inbox existing-entry review 경로를 얇게 추가하는 편이 가장 작은 변경으로 Q13을 닫는 방법이었다. `notion_sync`는 이미 존재하던 incremental pipeline을 재사용하면서 datasource `scan_mode`만 노출하면 됐고, `quarantine_sweep`는 Search 기반 읽기 검증과 경로 이동을 결합해 frontmatter 9-field 닫힌 스키마를 유지했다. 스케줄러는 APScheduler 등록까지만 구현해 문서 제약(실기동 금지)도 지켰다.
