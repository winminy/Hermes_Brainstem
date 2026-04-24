#!/usr/bin/env bash
set -euo pipefail

show_help() {
  cat <<'EOF'
Hermes Memory Provider interactive setup

Usage:
  bash setup.sh
  bash setup.sh --help

What it does:
  1. Checks for Python 3.10+
  2. Runs editable install with the embedding-api extra
  3. Installs LightRAG and prompts for the LightRAG embedding mode
  4. Prompts for vault path, optional Notion credentials, optional Notion DB URL,
     and live Notion property selection when the API key + DB are available
  5. Writes config.yaml and .env
  6. Creates knowledge/, inbox/, _quarantine/, and data/lightrag_store/ if needed
  7. Optionally starts the LightRAG server, then runs hermes-memory-doctor

Non-interactive Notion property selection:
  HERMES_SETUP_NOTION_SYNC_SELECTION=1,3   # select numbered properties
  HERMES_SETUP_NOTION_SYNC_SELECTION=title-only
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  show_help
  exit 0
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

LIGHTRAG_ENDPOINT="http://127.0.0.1:9621"
LIGHTRAG_WORKING_DIR_REL="./data/lightrag_store"
LIGHTRAG_WORKING_DIR="$PROJECT_ROOT/data/lightrag_store"
LIGHTRAG_LOG_PATH="$PROJECT_ROOT/data/lightrag.log"

find_python() {
  if command -v python3 >/dev/null 2>&1; then
    printf '%s\n' "python3"
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    printf '%s\n' "python"
    return 0
  fi
  return 1
}

if ! PYTHON_BIN="$(find_python)"; then
  echo "[ERROR] Python 3.10+ is required, but no python executable was found." >&2
  exit 1
fi

if ! "$PYTHON_BIN" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
then
  echo "[ERROR] Python 3.10+ is required. Detected: $($PYTHON_BIN --version 2>&1)" >&2
  exit 1
fi

echo "[INFO] Using $($PYTHON_BIN --version 2>&1)"
echo "[INFO] Installing project in editable mode with [embedding-api] extra..."
"$PYTHON_BIN" -m pip install -e ".[embedding-api]"
echo "[INFO] Installing LightRAG..."
"$PYTHON_BIN" -m pip install lightrag-hku

expand_path() {
  "$PYTHON_BIN" - "$1" <<'PY'
import os
import sys
print(os.path.abspath(os.path.expanduser(sys.argv[1])))
PY
}

existing_env_value() {
  local key="$1"
  if [[ ! -f "$PROJECT_ROOT/.env" ]]; then
    return 1
  fi
  "$PYTHON_BIN" - "$PROJECT_ROOT/.env" "$key" <<'PY'
from pathlib import Path
import sys

env_path = Path(sys.argv[1])
key = sys.argv[2]
for raw_line in env_path.read_text(encoding='utf-8').splitlines():
    line = raw_line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    name, value = line.split('=', 1)
    if name.strip() == key and value.strip():
        print(value.strip())
        raise SystemExit(0)
raise SystemExit(1)
PY
}

extract_notion_db_id() {
  "$PYTHON_BIN" - "$1" <<'PY'
from urllib.parse import urlparse
import re
import sys

raw = sys.argv[1].strip()
if not raw:
    raise SystemExit(1)
parsed = urlparse(raw)
candidates = [raw]
if parsed.path:
    candidates.extend(part for part in parsed.path.split('/') if part)
pattern = re.compile(r'([0-9a-fA-F]{32})')
for candidate in candidates:
    match = pattern.search(candidate.replace('-', ''))
    if match:
        print(match.group(1).lower())
        raise SystemExit(0)
raise SystemExit(1)
PY
}

is_interactive_shell() {
  [[ -t 0 && -t 1 ]]
}

fetch_notion_database_properties_payload() {
  "$PYTHON_BIN" - "$NOTION_API_KEY" "$NOTION_DB_ID" <<'PY'
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

api_key = sys.argv[1].strip()
database_id = sys.argv[2].strip()
supported_types = {
    'title',
    'rich_text',
    'number',
    'select',
    'multi_select',
    'status',
    'date',
    'person',
    'checkbox',
    'url',
    'email',
    'phone_number',
    'files',
    'relation',
    'created_time',
    'last_edited_time',
    'created_by',
    'last_edited_by',
    'formula',
    'rollup',
}

headers = {
    'Authorization': f'Bearer {api_key}',
    'Notion-Version': '2022-06-28',
}

last_error: str | None = None
payload: dict[str, object] | None = None
for endpoint in (
    f'https://api.notion.com/v1/databases/{database_id}',
    f'https://api.notion.com/v1/data_sources/{database_id}',
):
    request = urllib.request.Request(endpoint, headers=headers, method='GET')
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
            break
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace').strip()
        last_error = f'{exc.code} {exc.reason}: {body or endpoint}'
    except urllib.error.URLError as exc:
        last_error = str(exc.reason)

if payload is None:
    print(last_error or 'failed to retrieve Notion database schema', file=sys.stderr)
    raise SystemExit(1)

properties: list[dict[str, str]] = []
unsupported: list[dict[str, str]] = []
for property_name, descriptor in (payload.get('properties') or {}).items():
    if not isinstance(property_name, str) or not isinstance(descriptor, dict):
        continue
    property_type = str(descriptor.get('type') or '').strip().lower()
    if not property_type:
        continue
    item = {'name': property_name, 'type': property_type}
    if property_type in supported_types:
        properties.append(item)
    else:
        unsupported.append(item)

properties.sort(key=lambda item: (item['type'] != 'title', item['name']))
if unsupported:
    skipped = ', '.join(f"{item['name']}({item['type']})" for item in unsupported)
    print(f'[WARN] 지원하지 않는 Notion 속성 타입은 선택 목록에서 제외됩니다: {skipped}', file=sys.stderr)

print(json.dumps({'properties': properties}, ensure_ascii=False))
PY
}

print_notion_property_menu() {
  "$PYTHON_BIN" - "$1" <<'PY'
from __future__ import annotations

import json
import sys

payload = json.loads(sys.argv[1])
properties = payload.get('properties') or []
for index, item in enumerate(properties, start=1):
    print(f' [{index}] {item["name"]} ({item["type"]})')
PY
}

parse_notion_sync_selection() {
  "$PYTHON_BIN" - "$1" "$2" <<'PY'
from __future__ import annotations

import json
import sys

payload = json.loads(sys.argv[1])
selection = sys.argv[2].strip()
properties = payload.get('properties') or []

selection_lower = selection.lower()
if not selection or selection_lower in {'all', '*'}:
    print('null')
    raise SystemExit(0)

if selection_lower in {'0', 'title-only', 'title_only', 'title'}:
    print('[]')
    raise SystemExit(0)

tokens = [token.strip() for token in selection.split(',') if token.strip()]
if not tokens:
    raise SystemExit(1)

chosen: list[dict[str, str]] = []
seen: set[tuple[str, str]] = set()
for token in tokens:
    index = int(token)
    if index < 1 or index > len(properties):
        raise SystemExit(1)
    item = properties[index - 1]
    key = (str(item['name']), str(item['type']))
    if key in seen:
        continue
    seen.add(key)
    chosen.append({'name': key[0], 'type': key[1]})

print(json.dumps(chosen, ensure_ascii=False))
PY
}

prompt_notion_sync_properties() {
  NOTION_SYNC_PROPERTIES_JSON='null'
  NOTION_SYNC_PROPERTIES_SUMMARY='not configured'

  if [[ -z "${NOTION_DB_ID:-}" ]]; then
    return 0
  fi

  NOTION_SYNC_PROPERTIES_SUMMARY='full (sync_properties: null)'

  local existing_key=""
  if [[ -z "${NOTION_API_KEY:-}" ]] && existing_key="$(existing_env_value NOTION_API_KEY 2>/dev/null)"; then
    NOTION_API_KEY="$existing_key"
  fi

  if [[ -z "${NOTION_API_KEY:-}" ]]; then
    echo "[WARN] 속성 목록을 자동 조회할 수 없습니다. 나중에 config.yaml의 sync_properties에 직접 입력하세요."
    NOTION_SYNC_PROPERTIES_SUMMARY='full (property auto lookup unavailable)'
    return 0
  fi

  local properties_payload=""
  if ! properties_payload="$(fetch_notion_database_properties_payload)"; then
    echo "[WARN] 속성 목록을 자동 조회할 수 없습니다. 나중에 config.yaml의 sync_properties에 직접 입력하세요."
    NOTION_SYNC_PROPERTIES_SUMMARY='full (property auto lookup failed)'
    return 0
  fi

  local property_count=""
  property_count="$($PYTHON_BIN - "$properties_payload" <<'PY'
from __future__ import annotations

import json
import sys

payload = json.loads(sys.argv[1])
print(len(payload.get('properties') or []))
PY
)"
  if [[ "$property_count" == "0" ]]; then
    echo "[WARN] 선택 가능한 Notion 속성을 찾지 못했습니다. sync_properties: null로 저장합니다."
    NOTION_SYNC_PROPERTIES_SUMMARY='full (no selectable properties found)'
    return 0
  fi

  echo "[INFO] Notion 속성 목록을 조회했습니다."
  print_notion_property_menu "$properties_payload"

  local selection="${HERMES_SETUP_NOTION_SYNC_SELECTION:-}"
  if [[ -n "$selection" ]]; then
    echo "[INFO] HERMES_SETUP_NOTION_SYNC_SELECTION 값을 사용합니다: $selection"
  fi

  while true; do
    if [[ -z "$selection" ]]; then
      if is_interactive_shell; then
        echo "이 DB에서 어떤 속성(컬럼)을 동기화하시겠습니까?"
        echo " - Enter: 전체 동기화 (sync_properties: null)"
        echo " - 0: 제목만 동기화 (sync_properties: [])"
        read -r -p "번호를 쉼표로 입력하세요 (예: 1,3,4): " selection
        selection="${selection:-}"
      else
        echo "[WARN] 비대화식 모드에서는 Notion 속성 선택 프롬프트를 띄울 수 없습니다. 기본값 전체 동기화(sync_properties: null)를 사용합니다. 선택하려면 HERMES_SETUP_NOTION_SYNC_SELECTION=1,3 또는 title-only를 지정하세요."
        return 0
      fi
    fi

    if NOTION_SYNC_PROPERTIES_JSON="$(parse_notion_sync_selection "$properties_payload" "$selection")"; then
      case "$(printf '%s' "$selection" | tr '[:upper:]' '[:lower:]')" in
        ''|'all'|'*')
          NOTION_SYNC_PROPERTIES_SUMMARY='full (sync_properties: null)'
          ;;
        '0'|'title-only'|'title_only'|'title')
          NOTION_SYNC_PROPERTIES_SUMMARY='title-only (sync_properties: [])'
          ;;
        *)
          NOTION_SYNC_PROPERTIES_SUMMARY="selected ($selection)"
          ;;
      esac
      return 0
    fi

    if ! is_interactive_shell || [[ -n "${HERMES_SETUP_NOTION_SYNC_SELECTION:-}" ]]; then
      echo "[WARN] 잘못된 Notion 속성 선택 값이 감지되어 기본값 전체 동기화(sync_properties: null)를 사용합니다."
      NOTION_SYNC_PROPERTIES_JSON='null'
      NOTION_SYNC_PROPERTIES_SUMMARY='full (invalid selection fallback)'
      return 0
    fi

    echo "[ERROR] 올바른 번호 조합을 입력하세요. Enter=전체 동기화, 0=제목만, 1..N=선택 동기화입니다."
    selection=""
  done
}

