from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from plugins.memory.hermes_memory.backends.notion import NotionBackend
from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings
from plugins.memory.hermes_memory.config.settings import NotionDatabaseConfig, NotionSettings, SyncProperty


class FakeDataSources:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def query(self, *, data_source_id: str, page_size: int, start_cursor: str | None = None) -> dict[str, object]:
        self.calls.append({'data_source_id': data_source_id, 'page_size': page_size, 'start_cursor': start_cursor})
        if data_source_id == '${SUB_TASK_DB_ID}':
            if start_cursor is None:
                return {
                    'results': [_subtask_page('memo-1', '메모/ 리소스', relation_ids=['proj-1'])],
                    'has_more': True,
                    'next_cursor': 'cursor-1',
                }
            return {
                'results': [_subtask_page('skip-1', '휴지통')],
                'has_more': False,
                'next_cursor': None,
            }
        return {
            'results': [_user_info_page('user-1', '말투')],
            'has_more': False,
            'next_cursor': None,
        }


class FakePages:
    def retrieve(self, *, page_id: str) -> dict[str, object]:
        if page_id == 'proj-1':
            return {
                'id': page_id,
                'properties': {
                    'Name': {
                        'type': 'title',
                        'title': [{'plain_text': 'brainstemV2아키텍쳐수정'}],
                    }
                },
            }
        raise AssertionError(f'unexpected relation lookup: {page_id}')


class FakeNotionClient:
    def __init__(self) -> None:
        self.data_sources = FakeDataSources()
        self.pages = FakePages()


class CaptureClientBackend(NotionBackend):
    def __init__(self, *, config: ConfigLayer) -> None:
        super().__init__(config=config)
        self.captured_auth: str | None = None

    def _build_client(self) -> object:
        notion_settings = self._config.settings.notion
        self.captured_auth = self._config.resolve_secret(
            yaml_value=notion_settings.api_key,
            service_name=notion_settings.service_name,
            env_vars=notion_settings.env_vars,
        )
        return FakeNotionClient()


