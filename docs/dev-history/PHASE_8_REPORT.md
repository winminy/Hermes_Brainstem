# PHASE_8_REPORT

## 1. 변경 파일 목록
| 상대경로 | 라인 증감 | 비고 |
| --- | --- | --- |
| `code/plugins/memory/hermes_memory/attach/__init__.py` | `신규` | attach 패키지 export 추가 |
| `code/plugins/memory/hermes_memory/attach/downloader.py` | `신규` | mock-only 다운로드 인터페이스 추가 |
| `code/plugins/memory/hermes_memory/attach/models.py` | `신규` | attach 결과/소스 dataclass 추가 |
| `code/plugins/memory/hermes_memory/attach/notion.py` | `신규` | Notion page property + block attachment extractor 추가 |
| `code/plugins/memory/hermes_memory/attach/pipeline.py` | `신규` | persist.attach 본체, scope 분기, companion note, hash dedup 구현 |
| `code/plugins/memory/hermes_memory/pipeline/persist_attach.py` | `신규` | P8 acceptance 경로용 thin wrapper 추가 |
| `code/plugins/memory/hermes_memory/config/settings.py` | `수정` | `skills_root` 설정 추가 |
| `code/plugins/memory/hermes_memory/config/resources_loader.py` | `수정` | attachment root template 파싱 추가 |
| `code/plugins/memory/hermes_memory/config/layer.py` | `수정` | `attachment_bucket()` / `skill_root()` helper 추가 |
| `code/plugins/memory/hermes_memory/backends/notion.py` | `수정` | `retrieve_page()` / `list_block_children()` 공개 메서드 추가 |
| `tests/attach/test_persist_attach.py` | `신규` | scope 2종 × markdown/binary 매트릭스 + dedup + Notion load 경로 검증 |
| `docs/QUESTIONS.md` | `+6 / -0` | skill-scope frontmatter `area` canonical value 질문 추가 |
| `docs/PHASE_8_REPORT.md` | `신규` | Phase 8 결과 보고서 작성 |

## 2. 테스트 결과
- 실행 명령:
  - `PYTHONPATH=code uv run --with pytest --with pydantic --with pydantic-settings --with pyyaml --with jsonschema --with filelock --with httpx --with openai --with anthropic --with notion-client --with python-frontmatter --with mistune pytest -q tests/attach/test_persist_attach.py`
  - `PYTHONPATH=code uv run --with pytest --with pydantic --with pydantic-settings --with pyyaml --with jsonschema --with filelock --with httpx --with openai --with anthropic --with notion-client --with python-frontmatter --with mistune pytest -q tests`
  - `PYTHONPATH=code uv run --with ruff ruff check code tests`
  - `PYTHONPATH=code uv run --with mypy --with types-PyYAML --with pytest --with pydantic --with pydantic-settings --with pyyaml --with jsonschema --with filelock --with httpx --with openai --with anthropic --with notion-client --with python-frontmatter --with mistune mypy --strict code/plugins/memory/hermes_memory tests`
- 결과:
  - attach targeted pytest: `8 passed`
  - 전체 pytest: `48 passed`
  - `ruff check`: clean
  - `mypy --strict`: clean
- 통과/실패 카운트: `48 / 0`
- 이전 Phase 인터페이스 변경 사항:
  - `HermesMemorySettings`에 `skills_root`를 추가해 skill references 경로를 설정 주입으로 해결했다.
  - `ConfigLayer`에 `attachment_bucket()`과 `skill_root()` helper를 추가해 P8 경로 계산을 config 계층으로 이동했다.
  - `ResourceLoader/VaultSpecContract`는 `provider_managed_attachment_root`를 런타임 파싱하도록 확장했다.
  - `NotionBackend`는 attach 파이프라인에서 mock client 기반 page/block attachment discovery를 할 수 있도록 `retrieve_page()`와 `list_block_children()`를 공개했다.