prompt_vault_root() {
  local answer=""
  while true; do
    read -r -p "Obsidian 볼트 경로를 입력하세요 (예: ~/obsidian/vault): " answer
    answer="${answer:-}"
    if [[ -z "$answer" ]]; then
      echo "[WARN] 볼트 경로는 비워둘 수 없습니다."
      continue
    fi
    VAULT_ROOT="$(expand_path "$answer")"
    if [[ -d "$VAULT_ROOT" ]]; then
      mkdir -p "$VAULT_ROOT/knowledge" "$VAULT_ROOT/inbox" "$VAULT_ROOT/_quarantine"
      break
    fi
    echo "[ERROR] 볼트 경로가 존재하지 않습니다: $VAULT_ROOT"
  done
}

prompt_lightrag_embedding_model() {
  local answer=""
  while true; do
    printf 'LightRAG 임베딩 모델을 선택하세요:\n'
    printf ' [1] OpenAI API (text-embedding-3-small) — API 키 필요\n'
    printf ' [2] 로컬 모델 (sentence-transformers/all-MiniLM-L6-v2) — API 키 불필요\n'
    printf ' [Enter] 기본값: OpenAI API\n'
    read -r -p "> " answer
    answer="${answer:-1}"
    case "$answer" in
      1)
        EMBEDDING_BACKEND="api"
        LIGHTRAG_EMBEDDING_MODEL="openai"
        LIGHTRAG_START_COMMAND="lightrag serve --host 127.0.0.1 --port 9621 --working-dir ./data/lightrag_store"
        break
        ;;
      2)
        EMBEDDING_BACKEND="local"
        LIGHTRAG_EMBEDDING_MODEL="local"
        echo "[INFO] Installing sentence-transformers and torch for local LightRAG embeddings..."
        "$PYTHON_BIN" -m pip install sentence-transformers torch
        echo "[INFO] 로컬 모델은 첫 기동 시 자동 다운로드될 수 있습니다."
        LIGHTRAG_START_COMMAND="lightrag serve --host 127.0.0.1 --port 9621 --working-dir ./data/lightrag_store --embedding-model sentence-transformers/all-MiniLM-L6-v2"
        break
        ;;
      *)
        echo "[ERROR] 1, 2, 또는 Enter만 입력하세요."
        ;;
    esac
  done
}

