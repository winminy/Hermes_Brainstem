# PHASE_13_REPORT.md

## 1. 변경 파일 목록 (상대경로, 라인 증감)

| 파일 | 라인 증감 | 비고 |
| --- | --- | --- |
| `code/plugins/memory/hermes_memory/inbox/runner.py` | `+7 / -0` | `InboxRunner.run()`에 병렬 실행 거부 lock 추가 |
| `pytest.ini` | `+4 / -0` | `e2e`, `acceptance` marker 등록 |
| `tests/e2e/test_phase13_e2e.py` | `+706 / -0` | 필수 7개 E2E 통합 시나리오 추가 |
| `tests/acceptance/test_phase13_acceptance.py` | `+221 / -0` | 계약 위반 acceptance 테스트 추가 |
| `docs/PHASE_13_REPORT.md` | `+64 / -0` | Phase 13 보고서 신규 작성 |

## 2. 테스트 결과 (실행 명령, 통과/실패 카운트)

| 명령 | 결과 |
| --- | --- |
| `PYTHONPATH=code uv run --with pytest --with pydantic --with pydantic-settings --with PyYAML --with filelock --with httpx --with notion-client --with openai --with anthropic --with jsonschema --with python-frontmatter --with structlog --with mcp --with anyio --with apscheduler python -m pytest -q` | `77 passed, 0 failed` |
| `PYTHONPATH=code uv run --with pytest --with pydantic --with pydantic-settings --with PyYAML --with filelock --with httpx --with notion-client --with openai --with anthropic --with jsonschema --with python-frontmatter --with structlog --with mcp --with anyio --with apscheduler python -m pytest -q -m e2e` | `7 passed, 70 deselected, 0 failed` |
| `PYTHONPATH=code uv run --with pytest --with pydantic --with pydantic-settings --with PyYAML --with filelock --with httpx --with notion-client --with openai --with anthropic --with jsonschema --with python-frontmatter --with structlog --with mcp --with anyio --with apscheduler python -m pytest -q -m acceptance` | `3 passed, 74 deselected, 0 failed` |
| `PYTHONPATH=code uv run --with ruff ruff check code tests` | `All checks passed` |
| `PYTHONPATH=code uv run --with mypy --with pytest --with types-PyYAML --with types-jsonschema --with pydantic --with pydantic-settings --with PyYAML --with filelock --with httpx --with notion-client --with openai --with anthropic --with jsonschema --with python-frontmatter --with structlog --with mcp --with anyio --with apscheduler mypy --strict code tests` | `Success: no issues found in 101 source files` |
| `PYTHONPATH=code uv run --with coverage --with pytest --with pydantic --with pydantic-settings --with PyYAML --with filelock --with httpx --with notion-client --with openai --with anthropic --with jsonschema --with python-frontmatter --with structlog --with mcp --with anyio --with apscheduler python -m coverage run -m pytest -q && PYTHONPATH=code uv run --with coverage coverage report` | `77 passed, TOTAL 85% coverage` |
| `PYTHONPATH=code uv run --with pytest --with pytest-cov --with pydantic --with pydantic-settings --with PyYAML --with filelock --with httpx --with notion-client --with openai --with anthropic --with jsonschema --with python-frontmatter --with structlog --with mcp --with anyio --with apscheduler pytest -q tests --cov=code/plugins/memory/hermes_memory --cov-report=term-missing:skip-covered` | `77 passed, scoped package coverage TOTAL 81%` |

- coverage 수치는 측정 범위에 따라 다르다. `coverage run -m pytest` 전체 측정은 85%, `pytest-cov --cov=code/plugins/memory/hermes_memory`의 패키지 한정 측정은 81%였다.
- 통합 검증 중 수정된 버그/인터페이스 정렬:
  - `InboxRunner.run()`은 기존에 병렬 호출을 거부하지 않았고 순차 처리 불변식 위반 시도가 그대로 통과할 수 있었다. Phase 13에서 non-blocking lock을 추가해 동일 runner의 병렬 inbox batch 실행을 `RuntimeError`로 거부하도록 정렬했다.
  - `pytest -m e2e`, `pytest -m acceptance` 선택 실행을 위해 marker 선언을 `pytest.ini`에 추가했다.

