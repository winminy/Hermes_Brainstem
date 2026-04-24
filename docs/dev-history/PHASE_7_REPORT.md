# PHASE_7_REPORT

## 1. 변경 파일 목록
| 상대경로 | 라인 증감 | 비고 |
| --- | --- | --- |
| `code/plugins/memory/hermes_memory/pipeline/persist_process.py` | `+1 / -1` | `ReducedEntry` 타입 import 누락 보정으로 `ruff`/`mypy --strict` 복구 |
| `tests/inbox/test_runner.py` | `+34 / -2` | mypy 호환 annotation 2건 보정 + `inbox-to-inbox` 경로 부재 검증 테스트 추가 |
| `docs/QUESTIONS.md` | `+6 / -0` | merge-confirm queue consumer contract 신규 질문 추가 |
| `docs/PHASE_7_REPORT.md` | `신규` | Phase 7 결과 보고서 작성 |

## 2. 테스트 결과
- 실행 명령:
  - `PYTHONPATH=code uv run --with pytest --with pydantic --with pydantic-settings --with pyyaml --with jsonschema --with filelock --with httpx --with openai --with anthropic --with notion-client --with python-frontmatter --with mistune pytest -q tests/inbox/test_runner.py`
  - `PYTHONPATH=code uv run --with pytest --with pydantic --with pydantic-settings --with pyyaml --with jsonschema --with filelock --with httpx --with openai --with anthropic --with notion-client --with python-frontmatter --with mistune pytest -q tests`
  - `PYTHONPATH=code uv run --with ruff ruff check code tests`
  - `PYTHONPATH=code uv run --with mypy --with types-PyYAML --with pytest --with pydantic --with pydantic-settings --with pyyaml --with jsonschema --with filelock --with httpx --with openai --with anthropic --with notion-client --with python-frontmatter --with mistune mypy --strict code/plugins/memory/hermes_memory tests`
- 결과:
  - inbox targeted pytest: `9 passed`
  - 전체 pytest: `40 passed`
  - `ruff check`: clean
  - `mypy --strict`: clean
- 통과/실패 카운트: `40 / 0`
- 기존 코드 보정 사항:
  - Phase 7 inbox 프로덕션 코드는 수용 기준상 이미 구현돼 있었고, 추가 기능 구현은 필요하지 않았다.
  - 대신 검증 단계에서 기존 Phase 6 파이프라인에 `ReducedEntry` import 누락이 있어 `ruff`/`mypy --strict`가 실패하던 문제를 보정했다.
  - `tests/inbox/test_runner.py`의 Notion write-back recording helper 2곳은 `dict` invariance 때문에 mypy가 실패하던 상태여서 명시적 annotation으로 정리했다.
  - 수용 기준 문구에 있는 `inbox-to-inbox 경로 부재`는 기존 테스트에서 직접 증명하지 않아 전용 테스트를 추가했다.

## 3. Acceptance 체크
| 항목명 | 검증 경로 |
| --- | --- |
| 1단 source 멱등성 — 동일 source 해시 skip | `tests/inbox/test_runner.py::test_source_idempotency_skips_duplicate_inbox_entry` |
| 2단 uuid 충돌 — 기존 파일 `updated`만 갱신 | `tests/inbox/test_runner.py::test_uuid_collision_only_updates_updated_field` |
| 3단 의미 유사도 — threshold 초과 후보 탐지 | `tests/inbox/test_runner.py::test_similarity_candidates_are_queued_and_note_stays_in_inbox` |
| 4단 사용자 confirm — merge queue 보류 | `tests/inbox/test_runner.py::test_similarity_candidates_are_queued_and_note_stays_in_inbox` |
| graduator — `knowledge/` 이동 후 inbox 원본 제거 | `tests/inbox/test_runner.py::test_happy_path_graduates_to_knowledge_and_upserts_lightrag` |
| ambiguous 시 inbox 유지 + reason tag 기록 | `tests/inbox/test_runner.py::test_ambiguous_classification_stays_in_inbox_with_reason_tag` |
| 규격 미달 시 quarantine 이동 | `tests/inbox/test_runner.py::test_invalid_classification_moves_note_to_quarantine` |
| runner 순차 처리 보장 | `tests/inbox/test_runner.py::test_runner_processes_entries_sequentially` |
| inbox-to-inbox 경로 부재 | `tests/inbox/test_runner.py::test_inbox_similarity_candidates_do_not_create_inbox_to_inbox_path` |
| Notion single-entry 경로 재사용 회귀 없음 | `tests/inbox/test_runner.py::test_process_notion_page_delegates_to_pipeline_and_writes_back` |

## 4. RECON.md 보강 사항
- 신규 RECON 보강 없음.
- 기존 확정사항(볼트 note area=`knowledge/`,`inbox/`; quarantine=`<vault_root>/_quarantine/`; live 외부 서비스 direct call 금지)만 사용했다.

## 5. 질문 보류 신규 항목
- `docs/QUESTIONS.md`에 **13. Inbox merge-confirm queue consumer contract**를 추가했다.
- 현재 구현은 `inbox/.hermes-inbox-merge-queue.jsonl`를 사용하지만, 이후 Phase에서 이 queue를 어떤 UI/훅/메타아티팩트가 소비할지 SSoT 확인이 필요하다.

## 6. 다음 Phase 선행조건
- merge-confirm queue의 authoritative consumer contract를 확정해야 Phase 7의 4단 confirm 보류가 후속 자동화와 충돌하지 않는다.
- Phase 8 이후 작업은 수행하지 않았으므로 attach 계층은 현재 queue artifact와 별개로 설계 검토가 필요하다.
- inbox dedup/graduator 경로는 현재 acceptance를 충족하므로 후속 phase에서는 이 경로의 source-idempotency/invariant 보존을 깨지 않는 통합만 허용해야 한다.

## 7. 간략한 회고
이번 Phase에서는 inbox 모듈 본체를 먼저 재검토했고, 예상과 달리 4단 dedup·graduator·순차 runner 구현 자체는 이미 수용 기준에 근접해 있었다. 실제 누락은 “검증 관점”에 있었다. 전체 품질 게이트를 돌리자 Phase 6 파이프라인의 타입 import 누락과 테스트 헬퍼의 mypy 불일치가 드러났고, 또한 수용 기준의 `inbox-to-inbox 경로 부재`가 전용 테스트로는 증명되지 않고 있었다. 그래서 기능 추가를 무리하게 늘리지 않고, 기존 동작을 유지한 채 검증 실패 원인만 보정하고 acceptance를 직접 증명하는 테스트와 문서를 보강하는 방식으로 Phase 7을 마감했다.