ensure_openai_api_key_for_lightrag() {
  local existing_key=""
  if existing_key="$(existing_env_value OPENAI_API_KEY 2>/dev/null)"; then
    OPENAI_API_KEY="$existing_key"
    return 0
  fi
  while true; do
    read -r -p "OpenAI API 키를 입력하세요: " OPENAI_API_KEY
    OPENAI_API_KEY="${OPENAI_API_KEY:-}"
    if [[ -n "$OPENAI_API_KEY" ]]; then
      return 0
    fi
    echo "[ERROR] OpenAI API 키가 필요합니다."
  done
}

prompt_optional_notion_settings() {
  read -r -p "Notion API 키 (나중에 설정하려면 Enter): " NOTION_API_KEY
  NOTION_API_KEY="${NOTION_API_KEY:-}"

  local notion_url=""
  local existing_key=""
  if [[ -z "$NOTION_API_KEY" ]] && existing_key="$(existing_env_value NOTION_API_KEY 2>/dev/null)"; then
    NOTION_API_KEY="$existing_key"
  fi
  while true; do
    read -r -p "동기화할 Notion DB URL을 입력하세요 (나중에 설정하려면 Enter): " notion_url
    notion_url="${notion_url:-}"
    if [[ -z "$notion_url" ]]; then
      NOTION_DB_ID=""
      return 0
    fi
    if NOTION_DB_ID="$(extract_notion_db_id "$notion_url" 2>/dev/null)"; then
      echo "[INFO] Notion DB ID를 추출했습니다."
      return 0
    fi
    echo "[ERROR] URL에서 32자리 Notion DB ID를 찾지 못했습니다. 다시 입력하거나 Enter로 건너뛰세요."
  done
}

