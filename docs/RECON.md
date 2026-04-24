# RECON.md

Phase 0 RECON only. All values below are live observations from the current Hermes runtime/user environment unless explicitly marked as spec-only.

## 1) Hermes 런타임

| 항목 | 실측값 | 사양서 기재값 | 불일치 여부 |
| --- | --- | --- | --- |
| CLI 엔트리포인트 | `/root/.local/bin/hermes` → `hermes_cli.main` | `which hermes`, `import hermes` 경로 확인 | 부분 불일치 (`import hermes` 가능한 top-level 모듈 없음) |
| 패키지 버전 | `hermes-agent 0.8.0` | live runtime 확인 요구 | 없음 |
| 플러그인 로딩 경로 | 일반 플러그인: `~/.hermes/plugins/`, 프로젝트 플러그인: `./.hermes/plugins/`(env opt-in), pip entrypoint: `hermes_agent.plugins` | plugin loading path 확인 | 없음 |
| 메모리 provider 실제 위치 | `site-packages/plugins/memory/*`; `~/.hermes/plugins/memory/`는 없음 | `~/.hermes/plugins/memory/` 기존 provider 엔트리포인트 학습 | 불일치 |
| MemoryProvider 인터페이스 | `agent.memory_provider.MemoryProvider`; 핵심: `initialize`, `system_prompt_block`, `prefetch`, `sync_turn`, `get_tool_schemas`, `handle_tool_call`; optional: `on_turn_start`, `on_session_end`, `on_pre_compress`, `on_memory_write`, `on_delegation` | MemoryProvider interface 확인 | 없음 |
| call timing: prefetch | turn당 tool loop 전에 `prefetch_all()` 1회, user message에 ephemeral injection | call timing 확인 | 없음 |
| call timing: sync | completed turn 뒤 `sync_all()` + `queue_prefetch_all()` | call timing 확인 | 없음 |
| call timing: session end | provider `on_session_end(messages)`는 실제 세션 경계에서만 호출, `shutdown_memory_provider()` 경유 | call timing 확인 | 없음 |
| plugin `on_session_end` 의미 | `run_conversation()` 종료마다 호출; 진짜 boundary는 `on_session_finalize`/`on_session_reset` | hook timing 확인 | spec 기대와 용어상 불일치 가능 |
| session payload 필드 | 확인된 hook kwargs는 `session_id`, `model`, `platform`, `completed`, `interrupted`, `conversation_history`, `user_message`, `assistant_response`; `session.id/messages/attachments` evidence 없음 | `session.id`, `session.messages`, `session.attachments` 실측 확인 | 불일치 |
| 활성 memory provider | `/root/.hermes/config.yaml`의 `memory.provider`가 빈 문자열 → built-in only | provider 확인 | 없음 |

## 2) LightRAG

| 항목 | 실측값 | 사양서 기재값 | 불일치 여부 |
| --- | --- | --- | --- |
| HTTP endpoint health | `http://127.0.0.1:9621/openapi.json` 접속 실패 (`connection refused`) | openapi fetch 후 upsert/query/delete 스키마 확정 | 불일치 |
| Python install path | 현재 runtime에 `lightrag` import 불가, 설치 흔적 미확인 | install path 확인 | 불일치 |
| API schema | live endpoint down으로 미확정 | upsert/query/delete schema 확정 필요 | 미확정 |
| 실제 요청 1회 검증 | 서버 미기동으로 미실행 | 실제 요청 1회씩 전송 | 미실측 |
| embedding model | live config/code에서 LightRAG embedding model 미확정 | embedding model 확인 | 미확정 |
| graph storage structure | live path/config 미확정 | graph storage structure 확인 | 미확정 |
| 운영 흔적 | vault 문서에서 LightRAG 검색/인덱싱 정책 언급 존재 | backend 근거 확보 | 부분 일치 |

## 3) Notion MCP

