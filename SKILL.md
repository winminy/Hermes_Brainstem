---
name: hermes-memory-provider
description: >
  Obsidian-backed memory provider with inbox-first note persistence, optional
  Notion sync, LightRAG-backed semantic search, and MCP tools for sync/search/status.
version: 0.14.0
author: Nous Research
auto_setup: true
tags:
  - memory
  - obsidian
  - notion
  - mcp
  - lightrag
  - search
  - sync
---

# Hermes Memory Provider

Hermes Memory Provider stores durable notes in an Obsidian vault, routes new
entries through `inbox/`, and exposes `sync`, `search`, `inbox_submit`, and
`status` over MCP.

## Setup

Preferred install path:

```bash
bash setup.sh
```

If interactive setup is not possible, use the documented fallback:

```bash
python -m pip install -e ".[dev]"
python -m pip install -e ".[embedding-api]"
python -m pip install lightrag-hku
cp config.example.yaml config.yaml
cp env.example .env
mkdir -p data/lightrag_store
```

Then configure:
- `vault_root` in `config.yaml`
- `embedding.backend` as `api` or `local`
- optional `NOTION_API_KEY` and `OPENAI_API_KEY` in `.env`

Automatic onboarding uses `SETUP_PROMPT.md` to collect the **Notion Integration Token**, optional **Notion DB URL**, LightRAG embedding choice,
동기화 주기/`cron` preference, and whether to run a 최초 동기화 dry-run. If a
value is unknown, leave it blank and configure `config.yaml` later.

## Run

Start the MCP server:

```bash
python -m plugins.memory.hermes_memory.mcp.server
```

Available tools:
- `search`
- `sync`
- `inbox_submit`
- `status`

## Safety

- Prefer `hermes-memory-doctor --config ./config.yaml` after setup.
- Run only dry-run sync before any real sync.
- Do not perform real external writes without explicit user approval.