backup_if_exists() {
  local target="$1"
  if [[ -f "$target" ]]; then
    local backup="$target.bak.$(date +%Y%m%d%H%M%S)"
    cp "$target" "$backup"
    echo "[INFO] Backed up existing $(basename "$target") to $(basename "$backup")"
  fi
}

NOTION_SYNC_PROPERTIES_JSON='null'
NOTION_SYNC_PROPERTIES_SUMMARY='not configured'

prompt_vault_root
prompt_lightrag_embedding_model
OPENAI_API_KEY=""
if [[ "$LIGHTRAG_EMBEDDING_MODEL" == "openai" ]]; then
  ensure_openai_api_key_for_lightrag
fi
prompt_optional_notion_settings
prompt_notion_sync_properties
read -r -p "LightRAG 서버를 지금 기동할까요? [y/N]: " START_LIGHTRAG_NOW
START_LIGHTRAG_NOW="$(printf '%s' "${START_LIGHTRAG_NOW:-N}" | tr '[:upper:]' '[:lower:]')"

mkdir -p "$LIGHTRAG_WORKING_DIR"
backup_if_exists "$PROJECT_ROOT/config.yaml"
backup_if_exists "$PROJECT_ROOT/.env"

export HM_SETUP_VAULT_ROOT="$VAULT_ROOT"
export HM_SETUP_EMBEDDING_BACKEND="$EMBEDDING_BACKEND"
export HM_SETUP_LIGHTRAG_ENDPOINT="$LIGHTRAG_ENDPOINT"
export HM_SETUP_LIGHTRAG_EMBEDDING_MODEL="$LIGHTRAG_EMBEDDING_MODEL"
export HM_SETUP_LIGHTRAG_WORKING_DIR="$LIGHTRAG_WORKING_DIR_REL"
export HM_SETUP_NOTION_API_KEY="$NOTION_API_KEY"
export HM_SETUP_NOTION_DB_ID="${NOTION_DB_ID:-}"
export HM_SETUP_NOTION_SYNC_PROPERTIES_JSON="$NOTION_SYNC_PROPERTIES_JSON"
export HM_SETUP_OPENAI_API_KEY="$OPENAI_API_KEY"

