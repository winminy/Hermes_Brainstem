# PHASE_10_REPORT.md

## 1. 변경 파일 목록 (상대경로, 라인 증감)

| 파일 | 라인 증감 | 비고 |
| --- | --- | --- |
| `code/plugins/memory/hermes_memory/mcp/services.py` | `+1 / -1` | `PersistAttachPipeline` 참조를 `attach` 패키지로 바로 정정해 import/cycle 문제 해소 |
| `code/plugins/memory/hermes_memory/mcp/errors.py` | `+4 / -4` | MCP error helpers를 `NoReturn`로 지정해 strict type narrowing 복구 |
| `code/plugins/memory/hermes_memory/mcp/schema_loader.py` | `+4 / -1` | schema JSON object 타입 검증 추가 |
| `code/plugins/memory/hermes_memory/mcp/tools/search.py` | `+12 / -2` | `tag_match_mode` literal 검증 helper 및 strict typing 보강 |
| `code/plugins/memory/hermes_memory/mcp/tools/sync.py` | `+7 / -1` | `SyncEntryResult` 기반 payload typing 정리 |
| `tests/mcp/test_server.py` | `+24 / -2` | MCP fake backend/test DI typing 보강 |
| `tests/search/test_search.py` | `+52 / -0` | `tag_match_mode=all/any` 직접 검색 회귀 테스트 추가 |
| `docs/QUESTIONS.md` | `+3 / -2` | Q15 resolved 처리 |
| `code/plugins/memory/hermes_memory/inbox/classifier.py` | `+1 / -1` | `jsonschema` typed import 정리 |
| `code/plugins/memory/hermes_memory/interpreter/notion_sync.py` | `+1 / -1` | `jsonschema` typed import 정리 |
| `code/plugins/memory/hermes_memory/pipeline/reduce.py` | `+1 / -1` | `jsonschema` typed import 정리 |
| `tests/interpreter/test_schema_builder.py` | `+1 / -1` | `jsonschema` typed import 정리 |
| `docs/PHASE_10_REPORT.md` | `+53 / -0` | Phase 10 완료 보고서 신규 작성 |

## 2. 테스트 결과 (실행 명령, 통과/실패 카운트)

| 명령 | 결과 |
| --- | --- |
| `PYTHONPATH=code uv run --with pytest --with pydantic --with pydantic-settings --with PyYAML --with filelock --with httpx --with notion-client --with openai --with anthropic --with jsonschema --with python-frontmatter --with structlog --with mcp --with anyio python -m pytest -q` | `55 passed, 0 failed` |
| `PYTHONPATH=code uv run --with ruff ruff check code tests` | `All checks passed` |
| `PYTHONPATH=code uv run --with mypy --with pytest --with types-PyYAML --with types-jsonschema --with pydantic --with pydantic-settings --with PyYAML --with filelock --with httpx --with notion-client --with openai --with anthropic --with jsonschema --with python-frontmatter --with structlog --with mcp --with anyio mypy --strict code tests` | `Success: no issues found in 83 source files` |

- 실제 전체 검증을 마지막 수정 이후 재실행해 모두 green 확인.
- 외부 API 호출이나 MCP 서버 실기동은 수행하지 않았고, in-memory/session test만 사용했다.

## 3. Acceptance 체크 (항목명, 검증 경로)

| 항목명 | 검증 경로 |
| --- | --- |
| `mcp/services.py` import 오류 해소 | `code/plugins/memory/hermes_memory/mcp/services.py`, `tests/mcp/test_server.py` |
| MCP server tool listing/call roundtrip 정상화 | `tests/mcp/test_server.py::test_mcp_roundtrip_lists_tools_and_calls_search_sync_inbox_status` |
| invalid params가 JSON-RPC/MCP error object로 반환 | `tests/mcp/test_server.py::test_mcp_invalid_params_return_jsonrpc_error_object` |
| search tags filter 기본 `all` + 선택적 `any` semantics 유지 | `code/plugins/memory/hermes_memory/search/direct_file.py`, `code/plugins/memory/hermes_memory/mcp/tools/search.py`, `docs/QUESTIONS.md` |
| `tag_match_mode(all/any)` 회귀 테스트 보강 | `tests/search/test_search.py::test_direct_file_search_supports_tag_match_mode_all_and_any` |
| strict typing gate 복구 | `code/plugins/memory/hermes_memory/mcp/errors.py`, `code/plugins/memory/hermes_memory/mcp/schema_loader.py`, `code/plugins/memory/hermes_memory/mcp/tools/{search,sync}.py` |

## 4. RECON.md 보강 사항

- 없음.
- 이번 Phase는 저장소 내부 구현/테스트만 수정했고 live MCP transport, live Notion, live LightRAG endpoint 실측은 추가하지 않았다.

## 5. 질문 보류 신규 항목

- 없음.
- `docs/QUESTIONS.md`의 Q15는 resolved 처리했고, 이번 수정 범위에서 새 미해결 사항은 발생하지 않았다.

## 6. 다음 Phase 선행조건

1. 실제 상위 Hermes 런타임에서 stdio MCP entrypoint wiring만 연결하면 된다.
2. attach 관련 MCP tool이 Phase 11 이후 범위에 포함될 경우, 현재 `HermesMemoryServices.attach_pipeline` lazy property를 그대로 재사용하면 된다.
3. live runtime smoke test가 필요하면 in-memory MCP tests와 별도로 transport-level integration만 추가하면 된다.

## 7. 간략한 회고 한 단락

Phase 10의 핵심 blocker는 기능 부족보다 import 경계와 strict typing 누수였다. `PersistAttachPipeline`를 `pipeline` 집합 export에 억지로 포함시키는 대신, 실제 소유 모듈인 `attach`에서 직접 참조하도록 되돌리는 편이 가장 작은 수정으로 import/cycle 문제를 끝내는 방법이었다. 그 다음으로 MCP helper들이 `NoReturn`/literal/type-narrowing을 충분히 제공하지 않아 `mypy --strict`가 연쇄적으로 깨졌는데, 이를 얇게 정리하니 서버/툴/테스트 전체가 큰 구조 변경 없이 안정화됐다. 결과적으로 Q15를 resolved 처리하면서 search tag semantics도 문서와 구현이 다시 일치하게 됐다.
