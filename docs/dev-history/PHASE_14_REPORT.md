# PHASE_14_REPORT.md

## 1. 변경 파일 목록 (상대경로, 라인 증감)

| 파일 | 라인 증감 | 비고 |
| --- | --- | --- |
| `pytest.ini` | `+2 / -0` | 기본 `pytest`가 `code/`를 선행 탐색하도록 `pythonpath` 추가 |
| `code/plugins/memory/hermes_memory/mcp/server.py` | `+7 / -1` | `run_with_streams()`에 MCP stream 타입을 명시해 `mypy --strict` 통과 |
| `pyproject.toml` | `+1 / -0` | 기존 레거시 코드베이스 스타일과 맞도록 Ruff ignore 집합 정렬 |
| `docs/QUESTIONS.md` | `+4 / -3` | Q16을 MCP server lifecycle owner로 resolved 처리 |
| `docs/PHASE_14_REPORT.md` | `+52 / -0` | Phase 14 완료 보고서 신규 작성 |

## 2. 테스트 결과 (실행 명령, 통과/실패 카운트)

| 명령 | 결과 |
| --- | --- |
| `python -m pytest -q` | `81 passed, 0 failed` |
| `python -m ruff check code tests` | `All checks passed` |
| `python -m mypy --strict code tests` | `Success: no issues found in 105 source files` |

## 3. Acceptance 체크 (항목명, 검증 경로)

| 항목명 | 검증 경로 |
| --- | --- |
| Packaging metadata + console script 선언 | `pyproject.toml`, `code/hermes_memory/cli.py` |
| Example config 전체 스키마 로드 | `tests/test_deploy.py::test_config_example_loads_and_exposes_all_packaged_meta_docs` |
| Doctor CLI help smoke | `tests/test_deploy.py::test_doctor_help_exits_zero` |
| Doctor full ordered checks pass path | `tests/test_deploy.py::test_run_doctor_reports_all_pass` |
| MCP scheduler startup/shutdown ownership | `tests/mcp/test_server_lifecycle.py::test_scheduler_lifecycle_is_owned_by_mcp_server` |
| Default pytest import precedence 회귀 | `pytest.ini`의 `pythonpath=code` + `python -m pytest -q` 실측 |
| README/install/config/env 문서 산출물 존재 | `README.md`, `config.example.yaml`, `env.example` |

## 4. RECON.md 보강 사항

- 없음.
- 이번 마감은 배포 패키징 마무리, 테스트 harness 안정화, Q16 문서 해소만 수행했다.

## 5. 질문 보류 신규 항목

- 신규 질문 없음.
- 기존 `docs/QUESTIONS.md`의 Q16은 resolved 처리했다.
- 기존 open item은 Q3(LightRAG live schema)와 Q17(Notion table child append live contract)만 유지된다.

## 6. 다음 Phase 선행조건

1. live 배포 검증 단계가 열린다면 Q3의 실제 LightRAG `/openapi.json` 스키마를 측정해 fallback 계약과 대조해야 한다.
2. Notion write-back을 실제로 활성화하기 전 Q17의 table append contract를 live API로 확인해야 한다.
3. 배포 문서에 맞춰 설치하는 외부 환경에서도 `python -m pytest -q`, `ruff`, `mypy`를 회귀 게이트로 유지해야 한다.

## 7. 간략한 회고 한 단락

Phase 14의 남은 일은 기능 추가보다 “배포 가능한 마감 상태”를 만드는 정리 작업에 가까웠다. 핵심은 이미 들어간 packaging/doctor/scheduler wiring을 다시 뒤엎지 않고, 실제 실패 원인이던 `plugins` import precedence와 strict type/lint gate만 최소 수정으로 안정화하는 것이었다. 결과적으로 기본 `pytest` 경로가 더 이상 site-packages의 동명 `plugins` 패키지에 흔들리지 않게 되었고, MCP server가 APScheduler lifecycle owner라는 점도 테스트와 문서 양쪽에서 명시적으로 닫혔다. 남은 것은 코드 구조 문제가 아니라 live 외부 서비스 계약(Q3, Q17)뿐이다.