"$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

project_root = Path.cwd()
config_path = project_root / 'config.yaml'
env_path = project_root / '.env'

vault_root = os.environ['HM_SETUP_VAULT_ROOT']
embedding_backend = os.environ['HM_SETUP_EMBEDDING_BACKEND']
lightrag_endpoint = os.environ['HM_SETUP_LIGHTRAG_ENDPOINT']
lightrag_embedding_model = os.environ['HM_SETUP_LIGHTRAG_EMBEDDING_MODEL']
lightrag_working_dir = os.environ['HM_SETUP_LIGHTRAG_WORKING_DIR']
notion_api_key = os.environ.get('HM_SETUP_NOTION_API_KEY', '')
notion_db_id = os.environ.get('HM_SETUP_NOTION_DB_ID', '')
notion_sync_properties = json.loads(os.environ.get('HM_SETUP_NOTION_SYNC_PROPERTIES_JSON', 'null'))
openai_api_key = os.environ.get('HM_SETUP_OPENAI_API_KEY', '')

def q(value: str) -> str:
    return json.dumps(value)

def render_notion_database_block(database_id: str, sync_properties: object) -> str:
    lines = [
        '  databases:',
        '    # Notion에서 DB 열기 → URL의 notion.so/ 뒤 32자리 ID를 복사하세요.',
        '    - name: "Primary Notion DB"',
        f'      id: {q(database_id)}',
        '      type: knowledge',
    ]
    if sync_properties is None:
        lines.append('      sync_properties: null')
    elif isinstance(sync_properties, list) and not sync_properties:
        lines.append('      sync_properties: []')
    elif isinstance(sync_properties, list):
        lines.append('      sync_properties:')
        for item in sync_properties:
            lines.append(f'        - name: {q(str(item["name"]))}')
            lines.append(f'          type: {q(str(item["type"]))}')
    else:
        lines.append('      sync_properties: null')
    return '\n'.join(lines) + '\n'

if notion_db_id:
    notion_databases_block = render_notion_database_block(notion_db_id, notion_sync_properties)
else:
    notion_databases_block = '''  databases:\n    # Notion에서 DB 열기 → URL의 notion.so/ 뒤 32자리 ID를 복사하세요.\n    - name: "내 DB 이름"\n      id: "${DB_ID}"\n      type: knowledge\n'''

config_content = f"""resource_package: plugins.memory.hermes_memory.config.resources
resource_system_root: _system
vault_root: {q(vault_root)}
skills_root: \"./skills\"
quarantine_dirname: _quarantine
timezone: UTC
log_level: INFO
wikilink_max_links: 2
wikilink_top_k: 8
wikilink_score_threshold: 0.0
openclaw_config_path: \"~/.openclaw/openclaw.json\"

notion:
  api_key: {q(notion_api_key)}
  service_name: notion
  timeout_seconds: 30.0
  page_size: 100
{notion_databases_block}
embedding:
  backend: {q(embedding_backend)}
  api:
    provider: openai
    model: text-embedding-3-small
    base_url:
    api_key: {q(openai_api_key)}
    service_name: openai
    dimensions:
    timeout_seconds: 30.0
  local:
    model_name: sentence-transformers/all-MiniLM-L6-v2
    device:
    normalize: false
    local_files_only: false
    batch_size: 32

lightrag:
  endpoint: {q(lightrag_endpoint)}
  base_url: {q(lightrag_endpoint)}
  embedding_model: {q(lightrag_embedding_model)}
  working_dir: {q(lightrag_working_dir)}
  query_path: /query
  upsert_path: /documents/texts
  delete_path: /documents/delete_document
  timeout_seconds: 30.0

obsidian_writer:
  mode: fs
  vault_name:
  advanced_uri_base: obsidian://advanced-uri
  filelock_timeout_seconds: 5.0

llm:
  provider: openai
  openai:
    model: gpt-5.4
    base_url:
    api_key: {q(openai_api_key)}
    service_name: openai
    timeout_seconds: 60.0
  anthropic:
    model:
    api_key:
    service_name: anthropic
    timeout_seconds: 60.0

gdrive_mcp:
  enabled: false
  server_name: gdrive
  timeout_seconds: 30.0

inbox:
  similarity_top_k: 5
  similarity_threshold: 0.85
  merge_queue_filename: .hermes-inbox-merge-queue.jsonl

mcp:
  server_name: hermes_memory_provider
  server_version: 0.14.0
  instructions: >-
    Hermes memory provider MCP server. Exposes search, sync, inbox submit,
    and status tools over stdio.
  transport: stdio
"""

