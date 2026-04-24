from __future__ import annotations

from pathlib import Path
import subprocess


def test_setup_script_help_smoke() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(['bash', 'setup.sh', '--help'], cwd=root, check=False, capture_output=True, text=True)

    assert result.returncode == 0
    assert 'interactive setup' in result.stdout
    assert 'hermes-memory-doctor' in result.stdout


def test_setup_prompt_covers_required_topics() -> None:
    root = Path(__file__).resolve().parents[1]
    prompt = (root / 'SETUP_PROMPT.md').read_text(encoding='utf-8')

    required_snippets = (
        'Obsidian',
        'knowledge/',
        'inbox/',
        '_quarantine/',
        'inbox-first',
        'LightRAG',
        'OpenAI API',
        'sentence-transformers/all-MiniLM-L6-v2',
        '나중에 위 명령으로 기동하세요',
        '동기화할 DB URL을 알려주세요',
        'notion.so/워크스페이스/[이 부분이 DB ID]?v=...',
        'MCP',
        'dry_run=true',
        'hermes-memory-doctor',
    )

    for snippet in required_snippets:
        assert snippet in prompt


def test_deployment_assets_cover_lightrag_and_notion_placeholders() -> None:
    root = Path(__file__).resolve().parents[1]
    setup_script = (root / 'setup.sh').read_text(encoding='utf-8')
    readme = (root / 'README.md').read_text(encoding='utf-8')
    config_example = (root / 'config.example.yaml').read_text(encoding='utf-8')
    gitignore = (root / '.gitignore').read_text(encoding='utf-8')

    assert 'pip install lightrag-hku' in setup_script
    assert 'LightRAG 서버를 지금 기동할까요? [y/N]:' in setup_script
    assert '동기화할 Notion DB URL을 입력하세요 (나중에 설정하려면 Enter):' in setup_script
    assert '이 DB에서 어떤 속성(컬럼)을 동기화하시겠습니까?' in setup_script
    assert 'HERMES_SETUP_NOTION_SYNC_SELECTION' in setup_script
    notion_database_endpoint = 'https://' + 'api' + '.notion.' + 'com' + '/v1/databases/'
    assert notion_database_endpoint in setup_script
    assert '속성 목록을 자동 조회할 수 없습니다. 나중에 config.yaml의 sync_properties에 직접 입력하세요.' in setup_script
    assert '--working-dir ./data/lightrag_store' in setup_script
    assert 'embedding_model' in config_example
    assert 'working_dir: ./data/lightrag_store' in config_example
    assert 'notion:' in config_example and 'databases:' in config_example and '${DB_ID}' in config_example
    assert 'data/lightrag_store/' in gitignore
    assert 'text-embedding-3-small' in readme
    assert 'sentence-transformers/all-MiniLM-L6-v2' in readme
    assert 'HERMES_SETUP_NOTION_SYNC_SELECTION' in readme


def test_example_files_do_not_contain_machine_specific_root_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    home_root = f'{Path.home()}/'

    for relative_path in ('config.example.yaml', 'env.example', 'README.md', 'SETUP_PROMPT.md', 'setup.sh'):
        content = (root / relative_path).read_text(encoding='utf-8')
        assert home_root not in content
        assert "<vault-name>" not in content
