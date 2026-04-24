from __future__ import annotations

from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings
from plugins.memory.hermes_memory.interpreter.hook_router import HookRouter


def test_hook_router_routes_notion_sync_by_triplet() -> None:
    config = ConfigLayer.from_settings(HermesMemorySettings())
    router = HookRouter(config)

    route = router.route(
        'notion_sync',
        datasource_id='${USER_INFO_DB_ID}',
        notion_type='말투',
        file_type='md',
    )

    assert route.datasource_id == '${USER_INFO_DB_ID}'
    assert route.notion_type == '말투'
    assert route.file_type == 'md'
    assert route.note_type == 'preference'
    assert route.area == 'knowledge'
