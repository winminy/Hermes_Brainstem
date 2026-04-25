from __future__ import annotations

from pathlib import Path

import yaml


def test_root_skill_manifest_exists_and_has_required_frontmatter() -> None:
    skill_path = Path(__file__).resolve().parent.parent / 'SKILL.md'
    text = skill_path.read_text(encoding='utf-8')

    assert text.startswith('---\n')
    _, frontmatter_text, _ = text.split('---', 2)
    payload = yaml.safe_load(frontmatter_text)

    assert isinstance(payload, dict)
    assert payload['name'] == 'hermes-memory-provider'
    assert isinstance(payload['description'], str) and payload['description'].strip()
    assert isinstance(payload['version'], str) and payload['version'].strip()
    assert isinstance(payload['tags'], list) and payload['tags']

    tags = payload['tags']
    assert all(isinstance(item, str) and item.strip() for item in tags)