## 3. Acceptance 체크 (항목명, 검증 경로)

| 항목명 | 검증 경로 |
| --- | --- |
| E2E (1) Full sync happy path | `tests/e2e/test_phase13_e2e.py::test_e2e_full_sync_happy_path` |
| E2E (2) Incremental sync + attach + sha256 dedup | `tests/e2e/test_phase13_e2e.py::test_e2e_incremental_sync_attach_and_sha256_dedup` |
| E2E (3) Inbox flow + session_close merge-confirm | `tests/e2e/test_phase13_e2e.py::test_e2e_inbox_flow_and_session_close_merge_confirm` |
| E2E (4) Search round-trip via MCP with semantic + fallback + filters | `tests/e2e/test_phase13_e2e.py::test_e2e_search_round_trip_via_mcp_with_semantic_fallback_and_filters` |
| E2E (5) Quarantine path + quarantine_sweep | `tests/e2e/test_phase13_e2e.py::test_e2e_quarantine_path_and_quarantine_sweep` |
| E2E (6) Converter fidelity | `tests/e2e/test_phase13_e2e.py::test_e2e_converter_fidelity` |
| E2E (7) Error resilience where one entry fails and others succeed | `tests/e2e/test_phase13_e2e.py::test_e2e_error_resilience_one_entry_fails_and_others_succeed` |
| Acceptance marker selection | `pytest -q -m e2e`, `pytest -q -m acceptance` 실행 결과 |
| 계약 위반: immutable frontmatter 변경 시도 거부 | `tests/acceptance/test_phase13_acceptance.py::test_acceptance_rejects_frontmatter_mutation` |
| 계약 위반: MCP schema 불일치 input 거부 | `tests/acceptance/test_phase13_acceptance.py::test_acceptance_rejects_non_schema_mcp_input` |
| 계약 위반: 병렬 inbox 처리 시도 거부 | `tests/acceptance/test_phase13_acceptance.py::test_acceptance_rejects_parallel_inbox_processing_attempt` |
| 전체 회귀(unit+e2e+acceptance) | `python -m pytest -q` |

## 4. RECON.md 보강 사항

- 없음.
- 이번 Phase는 저장소 내부 E2E/acceptance 검증과 마지막 인터페이스 정렬만 수행했으며, live external service 측정이나 vault_meta 변경은 하지 않았다.

## 5. 질문 보류 신규 항목

- 신규 질문 없음.
- `docs/QUESTIONS.md`는 하단 추가 없이 유지했다.

## 6. 다음 Phase 선행조건

1. Phase 14에서는 이미 검증된 mock 체인을 실제 배포 bootstrap/doctor 경로에 연결하되, 이번 Phase의 `pytest -m e2e`, `pytest -m acceptance`를 회귀 게이트로 유지해야 한다.
2. 실제 external service 연동을 열 경우에도 LightRAG fallback, mock-safe 테스트 경로, quarantine 경로 기반 신호를 깨지 않도록 contract test를 유지해야 한다.
3. `InboxRunner.run()`의 병렬 거부 규칙을 상위 런타임이 우회하지 않도록 orchestration 레이어에서도 단일 batch 실행 모델을 유지해야 한다.

## 7. 간략한 회고 한 단락

Phase 13은 기능 추가보다 “전체 체인이 실제로 이어지는지”를 증명하는 단계였다. 그래서 Notion sync, attach, inbox graduation, session close queue consumption, MCP search fallback, quarantine sweep, converter fidelity, partial failure tolerance를 각각 따로가 아니라 저장소 상태 그대로 묶어 검증하는 데 집중했다. 그 과정에서 눈에 띈 마지막 불일치는 `InboxRunner.run()`의 병렬 거부 부재였고, 이를 런타임에서 바로 차단하도록 보정해 acceptance 요구와 불변 원칙 15를 맞췄다. 결과적으로 mock-only 환경에서 Phase 3~12 모듈 체인이 Phase 13 기준으로 전부 통과하는 마지막 회귀 스냅샷을 만들었다.