| 항목 | 실측값 | 사양서 기재값 | 불일치 여부 |
| --- | --- | --- | --- |
| MCP SDK 버전 | `mcp 1.27.0` | `pip show mcp` | 없음 |
| MCP 설정 위치 | `~/.hermes/config.yaml`의 `mcp_servers` 사용 | `~/.hermes/config/mcp.yaml` 또는 `~/.config/mcp/` 확인 | 부분 불일치 |
| configured servers | `elevenlabs`, `web-search`만 활성 | Notion MCP 실행 방식 파악 | 불일치 (Notion 없음) |
| `hermes mcp test notion` | `Server 'notion' not found in config` | sample call 검증 | 불일치 |
| Notion MCP endpoints | live Notion MCP server 부재로 미확정 | endpoints 확정 | 미확정 |
| MCP auth location | live Notion MCP 미구성으로 미확정 | auth 위치만 기록 | 미확정 |
| page/DB CRUD methods | MCP는 미확정. 대신 runtime helper `tools/notion_ai_tool.py`는 기대 도구로 `notion-search`, `notion-fetch`, optional `notion-create-pages`, `notion-update-page`를 참조 | page/DB CRUD methods 파악 | 부분 불일치 |
| direct REST fallback | `tools/notion_ai_tool.py`에서 `/v1/search`, `/v1/blocks/{page_id}/children` 확인 | MCP 우선 | 부분 불일치 |
| direct auth fallback location | env(`NOTION_API_KEY` 등) 또는 `/root/.openclaw/openclaw.json#skills.entries.notion.apiKey` | 토큰 위치만 기록 | 부분 일치 |

## 4) LLM SDK

| 항목 | 실측값 | 사양서 기재값 | 불일치 여부 |
| --- | --- | --- | --- |
| 기본 모델 | `gpt-5.4` | model in use 확인 | 없음 |
| provider | `openai-codex` | provider 확인 | 없음 |
| base_url | `https://chatgpt.com/backend-api/codex` | call wrapper 확인 | 없음 |
| active auth state location | `/root/.hermes/auth.json` (`active_provider: openai-codex`) | API key/location 확인 | 없음 |
| 보조 credential pool | `/root/.hermes/auth.json`, `/root/.hermes/.env`, `config.yaml` | API key/location 확인 | 없음 |
| SDK versions | `openai 2.31.0`, `anthropic 0.94.0`, `httpx 0.28.1`, `tenacity 9.1.4`, `pydantic 2.12.5`, `jsonschema 4.26.0`, `PyYAML 6.0.3`, `filelock 3.28.0` | dependency version 확인 | 부분 불일치 |
| missing deps from requested list | `mistune`, `python-frontmatter`, `APScheduler`, `structlog` package metadata 미검출 | listed packages 확인 | 불일치 |
| runtime wrapper clue | provider resolution은 config/auth 기반, OpenAI-compatible routing 사용; `openai-codex` active | call wrapper 확인 | 부분 일치 |
| token limits | live config/code에서 확정 numeric limit 미확인 | token limits 확인 | 미확정 |
| structured output wrapper | OpenAI/Anthropic SDK는 설치되어 있으나 project-specific wrapper/usage path는 Phase 0 범위에서 numeric/token guarantee 미확정 | wrapper 확인 | 미확정 |
| stale alt config | `/root/.hermes/config.toml`에 별도 custom provider 흔적 존재, 현재 active runtime과 불일치 | live runtime 우선 | 불일치 |

## 5) Vault meta docs / `_system` 현황

### 5-a. 볼트 루트/구조

| 항목 | 실측값 | 사양서 기재값 | 불일치 여부 |
| --- | --- | --- | --- |
| `config.yaml`의 `vault.root` | 없음 | `config.yaml`에서 확정 | 불일치 |
| 유력 vault 경로 | `/root/obsidian/Remy's brain/Remy's brain` (실파일 다수 존재) | vault path 확정 필요 | 미확정(추정) |
| 메타 루트 이름 | 실제는 `system/` | `_system/` | 불일치 |
| 현재 메타 문서 수 | `system/` 아래 `.md` 60개 | 16종 체크리스트 | 구조 불일치 |

### 5-b. 16종 체크리스트 대조

| 항목 | 실측값 | 사양서 기재값 | 불일치 여부 |
| --- | --- | --- | --- |
| `vault_spec.md` | `system/data_ops/vault_spec.md` 존재 | `_system/vault_spec.md` | 불일치(경로 상이) |
| `TAGS.md` | `system/self_reference/TAGS.md` 존재 | `_system/TAGS.md` | 불일치(경로 상이) |
| `notion_datasource_map.md` | 없음 | 필요 | 불일치 |
| `data_ops/file_policy.md` | 없음 | 필요 | 불일치 |
| `data_ops/retention.md` | 없음 | 필요 | 불일치 |
| `data_ops/binary_policy.md` | 없음 | 필요 | 불일치 |
| `self_reference/persist_policy.md` | 없음 | 필요 | 불일치 |
| `self_reference/scope_policy.md` | 없음 | 필요 | 불일치 |
| `self_reference/hook_registry.md` | 없음 | 필요 | 불일치 |
| `self_reference/quarantine_policy.md` | 없음 | 필요 | 불일치 |
| `skills/skill_spec.md` | 없음 | 필요 | 불일치 |
| `skills/skill_registry.md` | 없음 | 필요 | 불일치 |
| `skills/default/*.md` 기본 4종 | 없음 | 기본 스킬 4종 필요 | 불일치 |

