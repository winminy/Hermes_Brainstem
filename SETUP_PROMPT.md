# Hermes Memory Provider Setup Prompt

You are installing **Hermes Memory Provider**, an Obsidian-backed memory system that stores durable notes in a vault, routes every new entry through `inbox/`, and exposes sync/search/status tools through MCP. It can sync from Notion, use LightRAG for semantic search, and fall back to direct vault search when LightRAG is absent. Your job is to complete installation safely, ask the user for missing values, and never run a real sync without approval.

## 1. Installation flow

Prefer this order:
1. Run `bash setup.sh` from the project root.
2. If `setup.sh` cannot be used, perform the manual steps below.
3. After setup, run `hermes-memory-doctor --config ./config.yaml`.
4. Before any real sync, run only a dry-run and ask the user for approval.

## 2. What you must ask the user

Ask for these values in plain language:
- **Obsidian 볼트 경로가 어디인가요?**
- **LightRAG 임베딩 모델을 선택할까요?**
  - `[1] OpenAI API (text-embedding-3-small)`
  - `[2] 로컬 모델 (sentence-transformers/all-MiniLM-L6-v2)`
  - 모르면 **기본값은 OpenAI API**라고 안내
- **Notion API 키가 있나요? 없으면 나중에 설정해도 됩니다.**
- **동기화할 Notion DB URL을 알려주세요. 나중에 설정하려면 Enter로 건너뛸 수 있습니다.**
- **이 DB에서 어떤 속성(컬럼)을 동기화하시겠습니까?**
  - Notion API 키가 있으면 속성 목록을 보여주고 번호 선택을 요청
  - Enter면 기본값은 **전체 동기화**라고 안내
  - 사용자가 모르면 `sync_properties: null`로 두고 나중에 수정 가능하다고 설명
- **어떤 속성 기준으로 type을 분류할까요?**
- **OpenAI API 키가 있나요?**
  - OpenAI LightRAG를 고르면 없을 때 반드시 다시 물어서 `.env`에 넣어야 함

If the user does not know a value:
- use the documented default when safe,
- or leave the secret blank and explain how to add it later.

## 3. setup.sh 사용 방법

Run:

```bash
bash setup.sh
```

`setup.sh` will:
- verify Python 3.10+
- run `python -m pip install -e ".[embedding-api]"`
- run `python -m pip install lightrag-hku`
- ask for the vault path, LightRAG embedding choice, optional Notion API key, optional Notion DB URL, optional Notion sync property selection, and OpenAI API key when required
- create `config.yaml` and `.env`
- create `knowledge/`, `inbox/`, `_quarantine/` inside the chosen vault if missing
- create `data/lightrag_store/` inside the project root
- optionally start `lightrag serve --host 127.0.0.1 --port 9621 --working-dir ./data/lightrag_store`
- run `hermes-memory-doctor`
- print a summary

## 4. Manual installation fallback

If interactive setup is not possible, do this:

```bash
python -m pip install -e ".[dev]"
python -m pip install -e ".[embedding-api]"
python -m pip install lightrag-hku
cp config.example.yaml config.yaml
cp env.example .env
mkdir -p data/lightrag_store
```

Then edit `config.yaml`:
- set `vault_root` to the user’s Obsidian vault
- set `embedding.backend` to `api` or `local`
- set `lightrag.endpoint` and `lightrag.base_url` to `http://127.0.0.1:9621`
- set `lightrag.embedding_model` to `openai` or `local`
- keep `lightrag.working_dir: ./data/lightrag_store`
- if the user provides a Notion DB URL, extract the 32-character database ID from the URL and put it under `notion.databases`
- if the user wants selective sync, set `sync_properties` to `[{name, type}, ...]`
- if the user wants title-only sync, set `sync_properties: []`
- if the user wants full sync or does not know yet, omit `sync_properties` or set it to `null`
- leave optional secrets blank if the user does not have them yet

Then edit `.env` as needed:
- `NOTION_API_KEY`
- `OPENAI_API_KEY`
- optional `HERMES_MEMORY_*` overrides

## 5. Obsidian vault integration

### 볼트 경로 확인법
- Obsidian 앱 → **설정 → 볼트**
- 현재 볼트의 경로를 확인하거나 복사

### 볼트 내 폴더 구조
- `knowledge/`: 분류 완료된 지식 entry 저장소
- `inbox/`: 모든 신규 entry가 최초 도착하는 관문. classifier가 type/tags를 판별하면 `knowledge/`로 자동 승격됨. 판별 실패 시 `inbox/`에 남고 확인 사유가 남음
- `_quarantine/`: 규격 미달 entry 격리소. `quarantine_sweep` 훅이 주기적으로 정리

### 핵심 원칙
- **inbox-first**: 모든 entry는 반드시 `inbox/`를 먼저 거친다
- provider가 본문 note를 직접 `knowledge/`에 쓰는 경로는 없다
- 사용자는 Obsidian 파일 트리에서 `knowledge/`와 `inbox/`를 분리해 확인하면 된다

## 6. LightRAG 설치 및 연동

```bash
python -m pip install lightrag-hku
lightrag serve --host 127.0.0.1 --port 9621 --working-dir ./data/lightrag_store
```

선택지는 두 가지입니다.
- **OpenAI API**
  - `text-embedding-3-small` 사용
  - `.env`에 `OPENAI_API_KEY`가 있으면 바로 사용 가능
  - 사용자가 모르면 기본값으로 안내 가능