def test_notion_secret_resolution_prefers_env_then_openclaw_then_yaml(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    openclaw_path = tmp_path / 'openclaw.json'
    openclaw_path.write_text('{"skills": {"entries": {"notion": {"apiKey": "openclaw-key"}}}}', encoding='utf-8')
    base_settings = HermesMemorySettings(
        openclaw_config_path=openclaw_path,
        notion=NotionSettings(api_key='yaml-key'),
    )

    monkeypatch.delenv('NOTION_API_KEY', raising=False)
    config = ConfigLayer.from_settings(base_settings)
    assert config.resolve_secret(
        yaml_value=config.settings.notion.api_key,
        service_name=config.settings.notion.service_name,
        env_vars=config.settings.notion.env_vars,
    ) == 'openclaw-key'

    monkeypatch.setenv('NOTION_API_KEY', 'env-key')
    config = ConfigLayer.from_settings(base_settings)
    assert config.resolve_secret(
        yaml_value=config.settings.notion.api_key,
        service_name=config.settings.notion.service_name,
        env_vars=config.settings.notion.env_vars,
    ) == 'env-key'


def test_notion_backend_queries_with_pagination_and_maps_entries() -> None:
    config = ConfigLayer.from_settings(HermesMemorySettings())
    backend = NotionBackend(config=config, client=FakeNotionClient())

    raw_rows = backend.query_datasource('Sub-task DB')
    assert len(raw_rows) == 2

    subtask_entries = backend.read_vault_entries('Sub-task DB')
    assert subtask_entries == [
        {
            'title': 'memo-1',
            'body': '# memo-1\n\n## Notion properties\n- 유형: 메모/ 리소스\n- 프로젝트: brainstemV2아키텍쳐수정\n\n## Source\n- url: https://www.notion.so/memo-1',
            'area': 'knowledge',
            'type': 'memo',
            'tags': ['brainstemV2아키텍쳐수정'],
            'date': '2026-04-23',
            'updated': '2026-04-24',
            'source': ['notion:memo-1'],
            'source_type': 'notion',
            'file_type': 'md',
            'notion_page_id': 'memo-1',
            'properties': raw_rows[0]['properties'],
        }
    ]
    user_entries = backend.read_vault_entries('User Info DB')
    assert user_entries == [
        {
            'title': 'user-1',
            'body': '# user-1\n\n## Notion properties\n- 유형: 말투\n\n## Source\n- url: https://www.notion.so/user-1',
            'area': 'knowledge',
            'type': 'preference',
            'tags': ['사용자정보'],
            'date': '2026-04-23',
            'updated': '2026-04-24',
            'source': ['notion:user-1'],
            'source_type': 'notion',
            'file_type': 'md',
            'notion_page_id': 'user-1',
            'properties': _user_info_page('user-1', '말투')['properties'],
        }
    ]


def test_notion_backend_build_client_uses_resolved_secret(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    openclaw_path = tmp_path / 'openclaw.json'
    openclaw_path.write_text('{"skills": {"entries": {"notion": {"apiKey": "openclaw-key"}}}}', encoding='utf-8')
    settings = HermesMemorySettings(openclaw_config_path=openclaw_path, notion=NotionSettings(api_key='yaml-key'))
    backend = CaptureClientBackend(config=ConfigLayer.from_settings(settings))

    monkeypatch.setenv('NOTION_API_KEY', 'env-key')
    _ = backend.client

    assert backend.captured_auth == 'env-key'


def _subtask_page(page_id: str, notion_type: str, *, relation_ids: list[str] | None = None) -> dict[str, object]:
    relation_payload = [{'id': relation_id} for relation_id in relation_ids or []]
    return {
        'id': page_id,
        'url': f'https://www.notion.so/{page_id}',
        'created_time': '2026-04-23T08:35:00.000Z',
        'last_edited_time': '2026-04-24T09:00:00.000Z',
        'properties': {
            'Name': {'type': 'title', 'title': [{'plain_text': page_id}]},
            '유형': {'type': 'select', 'select': {'name': notion_type}},
            '프로젝트': {'type': 'relation', 'relation': relation_payload},
        },
    }


def _user_info_page(page_id: str, notion_type: str) -> dict[str, object]:
    return {
        'id': page_id,
        'url': f'https://www.notion.so/{page_id}',
        'created_time': '2026-04-23T08:35:00.000Z',
        'last_edited_time': '2026-04-24T09:00:00.000Z',
        'properties': {
            'Name': {'type': 'title', 'title': [{'plain_text': page_id}]},
            '유형': {'type': 'select', 'select': {'name': notion_type}},
        },
    }


def test_sync_properties_selection_modes_and_type_parsing() -> None:
    settings = HermesMemorySettings(
        notion=NotionSettings(
            databases=[
                NotionDatabaseConfig(name='all', id='all-db', type='knowledge'),
                NotionDatabaseConfig(
                    name='selected',
                    id='selected-db',
                    type='knowledge',
                    sync_properties=[
                        SyncProperty(name='제목', type='title'),
                        SyncProperty(name='메모', type='rich_text'),
                        SyncProperty(name='마감일', type='date'),
                        SyncProperty(name='담당자', type='person'),
                        SyncProperty(name='관련 문서', type='relation'),
                    ],
                ),
                NotionDatabaseConfig(name='title-only', id='title-only-db', type='knowledge', sync_properties=[]),
                NotionDatabaseConfig(
                    name='mapped',
                    id='mapped-db',
                    mapping_property='유형',
                    mapping={'메모/ 리소스': 'memo'},
                    sync_properties=[SyncProperty(name='메모', type='rich_text')],
                ),
            ]
        )
    )
    backend = NotionBackend(config=ConfigLayer.from_settings(settings), client=_rendering_client())
    page = _rich_page('page-1')

    all_entry = backend._page_to_vault_entry(backend.datasources['all'], page)
    assert '- 메모: 상세 메모' in all_entry['body']
    assert '- 마감일: 2026-05-01' in all_entry['body']
    assert '- 담당자: Alice' in all_entry['body']
    assert '- 관련 문서: 관련 문서 제목' in all_entry['body']

    selected_entry = backend._page_to_vault_entry(backend.datasources['selected'], page)
    assert '- 제목: 선택 노트' in selected_entry['body']
    assert '- 메모: 상세 메모' in selected_entry['body']
    assert '- 마감일: 2026-05-01' in selected_entry['body']
    assert '- 담당자: Alice' in selected_entry['body']
    assert '- 관련 문서: 관련 문서 제목' in selected_entry['body']
    assert '- 유형: 메모/ 리소스' not in selected_entry['body']

    title_only_entry = backend._page_to_vault_entry(backend.datasources['title-only'], page)
    assert title_only_entry['body'] == '# 선택 노트'

    mapped_entry = backend._page_to_vault_entry(backend.datasources['mapped'], page)
    assert mapped_entry['type'] == 'memo'
    assert '- 메모: 상세 메모' in mapped_entry['body']
    assert '- 유형: 메모/ 리소스' not in mapped_entry['body']


def _rendering_client() -> object:
    class RenderingPages:
        def retrieve(self, *, page_id: str) -> dict[str, object]:
            if page_id == 'rel-1':
                return {
                    'id': page_id,
                    'properties': {'Name': {'type': 'title', 'title': [{'plain_text': '관련 문서 제목'}]}},
                }
            raise AssertionError(f'unexpected relation lookup: {page_id}')

    class RenderingClient:
        def __init__(self) -> None:
            self.pages = RenderingPages()

    return RenderingClient()


def _rich_page(page_id: str) -> dict[str, object]:
    return {
        'id': page_id,
        'url': f'https://www.notion.so/{page_id}',
        'created_time': '2026-04-23T08:35:00.000Z',
        'last_edited_time': '2026-04-24T09:00:00.000Z',
        'properties': {
            '제목': {'type': 'title', 'title': [{'plain_text': '선택 노트'}]},
            '유형': {'type': 'select', 'select': {'name': '메모/ 리소스'}},
            '메모': {'type': 'rich_text', 'rich_text': [{'plain_text': '상세 메모'}]},
            '마감일': {'type': 'date', 'date': {'start': '2026-05-01'}},
            '담당자': {'type': 'person', 'people': [{'name': 'Alice'}]},
            '관련 문서': {'type': 'relation', 'relation': [{'id': 'rel-1'}]},
        },
    }
