# QUESTIONS.md

Unknowns were not guessed. These items need user confirmation or an external environment that is not currently present in the live runtime.

## 1. Authoritative vault root — Resolved
- **Resolved:** current Hermes runtime config has `vault.root: "<runtime-root>/obsidian/<vault-name>/<vault-name>"`.
- **근거:** `<runtime-root>/.hermes/config.yaml` 실측.
- Phase 2 문서는 이 경로를 authoritative vault root로 참조했다.

## 2. `_system/` vs `system/` — Resolved
- **Resolved:** 현재 populated vault는 `_system/`을 사용하고, `system/` 경로는 존재하지 않았다.
- **근거:** `<runtime-root>/obsidian/<vault-name>/<vault-name>/_system` 실디렉터리 확인, markdown 60개 관측. `<runtime-root>/obsidian/<vault-name>/<vault-name>/system`는 미존재.
- 따라서 Phase 2 산출물도 `_system/` 타깃 구조를 유지한다.

## 3. LightRAG live environment
- `http://127.0.0.1:9621/openapi.json` is down.
- No live schema could be measured from the target endpoint in Phase 5.
- **Fallback implemented:** official `lightrag-hku 1.4.15` PyPI HTTP interface assumptions (`POST /documents/texts`, `POST /query`, `DELETE /documents/delete_document`) were used with explicit code comments marking live-schema follow-up.
- **Need confirmation:** Where does the intended LightRAG instance live (other venv/container/host), and is `127.0.0.1:9621` still the correct endpoint?

## 4. Notion MCP server choice
- No Notion MCP server is configured in `<hermes-home>/config.yaml`; only `elevenlabs` and `web-search` are present.
- **Need confirmation:** Which Notion MCP server/command/transport should Phase 4 target in this environment?

## 5. Notion auth source of truth
- Runtime helper code supports env vars and `<runtime-root>/.openclaw/openclaw.json#skills.entries.notion.apiKey`, but no live Notion MCP auth source was configured.
- **Need confirmation:** For this project, should Notion auth come from MCP-managed credentials, Hermes `.env`, keychain, or OpenClaw JSON?

## 6. Hook payload contract
- Live plugin hooks expose flattened kwargs like `session_id`, `conversation_history`, `model`, `platform`.
- Spec text asks to confirm `session.id`, `session.messages`, `session.attachments`.
- **Need confirmation:** Is the project expected to follow the live flattened hook contract, or is there another runtime/version where nested `session.*` payloads exist?

## 7. LLM token limits — Resolved
- **Resolved:** `vault_meta/_system/E_config/model_limits.yaml`를 실측 config 기준으로 작성했다.
- **근거:** `<runtime-root>/.hermes/config.yaml`에서 active runtime이 `openai-codex/gpt-5.4`임을 확인했고, `<runtime-root>/.openclaw/agents/main/agent/models.json`의 `codex.models[gpt-5.4]`에서 `contextWindow=272000`, `maxTokens=128000`을 확인했다.
- provider catalog가 비어 있거나 누락될 때만 provider API fallback을 사용한다.

## 8. GDrive 파일 DB 정본 — Resolved
- **Resolved:** out-of-scope로 판정, `notion_datasource_map.md` 매핑 불필요.
- **근거:** GDrive는 Notion 외부 파일 참조 카탈로그이며 볼트 entry 대상이 아니다.
- Phase 1의 Notion→Obsidian 동기화 대상은 knowledge/person/schedule 성격 DB만 유지한다.

## 9. GDrive 파일 DB 매핑 여부 — Resolved
- **Resolved:** out-of-scope로 판정, 매핑 불필요.
- **근거:** GDrive는 Notion 외부 파일 참조 카탈로그이며 볼트 entry 대상이 아니다.
- Scope correction에 따라 `GDrive 파일 DB 포함` 요구는 폐기한다.

## 10. Project relation → TAGS registry crosswalk (기존 Q9) — Resolved
- **Resolved:** relation title이 [[TAGS]] registry의 canonical project tag와 **정확히 일치할 때만** project tag를 부여하고, 미일치 relation은 무태그로 둔다.
- **근거:** `vault_meta/_system/TAGS.md`의 `project relation이 있어도 registry에 없는 새 태그는 생성하지 않는다`, `registry에 동일 canonical key가 있을 때만 project tag를 붙인다` 규칙과 `vault_meta/_system/notion_datasource_map.md`의 `project_relation_registry_match_only` note가 이미 같은 결론으로 수렴했다.
- 따라서 신규 canonical project tag 승인 전까지 자동 정규화나 별칭 매핑은 하지 않는다.