env_content = f"""HERMES_MEMORY_CONFIG_FILE=./config.yaml
HERMES_MEMORY_VAULT_ROOT={vault_root}
HERMES_MEMORY_SKILLS_ROOT=./skills
HERMES_MEMORY_OPENCLAW_CONFIG_PATH=~/.openclaw/openclaw.json
HERMES_MEMORY_EMBEDDING__BACKEND={embedding_backend}
HERMES_MEMORY_LIGHTRAG__ENDPOINT={lightrag_endpoint}
HERMES_MEMORY_LIGHTRAG__BASE_URL={lightrag_endpoint}
HERMES_MEMORY_LIGHTRAG__EMBEDDING_MODEL={lightrag_embedding_model}
HERMES_MEMORY_LIGHTRAG__WORKING_DIR={lightrag_working_dir}
NOTION_API_KEY={notion_api_key}
OPENAI_API_KEY={openai_api_key}
"""

config_path.write_text(config_content, encoding='utf-8')
env_path.write_text(env_content, encoding='utf-8')
print(f"[INFO] Wrote {config_path}")
print(f"[INFO] Wrote {env_path}")
PY

LIGHTRAG_STATUS="skipped"
if [[ "$START_LIGHTRAG_NOW" == "y" || "$START_LIGHTRAG_NOW" == "yes" ]]; then
  echo "[INFO] Starting LightRAG with nohup..."
  if [[ "$LIGHTRAG_EMBEDDING_MODEL" == "openai" && -n "$OPENAI_API_KEY" ]]; then
    OPENAI_API_KEY="$OPENAI_API_KEY" nohup bash -lc "cd '$PROJECT_ROOT' && $LIGHTRAG_START_COMMAND" >"$LIGHTRAG_LOG_PATH" 2>&1 &
  else
    nohup bash -lc "cd '$PROJECT_ROOT' && $LIGHTRAG_START_COMMAND" >"$LIGHTRAG_LOG_PATH" 2>&1 &
  fi
  sleep 3
  if curl --fail --silent --show-error "$LIGHTRAG_ENDPOINT/openapi.json" >/dev/null; then
    echo "[INFO] LightRAG 서버 응답 확인 성공"
    LIGHTRAG_STATUS="started"
  else
    echo "[WARN] LightRAG 서버 응답 확인 실패. 로그를 확인하세요: $LIGHTRAG_LOG_PATH"
    LIGHTRAG_STATUS="failed"
  fi
else
  echo "[INFO] LightRAG start command: $LIGHTRAG_START_COMMAND"
  echo "[INFO] 나중에 위 명령으로 기동하세요"
fi

DOCTOR_EXIT_CODE=0
set +e
if command -v hermes-memory-doctor >/dev/null 2>&1; then
  hermes-memory-doctor --config "$PROJECT_ROOT/config.yaml"
  DOCTOR_EXIT_CODE=$?
else
  "$PYTHON_BIN" - <<'PY'
from hermes_memory.cli import main
raise SystemExit(main(['--config', 'config.yaml']))
PY
  DOCTOR_EXIT_CODE=$?
fi
set -e

echo
echo "[SUMMARY]"
echo "- Vault root: $VAULT_ROOT"
echo "- Embedding backend: $EMBEDDING_BACKEND"
echo "- LightRAG endpoint: $LIGHTRAG_ENDPOINT"
echo "- LightRAG embedding model: $LIGHTRAG_EMBEDDING_MODEL"
echo "- LightRAG working dir: $LIGHTRAG_WORKING_DIR_REL"
echo "- Notion sync properties: $NOTION_SYNC_PROPERTIES_SUMMARY"
echo "- LightRAG status: $LIGHTRAG_STATUS"
echo "- Created/verified directories: knowledge/, inbox/, _quarantine/, data/lightrag_store/"
echo "- Config file: $PROJECT_ROOT/config.yaml"
echo "- Env file: $PROJECT_ROOT/.env"
echo "- Doctor exit code: $DOCTOR_EXIT_CODE"

if [[ "$DOCTOR_EXIT_CODE" -ne 0 ]]; then
  echo "[WARN] Doctor reported one or more FAIL checks. Fill missing secrets or start LightRAG, then rerun hermes-memory-doctor --config ./config.yaml"
fi
