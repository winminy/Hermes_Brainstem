# PHASE_4_REPORT

## 1. 변경 파일 목록
| 상대경로 | 상태 | 라인 증감 |
| --- | --- | --- |
| `code/plugins/memory/hermes_memory/__init__.py` | 갱신 | `+1 / -1` |
| `code/plugins/memory/hermes_memory/config/__init__.py` | 갱신 | `+1 / -1` |
| `code/plugins/memory/hermes_memory/config/settings.py` | 갱신 | `+127 / -11` |
| `code/plugins/memory/hermes_memory/config/layer.py` | 갱신 | `+51 / -0` |
| `code/plugins/memory/hermes_memory/config/resources_loader.py` | 갱신 | `+4 / -0` |
| `code/plugins/memory/hermes_memory/backends/__init__.py` | 신규 | `+59` |
| `code/plugins/memory/hermes_memory/backends/lightrag.py` | 신규 | `+99` |
| `code/plugins/memory/hermes_memory/backends/notion.py` | 신규 | `+396` |
| `code/plugins/memory/hermes_memory/backends/obsidian_writer.py` | 신규 | `+50` |
| `code/plugins/memory/hermes_memory/backends/gdrive_mcp.py` | 신규 | `+50` |
| `code/plugins/memory/hermes_memory/backends/embedding/__init__.py` | 신규 | `+34` |
| `code/plugins/memory/hermes_memory/backends/embedding/api.py` | 신규 | `+64` |
| `code/plugins/memory/hermes_memory/backends/embedding/local.py` | 신규 | `+61` |
| `code/plugins/memory/hermes_memory/backends/llm/__init__.py` | 신규 | `+150` |
| `tests/backends/test_backend_smoke.py` | 신규 | `+29` |
| `tests/backends/test_embedding_backends.py` | 신규 | `+83` |
| `tests/backends/test_notion_backend.py` | 신규 | `+178` |
| `docs/QUESTIONS.md` | 갱신 | `+4 / -5` |
| `docs/PHASE_4_REPORT.md` | 신규 | `+44` |

## 2. 테스트 결과
- 실행 명령:
  - `PYTHONPATH=code python - <<'PY' ... import smoke ... PY`
  - `PYTHONPATH=code uv run --with pytest --with ruff --with mypy --with types-PyYAML --with notion-client --with pydantic --with pydantic-settings --with pyyaml --with openai --with httpx --with filelock --with structlog --with python-frontmatter pytest -q tests`
  - `PYTHONPATH=code uv run --with pytest --with ruff --with mypy --with types-PyYAML --with notion-client --with pydantic --with pydantic-settings --with pyyaml --with openai --with httpx --with filelock --with structlog --with python-frontmatter ruff check code tests`
  - `PYTHONPATH=code uv run --with pytest --with ruff --with mypy --with types-PyYAML --with notion-client --with pydantic --with pydantic-settings --with pyyaml --with openai --with httpx --with filelock --with structlog --with python-frontmatter mypy --strict code/plugins/memory/hermes_memory tests`
- 결과: import smoke 성공, pytest `20 passed`, ruff clean, mypy --strict clean.
- 통과/실패 카운트: `20 / 0`
- Phase 3 수정 사항: `config/settings.py`에 YAML-backed nested settings를 추가했고, `config/layer.py`에 OpenClaw secret 해석(`env > openclaw.json > yaml`)을 추가했으며, `config/resources_loader.py`에 bundled `notion_datasource_map.md` 로더를 보강했다.

## 3. Acceptance 체크
| 항목 | 충족 근거 |
| --- | --- |
| `backends/notion.py` | `NotionBackend`가 notion-client `data_sources.query` 페이징 구조를 감싼 read-only wrapper로 구현되었고, `tests/backends/test_notion_backend.py`가 pagination, secret precedence, datasource map 기반 type/tag/source 변환을 mock으로 검증했다 |
| `notion_datasource_map.md` 반영 read 로직 | `NotionBackend.datasources` + `_page_to_vault_entry()`가 bundled datasource map의 include/exclude/rules를 해석하고 project relation exact-match tag만 부여한다 |
| `backends/embedding/*` | `EmbeddingBackend` protocol, `APIEmbeddingBackend`, `LocalEmbeddingBackend`, `build_embedding_backend()`가 구현되었고 `tests/backends/test_embedding_backends.py`가 api/local 선택과 doctor-friendly optional dependency 경로를 검증했다 |
| `config embedding.backend` 런타임 선택 | `HermesMemorySettings.embedding.backend`와 `build_embedding_backend()`가 `api | local` 선택을 담당한다 |
| `backends/lightrag.py` | `LightRAGHTTPBackend`가 query/upsert/delete 인터페이스와 embedding backend 주입 구조를 제공한다. query는 기본 `/query`, upsert/delete는 RECON openapi 공백 때문에 config path 주입형으로 남겼다 |
| `backends/obsidian_writer.py` | fs + advanced-uri 선택 지원, `filelock` 경유 write 경로 구현 |
| `backends/llm/__init__.py` | OpenAI json_schema / Anthropic tool_use 공통 인터페이스(`StructuredLLMBackend`) 제공 |
| `backends/gdrive_mcp.py` | persist.attach 전용 subprocess MCP wrapper 구현 |
| 재시도 정책 | `backends/__init__.py`의 `RetryPolicy` + `run_with_retry()`가 동일 방식 2회 + 대체 방식 2회 구조를 제공한다 |
| backend 테스트 | `tests/backends/` 신규 3개 파일 + import smoke로 mock 기반 검증 완료 |

## 4. RECON.md 보강 사항
- Notion은 MCP가 아니라 notion-client SDK 직접 호출 구조로 고정했다.
- secret precedence는 `env > <runtime-root>/.openclaw/openclaw.json > yaml`로 `ConfigLayer.resolve_secret()`에 반영했다.
- LightRAG query path는 기존 `/query` 사용 흔적을 따르되, upsert/delete path는 live openapi 부재로 config 주입형으로 남겨 RECON 불확실성을 코드 레벨에서 드러냈다.

## 5. 질문 보류 신규 항목
- 신규 질문 없음.
- 기존 Q3(LightRAG live schema 미확정)는 여전히 남아 있다.
- Q12는 `Resolved (N/A)`로 종료했다.

## 6. 다음 Phase 선행조건
- Phase 5는 `StructuredLLMBackend`와 `NotionBackend.read_vault_entries()` 산출 dict를 실제 interpreter/schema 경로에 연결하면 된다.
- LightRAG live OpenAPI가 확보되면 `lightrag.upsert_path/delete_path` 기본값과 payload shape를 실측값으로 좁혀야 한다.
- Obsidian writer와 GDrive MCP는 Phase 5+에서 실제 orchestration에 연결하기 전 config example/env example 정비가 필요하다.

## 7. 간략한 회고
Phase 4는 아직 실환경 API 호출 없이도 이후 phase가 바로 소비할 수 있는 adapter 표면을 닫는 작업이었다. 핵심은 bundled meta 문서와 Phase 3 ConfigLayer를 재사용해, Notion datasource map·secret precedence·embedding backend 선택을 코드화한 점이다. 반대로 LightRAG openapi 부재처럼 RECON이 비어 있는 지점은 억지 하드코딩 대신 config 주입형/명시적 제한으로 남겨 두어, 부모 검증과 후속 phase에서 안전하게 좁힐 수 있게 했다.
