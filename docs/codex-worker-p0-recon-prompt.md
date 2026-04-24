Phase 0 RECON only for Hermes Memory Provider. Do not write code. Read these docs first:
- docs/codex-bundle/00_CORE.md
- docs/codex-bundle/P0_RECON.md

Then, using the live runtime at <runtime-root>/.local/share/uv/tools/hermes-agent/lib/python3.12/site-packages plus live user config under <runtime-root>/.hermes and <runtime-root>/obsidian, produce a compact validation summary only (no file edits) for these axes:
1) Hermes runtime plugin loading path / memory interface / hook timing
2) LightRAG presence / endpoint health / install clues
3) Notion MCP configured servers / auth location / available tools
4) LLM SDK model/provider/api key location/wrapper clues
5) Vault meta docs current state
6) Obsidian vault path / writer mode / wikilink clues

Constraints:
- No implementation or Phase 1+
- Unknowns must be called out explicitly
- Keep output compact