## 11. Quarantine flag vs frontmatter 9-field closed schema — Resolved
- **Resolved:** quarantine 판정은 frontmatter 확장이 아니라 **경로 기반 `<vault_root>/_quarantine/`** 으로 확정한다.
- **근거:** Phase 1의 frontmatter는 9필드 닫힌 스키마이고 추가 `quarantine` 필드를 허용하지 않는다. Phase 2 `quarantine_policy.md`와 Phase 3 core 구현은 모두 `<vault_root>/_quarantine/` prefix를 authoritative signal로 사용한다.
- 따라서 검색/위키링크 제외 조건은 `_quarantine/` 하위 경로 여부로만 해석한다.

## 12. Default skill draft basenames for `skills/default/*.md` — Resolved (N/A)
- **Resolved:** N/A. `<runtime-root>/.hermes/skills/default`는 실제 runtime에 존재하지 않았고, 초기 사양의 default skills 가정과 현재 환경이 불일치했다.
- **근거:** Phase 3 실측 `ls -1 <runtime-root>/.hermes/skills/default` 결과가 `No such file or directory`였고, `<runtime-root>/.hermes/skills`에는 다른 skill 묶음만 존재했다.
- skills 시스템 자체는 현재 Hermes Memory Provider Phase 4 스코프 밖이므로 canonical basename 확정 작업은 본 phase에서 진행하지 않는다.

## 13. Inbox merge-confirm queue consumer contract — Resolved
- **Resolved:** Phase 11 hook system이 merge-confirm queue consumer를 담당한다. `session_close` 훅이 `inbox/.hermes-inbox-merge-queue.jsonl`을 authoritative queue artifact로 읽고, 미분류 inbox note를 재검토한다.
- **처리 규칙:** 자동 분류 가능한 항목은 `InboxRunner.review_existing_entry()`를 통해 `knowledge/`로 승격하고 queue에서 제거한다. 수동 확인이 필요한 항목은 note를 `inbox/`에 유지하면서 `needs-confirmation` reason tag를 남기고 queue record를 보존한다.
- **근거:** P11 hook acceptance의 `session_close` inbox 상태 정리와 충돌하지 않으며, inbox→knowledge 단일 승격 규칙·원문 비저장·hash-only audit 원칙을 유지한다.

## 14. `scope=skill` reference note의 `area` canonical value — Resolved
- **Resolved:** `scope=skill` reference note의 canonical `area`는 `knowledge`로 통일한다.
- **근거:** frontmatter 9필드의 `area` enum은 `knowledge | inbox`만 허용되고, 불변 원칙 11도 인박스에서 갈 수 있는 영역을 `knowledge/` 단일로 고정한다. 따라서 skill reference note는 저장 경로(`<hermes-home>/skills/{name}/references/`)와 `attach:` source metadata로 skill-scope를 구분하고, frontmatter `area`는 예외 없이 `knowledge`를 유지한다.
- Phase 8 attach 구현은 이 canonical rule을 따르는 상태이며 후속 phase도 동일 규칙을 재사용한다.

## 15. Search tags filter의 canonical match semantics — Resolved
- **Resolved:** canonical default는 기존 Phase 9와 동일한 **ALL-of subset match**로 유지하고, Phase 10 MCP/API는 명시적 `tag_match_mode`(`all | any`)를 추가로 노출한다.
- **근거:** backward compatibility를 위해 기존 search filter 기본 의미를 바꾸지 않으면서도, MCP tool schema와 `search/direct_file.py` 구현이 `tag_match_mode='all'` 기본값 및 `any` override를 함께 지원하도록 정렬했다.
- 따라서 SSoT는 `tags` 필터 기본값=`all`, 선택적 확장=`any`이다.

## 16. APScheduler 실제 기동 책임자 — Resolved
- **Resolved:** Phase 14에서 `plugins.memory.hermes_memory.mcp.server.HermesMemoryMCPApplication`가 scheduler lifecycle의 canonical owner로 확정되었다.
- **근거:** `scheduler_lifespan()`이 `build_scheduler()`로 job registration을 수행한 뒤 `scheduler.start()`를 MCP server run 직전에 호출하고, 서버 종료 경로에서 `scheduler.shutdown()`을 보장한다.
- **검증:** `tests/mcp/test_server_lifecycle.py`가 startup 1회 / shutdown 1회 호출을 회귀 테스트로 고정했다.

## 17. Notion table write-back API의 canonical child append 형태
- Phase 12는 Obsidian markdown → Notion blocks 역변환에서 table을 내부 `table` block + `children: table_row[]` 구조로 표현했다.
- **Need confirmation:** 실제 notion-client write-back 시 table row를 동일 payload append로 허용하는지, 아니면 table block 생성 후 별도 `blocks.children.append` 단계가 필요한지 live API contract 확인이 필요하다.