### 5-c. 추가 관찰

| 항목 | 실측값 | 사양서 기재값 | 불일치 여부 |
| --- | --- | --- | --- |
| 현행 `vault_spec.md` frontmatter schema | `area: system`, `domain`, `purpose` 등 사용 | frontmatter 9필드 통일 스키마 | 불일치 |
| 현행 `TAGS.md` 위치 | `system/self_reference/TAGS.md` | `_system/TAGS.md` | 불일치 |
| 현행 env meta | `system/self_reference/env.md` 존재하나 `vault_root` TODO 흔적 | 확정값 필요 | 불일치 |

## 6) Obsidian 쓰기 규칙

| 항목 | 실측값 | 사양서 기재값 | 불일치 여부 |
| --- | --- | --- | --- |
| vault path | 유력 후보 `/root/obsidian/Remy's brain/Remy's brain` | vault path 확정 | 미확정(추정) |
| `.obsidian/plugins` | checked vault들에서 community plugin dir 없음 | `advanced-uri`/`obsidian-local-rest-api` 존재 여부 확인 | 없음(미설치) |
| writer mode | config에 `vault.writer` 없음; plugin 부재 기준 spec상 `fs`가 기본안 | plugin 없으면 `config.vault.writer = "fs"` 고정 | 부분 일치 |
| live save rule clue | 현행 `vault_spec.md`: kebab-case 권장, `.md`, 중복시 numeric suffix | markdown save rules 확인 | spec과 일부 불일치 |
| live note reality | 실제 `knowledge/` 노트명은 한글/공백/특수문자 다수 사용 | kebab-case/영문 소문자+숫자+하이픈 | 불일치 |
| wikilink format | `[[파일명]]`, `[[파일명|표시텍스트]]`가 `vault_spec.md`에 명시되고 실제 노트에서도 사용 | wikilink format 확인 | 없음 |
| directory layout | 실제 vault: `inbox/`, `knowledge/`, `tools/`, `system/` | spec: `inbox/`, `knowledge/`, `tools/`, `_system/` | 불일치 |
| note frontmatter reality | 샘플 note들은 `uuid/area/type/tags/date/updated/source` 정도만 사용, 타입 값도 spec enum과 불일치(예: `AI prompts`, `페르소나`) | frontmatter 9필드 + enum | 불일치 |

## IMPL §21 확인 가능한 제안값(조사로 확정된 것만)

- `llm.model`: `gpt-5.4`
- `llm.provider`: `openai-codex`
- `llm.base_url`: `https://chatgpt.com/backend-api/codex`
- `obsidian.writer` proposal: `fs` (community plugin 미설치 관찰 기준)
- `vault_root` proposal: `/root/obsidian/Remy's brain/Remy's brain` **단, live config 근거는 없어서 사용자 확인 필요**

## 사양 대비 불일치 요약

1. Hermes runtime에는 top-level `hermes` import가 없고, memory provider는 `~/.hermes/plugins/memory/`가 아니라 site-packages `plugins/memory/*`에 존재한다.
2. session hook payload에서 spec이 기대한 `session.id/messages/attachments` 구조 증거를 찾지 못했고, 실제로는 평탄한 kwargs(`session_id`, `conversation_history` 등)가 사용된다.
3. LightRAG endpoint `127.0.0.1:9621`는 현재 down이며, 현재 Python runtime에 `lightrag` 패키지도 없다.
4. Notion MCP server는 live config에 아예 없고, `hermes mcp test notion`도 실패한다.
5. `~/.hermes/config.yaml`에는 `vault.root`와 `vault.writer`가 없다.
6. 실제 vault 메타 루트는 `_system/`이 아니라 `system/`이며, required 16종 체크리스트 대부분이 부재하다.
7. 현행 vault 문서의 frontmatter/type/path 규칙은 본 프로젝트 spec(9필드, `area=knowledge`, `_system/`, enum 고정)과 다수 충돌한다.
8. live vault note naming은 kebab-case 규칙과 다르고 한글/공백/특수문자를 사용한다.
9. dependency set이 spec 요청 목록과 다르며 `mistune`, `python-frontmatter`, `APScheduler`, `structlog`는 current runtime metadata 기준 미검출이다.
10. `/root/.hermes/config.toml`에는 현재 active runtime과 다른 stale custom provider 흔적이 있다.