- **로컬 모델**
  - `sentence-transformers/all-MiniLM-L6-v2` 사용
  - 추가로 `python -m pip install sentence-transformers torch`
  - API 키 불필요
  - 첫 실행 시 모델 다운로드가 일어날 수 있음
  - 기동 명령은 아래처럼 `--embedding-model`을 붙임

```bash
lightrag serve --host 127.0.0.1 --port 9621 \
  --working-dir ./data/lightrag_store \
  --embedding-model sentence-transformers/all-MiniLM-L6-v2
```

Then set:
- `config.yaml` → `lightrag.endpoint: http://127.0.0.1:9621`
- `config.yaml` → `lightrag.base_url: http://127.0.0.1:9621`
- `config.yaml` → `lightrag.embedding_model: openai` 또는 `local`
- `config.yaml` → `lightrag.working_dir: ./data/lightrag_store`

Important notes:
- 설치 흐름에서 **"LightRAG 서버를 지금 기동할까요? [y/N]:"** 라고 물어보고, 사용자가 거절하면 실행 명령을 보여준 뒤 **"나중에 위 명령으로 기동하세요"** 라고 안내합니다.
- LightRAG가 없어도 시스템 전체는 동작할 수 있음
- direct vault search fallback은 유지됨
- semantic search가 필요할 때만 LightRAG를 켜도 됨

## 7. Notion API 키 투입

1. <https://www.notion.so/my-integrations> 에서 Integration 생성
2. 발급된 Internal Integration Token(`ntn_...`)을 `.env`의 `NOTION_API_KEY`에 설정
3. 동기화 대상 Notion 페이지/데이터베이스에서 **우측 상단 ••• → 연결 추가**로 해당 Integration 연결
4. 연결하지 않으면 401/403 에러가 날 수 있음

### Notion DB ID 확인법
- Notion에서 동기화할 데이터베이스를 엽니다.
- URL이 `notion.so/워크스페이스/[이 부분이 DB ID]?v=...` 형태인지 확인합니다.
- LLM은 사용자에게 **"동기화할 DB URL을 알려주세요"** 라고 물어본 뒤 32자리 ID를 추출해 `config.yaml`의 `notion.databases`에 기록해야 합니다.
- Notion API 키가 있으면 속성 목록과 타입(`title`, `select`, `rich_text`, `date` 등)을 보여주고 **"이 DB에서 어떤 속성(컬럼)을 동기화하시겠습니까?"** 라고 물어봅니다.
- 사용자가 Enter를 누르면 `sync_properties: null`로 두어 전체 동기화합니다.
- 비대화식 설치에서는 `HERMES_SETUP_NOTION_SYNC_SELECTION=1,3` 또는 `title-only`로 선택값을 넘길 수 있고, 지정하지 않으면 안전하게 전체 동기화합니다.
- 사용자가 일부 번호를 고르면 해당 `{name, type}` 쌍만 `sync_properties`에 기록합니다.
- Notion API 키가 없어 속성 조회를 못 하면 **"속성 목록을 자동 조회할 수 없습니다. 나중에 config.yaml의 sync_properties에 직접 입력하세요."** 라고 안내하고 다음 질문으로 진행합니다.
- 실서비스 DB ID를 문서 예시나 메타 문서에 하드코딩하지 마세요.

## 8. 임베딩 백엔드 설정

### API 방식
- 외부 API 사용
- `.env`에 `OPENAI_API_KEY` 설정
- `config.yaml`에 `embedding.backend: api`

### Local 방식
- `python -m pip install -e ".[embedding-local]"`
- `config.yaml`에 `embedding.backend: local`
- 첫 실행 시 모델이 자동 다운로드될 수 있음

## 9. MCP 서버 등록 방법

Use either of these:

```yaml
mcp_servers:
  hermes-memory:
    command: python
    args:
      - -m
      - plugins.memory.hermes_memory.mcp.server
```

Or run manually:

```bash
python -m plugins.memory.hermes_memory.mcp.server
```

Available MCP tools:
- `search`
- `sync`
- `inbox_submit`
- `status`

## 10. Doctor 실행 및 검증

Run:

```bash
hermes-memory-doctor --config ./config.yaml
```

Interpretation:
- PASS/WARN만 있으면 정상
- FAIL이 있으면 출력 안내에 따라 수정 후 재실행
- 빈 Notion/OpenAI 키 또는 꺼진 LightRAG 때문에 FAIL이 날 수 있으니 원인을 함께 설명할 것

## 11. Dry-run 동기화 테스트

절대 사용자 승인 없이 실제 동기화를 실행하지 마세요.

First do a dry-run:
- MCP 환경이면 `sync` tool을 `dry_run=true`로 호출
- `mode`는 보통 `full` 또는 `incremental`
- 결과를 보여주고 실제 파일 생성/변경이 없었는지 설명

Then:
- 문제가 없으면 **실제 동기화를 진행해도 되는지** 사용자에게 승인 요청
- 승인 전까지 `dry_run=False` 실동기화 금지

## 12. 완료 조건

설치가 완료되었다고 말할 수 있는 조건:
- doctor가 PASS/WARN 상태만 남김
- dry-run sync가 성공함
- 실제 sync는 사용자 승인 정책을 준수함

## 13. 행동 규칙

- 모르는 값은 추측하지 말고 사용자에게 묻기
- 사용자가 모르는 값은 기본값 또는 나중 설정으로 처리하기
- 비밀값은 출력에 재노출하지 않기
- 실제 동기화, Notion write-back, 외부 서비스 변경은 사용자 승인 전 금지