## 3. Acceptance 체크
| 항목명 | 검증 경로 |
| --- | --- |
| `pipeline/persist_attach.py` 경로 제공 | `code/plugins/memory/hermes_memory/pipeline/persist_attach.py` |
| `scope=knowledge` → vault inbox 경유 | `tests/attach/test_persist_attach.py::test_knowledge_markdown_routes_only_through_inbox` |
| `scope=skill` → `references/` 직접 배치 | `tests/attach/test_persist_attach.py::test_skill_binary_writes_directly_to_registered_references_root` |
| knowledge binary → `attachments/YYYY/MM/` raw 저장 | `tests/attach/test_persist_attach.py::test_knowledge_binary_writes_raw_attachment_and_routes_companion_note_through_inbox` |
| source prefix = `attach:` | `tests/attach/test_persist_attach.py::test_knowledge_binary_writes_raw_attachment_and_routes_companion_note_through_inbox` |
| scope 2종 × file type(.md, binary) 매트릭스 | `tests/attach/test_persist_attach.py::test_knowledge_markdown_routes_only_through_inbox`, `tests/attach/test_persist_attach.py::test_knowledge_binary_writes_raw_attachment_and_routes_companion_note_through_inbox`, `tests/attach/test_persist_attach.py::test_skill_markdown_writes_frontmatter_note_directly`, `tests/attach/test_persist_attach.py::test_skill_binary_writes_directly_to_registered_references_root` |
| mock-only download 인터페이스 | `code/plugins/memory/hermes_memory/attach/downloader.py`, `tests/attach/test_persist_attach.py::MockAttachmentDownloader` |
| hash 기반 duplicate file 감지 | `tests/attach/test_persist_attach.py::test_hash_dedup_reuses_existing_skill_binary_and_note` |
| Notion page attachment extraction | `tests/attach/test_persist_attach.py::test_extractor_reads_page_property_files_and_blocks`, `tests/attach/test_persist_attach.py::test_process_notion_page_loads_page_and_blocks_from_notion_backend` |

## 4. RECON.md 보강 사항
- 신규 RECON 보강 없음.
- 기존 확정사항만 사용했다: note area=`knowledge/`,`inbox/`; quarantine=`<vault_root>/_quarantine/`; attachment root=`attachments/YYYY/MM/`; skill references=`~/.hermes/skills/{name}/references/`.

## 5. 질문 보류 신규 항목
- `docs/QUESTIONS.md`에 **14. `scope=skill` reference note의 `area` canonical value**를 추가했다.
- 현재 frontmatter 9필드 닫힌 스키마와 skill 외부경로 note 요구가 충돌하므로, 구현은 `area: knowledge` + 경로 기반 분리로 수습했다.

## 6. 다음 Phase 선행조건
- skill-scope reference markdown의 canonical frontmatter 해석(`area`, 검색 제외 규칙)을 SSoT로 확정해야 한다.
- session_close/audit 단계에서 `scope=skill` attach 산출물을 어떻게 제외·식별할지 P11과의 교차규칙을 명문화해야 한다.
- attachment sidecar manifest(`*.attach.json`)가 장기 SSoT인지, 추후 별도 metadata artifact로 이동할지 확인이 필요하다.

## 7. 간략한 회고
이번 Phase는 기존 P6/P7 경로를 깨지 않으면서 “첨부는 raw file, note는 structured markdown”이라는 축을 분리하는 작업이었다. 핵심은 실제 다운로드를 금지한 상태에서 Notion attachment를 어떻게 검증 가능한 인터페이스로 바꾸느냐였고, 그래서 mock-only downloader + extractor + scope-aware pipeline으로 나눴다. 또 frontmatter 9필드 닫힌 스키마를 유지해야 했기 때문에 별도 frontmatter 확장 대신 `attach:` source token에 page/block/hash 메타데이터를 넣고, 나머지 상세 메타데이터는 companion note 본문과 sidecar manifest로 분리했다. 이 접근으로 vault/inbox 규칙, skill references 분기, hash dedup, 전체 품질 게이트를 모두 통과시킬 수 있었다.
