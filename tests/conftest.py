from __future__ import annotations

import importlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CODE_ROOT = ROOT / 'code'
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

existing_plugins = sys.modules.get('plugins')
if existing_plugins is not None:
    module_path = getattr(existing_plugins, '__file__', '') or ''
    if 'site-packages' in module_path and str(CODE_ROOT) not in module_path:
        sys.modules.pop('plugins', None)
        sys.modules.pop('plugins.memory', None)
        sys.modules.pop('plugins.memory.hermes_memory', None)

importlib.invalidate_caches()
