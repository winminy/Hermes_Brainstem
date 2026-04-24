# P0_RECON — 환경 조사

## Phase 목표

코드 작성 전 필수 환경 조사. Hermes 런타임·LightRAG·Notion MCP·LLM SDK·볼트 메타문서·Obsidian 쓰기 경로 6축을 실측으로 확정.

## 진입 선행조건

- 작업 폴더 `~/Desktop/hermes-memory-provider/` 초기화 (`code/`, `vault_meta/`, `tests/`, `docs/` 4 디렉터리)
- [📦 Hermes Memory Provider — Codex 투입 번들](https://www.notion.so/Hermes-Memory-Provider-Codex-73684b10b1cd4a9fa61b7049547583d1?pvs=21) 상시 첨부

## 수용 기준

- [ ]  `docs/RECON.md` 6축 조사 결과 전부 기록
- [ ]  `docs/QUESTIONS.md` 사용자 확인 필요 항목 분리
- [ ]  사양·실측 불일치 항목 표 말미 정리
- [ ]  IMPL §21 미결 11건 중 조사로 확정 가능한 항목 제안값 기재
- [ ]  **RECON·QUESTIONS 회수 전까지 Phase 1 이후 전면 차단**

## 교차참조

| 이 Phase | 동시 참조 | 이유 |
| --- | --- | --- |
| P0 | 00_CORE 절대원칙 9 (추측 금지) | 모든 조사의 전제 |
| P0 → P1 | Phase 1 메타문서 A 3종 | RECON·QUESTIONS 통과 필수 |
| P0 → P4 | LightRAG·MCP 어댑터 | 엔드포인트·SDK 실측이 구현 근거 |

## 6축 조사 규격

### 1. Hermes 런타임

- `which hermes`, `pip show hermes-agent`
- 인터프리터에서 `import hermes` → 모듈 경로 확보
- 플러그인 로더 클래스 공개 API `inspect.getsource`
- `~/.hermes/plugins/memory/` 기존 provider 엔트리포인트 선두 80줄 학습
- 훅 콜백 세션 payload 필드명(`session.id`, `session.messages`, `session.attachments`) 실측 확인
- 불일치 시 Phase 1 차단 → 사용자 보고

### 2. LightRAG

- `curl http://127.0.0.1:9621/openapi.json` → upsert·query·delete 스키마 확정
- 실제 요청 1회씩 보내 응답 shape 기록
- 엔드포인트 차이 발견 시 `config.yaml` 기본값을 실측치로 반영

### 3. Notion MCP

- `pip show mcp` 버전 확인
- `~/.hermes/config/mcp.yaml` 또는 `~/.config/mcp/`에서 Notion MCP 실행 방식·토큰 저장 위치 파악
- 토큰이 keychain이면 **위치만** 기록, 값 자체는 RECON 미기록
- `query_datasource`·pagination SDK 시그니처 샘플 호출 검증

### 4. LLM Provider SDK

- `pip show anthropic openai httpx tenacity pydantic jsonschema pyyaml mistune python-frontmatter apscheduler filelock structlog`
- Anthropic tool_use, OpenAI `response_format=json_schema` 실제 SDK 버전별 예제 코드 열람

### 5. 볼트 메타문서 현황

- `config.yaml` `vault.root` 확정
- `_system/` 하위 16종 존재 여부 표 기록 ([Hermes Memory Provider — 필요 메타문서 체크리스트](https://www.notion.so/Hermes-Memory-Provider-aaf29ba05b504304bfa52059bf20d0dc?pvs=21) 대조)
- 없는 항목 → Phase 1·2에서 `vault_meta/_system/` 초안 작성

### 6. Obsidian 쓰기 경로

- `<vault>/.obsidian/plugins/` 내 `advanced-uri` 또는 `obsidian-local-rest-api` 존재 여부
- 있으면 QUESTIONS로 선호 질문, 없으면 `config.vault.writer = "fs"` 고정

## 프롬포트 Phase 0 블록

[Hermes Memory Provider — 개발 실행 프롬프트 (바탕화면 작업 폴더 버전)](https://www.notion.so/Hermes-Memory-Provider-8f53dd62729248a69d648b61d5c907a2?pvs=21) 본문의 **Phase 0** 단락 전문 참조. Phase 1 이후 착수는 `docs/RECON.md` + `docs/QUESTIONS.md` 제출 후 사용자 회신까지 대기.

## 리포트 템플릿 (PHASE_0_[REPORT.md](http://REPORT.md))

1. 변경 파일 목록 — 없음 (조사 전용)
2. 테스트 결과 — 실측 명령 로그
3. Acceptance 체크 — 6축 완료 여부
4. [RECON.md](http://RECON.md) 보강 사항
5. QUESTIONS 신규 항목
6. 다음 Phase 선행조건 — 사용자 회신
7. 회고