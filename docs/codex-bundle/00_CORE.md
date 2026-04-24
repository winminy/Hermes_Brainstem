# 00_CORE — 공통 축 (상시 첨부)

<aside>
⚠️

**모든 Phase 투입에 반드시 상시 첨부.** 본 문서 없이 다른 Phase 페이지만 투입하면 규칙 누락이 발생한다.

</aside>

## 원본 출처

- 불변 원칙 15 → [헤르메스 커스텀 메모리 프로바이더 — 전체 사양](https://www.notion.so/SOURCE_DOC_ID?pvs=21) §11
- 절대 원칙 9 + 금지 5 → [Hermes Memory Provider — 개발 실행 프롬프트 (바탕화면 작업 폴더 버전)](https://www.notion.so/Hermes-Memory-Provider-SOURCE_DOC_ID?pvs=21)
- frontmatter 9필드 → [헤르메스 커스텀 메모리 프로바이더 — 전체 사양](https://www.notion.so/SOURCE_DOC_ID?pvs=21) §4-6·§13, [헤르메스 메모리 프로바이더 구현 요청문 — 코드 구현 상세 설계](https://www.notion.so/SOURCE_DOC_ID?pvs=21) §4-4·§16 (vault_[spec.md](http://spec.md) SSoT)

## 불변 원칙 15항 (SPEC §11)

1. 프로바이더는 판정하지 않는다. 스킬과 메타문서가 판정한다.
2. 원문 대화는 어디에도 저장되지 않는다. 감사 로그도 해시만.
3. 자동 저장(persist.process)은 inbox/ 경유 기본. 사용자 명시 첨부(persist.attach)는 scope에 따라 볼트 또는 스킬 references/로 직접 배치.
4. frontmatter 불변 필드(`uuid`, `date`, `source`)는 생성 후 절대 변경 금지. invariant_guard가 런타임 차단.
5. area enum은 `knowledge`, `inbox`만 허용한다.
6. 이미지·바이너리는 임베딩 대상 아님. 동반 노트의 첨부물이거나 스킬 references/의 자료로만 존재.
7. 모든 tool call은 JSON 스키마 강제. 위반 시 런타임 거부.
8. 재시도는 동일 방식 2회 → 대체 방식 2회 → 총 4회 실패 시 사용자 보고.
9. 모델·훅↔기준 매핑·태그·enum 등 가변값은 전부 마크다운이 결정. 코드는 해석기.
10. 노션 자동 변환은 하루 1회 지정 DB만: Sub-task DB(유형 ∈ {메모/리소스, Project Backlogs}) + User Info DB 전체. GDrive는 persist.attach 시에만.
11. 인박스에서 갈 수 있는 영역은 knowledge/ 단일. 스킬 references/ 쓰기는 persist.attach scope=skill 전용.
12. 본문은 옵시디언 네이티브 문법만. `###` → `-` 항목. **인용구 블록 금지**. 이미지 `![[파일]]`, 위키링크 `[[노트명]]`. 상세는 vault_[spec.md](http://spec.md) SSoT.
13. frontmatter 9필드는 schema_builder 런타임 빌드 JSON 스키마로 LLM structured output 강제 + `jsonschema.validate` 재검증.
14. 자동훅은 원문을 LLM 사전 요약 없이 그대로 파이프라인에 전달. `pipeline/inline_llm.py` 파일 생성 금지.
15. 인박스 처리는 **순차**. 한 실행에서 inbox 문서는 병렬이 아닌 순차로 졸업. inbox-to-inbox dedup 경로 없음.

## 절대 원칙 9개 (개발 실행 프롬프트)

1. **SSoT는 볼트의 .md** — 태그·type·훅 매핑·저장 정책 하드코딩 금지, 런타임 해석.
2. **원문 비저장** — 볼트·인덱스·감사 어디에도 평문 대화 없음. 감사는 sha256만.
3. **area = "knowledge" | "inbox"만 허용**.
4. **frontmatter 9필드 스키마 강제** — structured output 통과해도 `jsonschema.validate` 재검증.
5. **인박스 .md 단일 경로** — 바이너리는 `<vault>/attachments/YYYY/MM/`, 스킬 자료는 `<hermes-home>/skills/{name}/references/` 직접 배치.
6. **graduator → LightRAG 순서 고정 (α 정책)** — 볼트가 정본, LightRAG는 파생 인덱스.
7. **자동훅 LLM 사전 요약 금지** — `pipeline/inline_llm.py` 금지.
8. **위키링크는 LLM이 쓰지 않는다** — `core.wikilink.suggest_links()`가 LightRAG 후보 기반, 파일당 최대 2개.
9. **추측 금지** — 모르는 import·엔드포인트·필드명은 터미널 실측 또는 `docs/QUESTIONS.md` 보류.

## 금지 사항 5종

1. 사양서·구현문에 없는 기능 임의 추가.
2. 추측으로 import 경로·엔드포인트·필드명 채우기.
3. `print` 디버깅 잔존 (`structlog`만 허용).
4. 테스트 없는 프로덕션 구현.
5. 한 커밋에 두 Phase 혼합.

## frontmatter 9필드 스키마

- `uuid` : string, pattern `^obs:[0-9]{8}T[0-9]{4}(-[0-9]+)?$` **[불변]**
- `area` : enum `["knowledge", "inbox"]`
- `type` : enum `["person", "knowledge", "tool", "schedule", "preference", "project", "memo"]` (vault_[spec.md](http://spec.md) SSoT)
- `tags` : array of [TAGS.md](http://TAGS.md) registry enum
- `date` : string, pattern `^[0-9]{4}-[0-9]{2}-[0-9]{2}$` **[불변]**
- `updated` : string, pattern `^[0-9]{4}-[0-9]{2}-[0-9]{2}$`
- `source` : array of string (prefix `notion:` | `web:` | `session:` | `attach:` | `multi:`) **[불변]**
- `source_type` : enum `["notion", "gdrive", ""]`
- `file_type` : string

## 바탕화면 작업 폴더 (절대 규칙)

모든 산출물은 `~/Desktop/hermes-memory-provider/` 내부에만. 실제 시스템(`<hermes-home>/`, 실제 볼트, LightRAG 인덱스, git 원격) 직접 쓰기 금지.

- `code/` — plugins/memory/hermes_memory/ 전체 + config.yaml
- `vault_meta/` — Hermes 에이전트 시스템 config로 번들될 메타문서 초안
- `tests/` — pytest 스위트
- `docs/` — [RECON.md](http://RECON.md), PHASE_N_[REPORT.md](http://REPORT.md), [QUESTIONS.md](http://QUESTIONS.md)

## Phase 종료 공통 게이트 (4조건)

1. pytest 해당 모듈 전부 통과
2. ruff check + mypy --strict 클린
3. IMPL §22 해당 Phase 활성화 항목 테스트 경로로 증명
4. `docs/PHASE_N_REPORT.md` 7절 작성

## 리포트 7절 규격

1. 변경 파일 목록 (상대경로, 라인 증감)
2. 테스트 결과 (실행 명령, 통과/실패 카운트)
3. Acceptance 체크 (항목명, 검증 경로)
4. [RECON.md](http://RECON.md) 보강 사항
5. 질문 보류 신규 항목
6. 다음 Phase 선행조건
7. 간략한 회고 한 단락

## 배포 가능성 원칙 (P14 선행 제약)

- 모든 경로·API 키·엔드포인트·모델명은 설정 주입. 하드코딩 절대 금지.
- 필수 의존성은 core에 포함 (LightRAG·notion-client 포함). 임베딩 백엔드만 pluggable (API / 로컬 선택).
- 설정 누락 시 crash 금지. `hermes-memory-doctor`가 명확히 안내.
- `pyproject.toml` + `config.example.yaml` + `env.example` 3종은 Phase 1·4·14에 걸쳐 완성.

## RECON 확정 사항 (Phase 0 결과 반영)

- vault root: `<runtime-root>/obsidian/<vault-name>/<vault-name>`
- live vault note areas: `knowledge/`, `inbox/` only
- Hermes 에이전트 시스템 config bundle source: `vault_meta/_system/` (live vault 구조와 분리)
- 플러그인 실제 위치: live site-packages `plugins/memory/*` (사양서의 `<hermes-home>/plugins/memory/` 추정은 폐기)
- 자동훅 payload: 평탄 kwargs (`session_id`, `conversation_history`, `model`, `platform`) — 중첩 `session.*` 폐기
- Notion 접근: notion-client SDK 직접 호출 (MCP 서버 불필요)
- LightRAG: 필수 의존성. 기본 엔드포인트 `127.0.0.1:9621`, config 오버라이드 가능
- 임베딩 백엔드: config의 `embedding.backend` 값에 따라 `api` / `local`
- Secret 우선순위: `env > <openclaw-home>/openclaw.json#skills.entries.{service}.apiKey > yaml`
- 모델 토큰 한도: `vault_meta/_system/E_config/model_limits.yaml` SSoT, provider API fallback