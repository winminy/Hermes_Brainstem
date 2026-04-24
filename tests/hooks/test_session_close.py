from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, cast

from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings
from plugins.memory.hermes_memory.core.frontmatter import FrontmatterCodec, MarkdownDocument
from plugins.memory.hermes_memory.core.hasher import sha256_hexdigest
from plugins.memory.hermes_memory.core.models import FrontmatterModel
from plugins.memory.hermes_memory.hooks.session_close import run_session_close
from plugins.memory.hermes_memory.inbox import InboxProcessResult
from plugins.memory.hermes_memory.pipeline import SyncBatchResult


@dataclass(frozen=True, slots=True)
class FakeDatasourceSpec:
    name: str
    scan_mode: str | None


class FakePipeline:
    def __init__(self, result: SyncBatchResult) -> None:
        self._result = result
        self.calls: list[dict[str, object]] = []

    def incremental_sync(self, *, datasources: tuple[str, ...], vault_root: Path, dry_run: bool) -> SyncBatchResult:
        self.calls.append({'datasources': datasources, 'vault_root': vault_root, 'dry_run': dry_run})
        return self._result


class FakeInboxRunner:
    def __init__(self, result: InboxProcessResult) -> None:
        self._result = result
        self.calls: list[dict[str, object]] = []

    def review_existing_entry(
        self,
        entry_path: Path,
        *,
        vault_root: Path,
        dry_run: bool = False,
        notification_reason_tag: str | None = None,
    ) -> InboxProcessResult:
        self.calls.append(
            {
                'entry_path': entry_path,
                'vault_root': vault_root,
                'dry_run': dry_run,
                'notification_reason_tag': notification_reason_tag,
            }
        )
        return self._result


class FakeNotionBackend:
    def __init__(self, specs: tuple[FakeDatasourceSpec, ...]) -> None:
        self.datasources = {spec.name: spec for spec in specs}


class FakeServices:
    def __init__(self, *, config: ConfigLayer, pipeline: FakePipeline, inbox_runner: FakeInboxRunner, notion_backend: FakeNotionBackend) -> None:
        self.config = config
        self.pipeline = pipeline
        self.inbox_runner = inbox_runner
        self.notion_backend = notion_backend


def test_session_close_runs_incremental_sync_and_consumes_merge_queue(tmp_path: Path) -> None:
    config = _config(tmp_path)
    note_path = _write_inbox_note(config, tmp_path, title='draft-memory', body='# Draft memory')
    queue_path = tmp_path / 'inbox' / config.settings.inbox.merge_queue_filename
    queue_path.write_text(
        json.dumps({'entry_path': str(note_path), 'title': 'draft-memory', 'source_hash': 'abc123'}, ensure_ascii=False) + '\n',
        encoding='utf-8',
    )
    pipeline = FakePipeline(
        SyncBatchResult(
            mode='incremental',
            datasources=('Sub-task DB',),
            entries=(),
            counts={'written': 1},
        )
    )
    inbox_runner = FakeInboxRunner(
        InboxProcessResult(
            status='written',
            inbox_path=None,
            knowledge_path='knowledge/draft-memory.md',
            quarantine_path=None,
            reason=None,
            reason_tag=None,
            queue_path=None,
        )
    )
    services = FakeServices(
        config=config,
        pipeline=pipeline,
        inbox_runner=inbox_runner,
        notion_backend=FakeNotionBackend((FakeDatasourceSpec(name='Sub-task DB', scan_mode='daily_auto'),)),
    )

    result = run_session_close(
        session_id='session-42',
        conversation_history=[
            {
                'attachments': [
                    {'file_id': 'keep-me', 'scope': 'knowledge'},
                    {'file_id': 'drop-me', 'scope': 'skill'},
                ]
            }
        ],
        model='gpt-5.4',
        platform='discord',
        services=cast(Any, services),
        vault_root=tmp_path,
    )

    assert pipeline.calls == [{'datasources': ('Sub-task DB',), 'vault_root': tmp_path, 'dry_run': False}]
    assert inbox_runner.calls[0]['entry_path'] == note_path
    assert inbox_runner.calls[0]['notification_reason_tag'] == 'needs-confirmation'
    assert result.entries[0].merge_queue_action == 'consumed-promoted'
    assert result.entries[0].knowledge_path == 'knowledge/draft-memory.md'
    assert result.audited_file_hashes == (sha256_hexdigest('keep-me'),)
    assert not queue_path.exists()
    audit_lines = (tmp_path / 'inbox' / '.hermes-session-close-audit.jsonl').read_text(encoding='utf-8').splitlines()
    assert len(audit_lines) == 1
    audit_record = json.loads(audit_lines[0])
    assert audit_record['session_id'] == 'session-42'
    assert audit_record['audited_file_hashes'] == [sha256_hexdigest('keep-me')]

    duplicate = run_session_close(
        session_id='session-42',
        conversation_history=[],
        model='gpt-5.4',
        platform='discord',
        services=cast(Any, services),
        vault_root=tmp_path,
    )
    assert duplicate.duplicate_audit is True
    assert len((tmp_path / 'inbox' / '.hermes-session-close-audit.jsonl').read_text(encoding='utf-8').splitlines()) == 1


def _config(tmp_path: Path) -> ConfigLayer:
    settings = HermesMemorySettings(vault_root=tmp_path, skills_root=tmp_path / 'skills', log_level='INFO')
    return ConfigLayer.from_settings(settings)


def _write_inbox_note(config: ConfigLayer, vault_root: Path, *, title: str, body: str) -> Path:
    codec = FrontmatterCodec(config)
    frontmatter = FrontmatterModel.from_data(
        {
            'uuid': 'obs:20260424T0641',
            'area': 'inbox',
            'type': 'memo',
            'tags': [],
            'date': '2026-04-24',
            'updated': '2026-04-24',
            'source': ['session:test-session'],
            'source_type': '',
            'file_type': 'md',
        },
        tag_registry=config.tag_registry,
    )
    path = vault_root / 'inbox' / f'{title}.md'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(codec.dumps(MarkdownDocument(frontmatter=frontmatter, body=body)), encoding='utf-8')
    return path
