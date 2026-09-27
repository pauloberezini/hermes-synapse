"""Generic private-plugin loader.

Any ``backend/<name>/plugin.py`` is optional. Core never imports a private
module by name — it only calls hook functions if a plugin is present.
"""

from __future__ import annotations

import importlib
import inspect
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, List, Optional

logger = logging.getLogger("hermes.plugins")


@lru_cache(maxsize=1)
def iter_plugins() -> tuple:
    mods = []
    backend_dir = Path(__file__).resolve().parent
    for child in sorted(backend_dir.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        if not (child / "plugin.py").is_file():
            continue
        try:
            mods.append(importlib.import_module(f"backend.{child.name}.plugin"))
        except Exception as exc:
            logger.warning("Skipped plugin %s: %s", child.name, exc)
    return tuple(mods)


def available() -> bool:
    return bool(iter_plugins())


def hook(name: str, *args: Any, default: Any = None, **kwargs: Any) -> Any:
    for mod in iter_plugins():
        fn = getattr(mod, name, None)
        if fn is None:
            continue
        result = fn(*args, **kwargs)
        if result is not None:
            return result
    return default


async def hook_async(name: str, *args: Any, default: Any = None, **kwargs: Any) -> Any:
    for mod in iter_plugins():
        fn = getattr(mod, name, None)
        if fn is None:
            continue
        result = fn(*args, **kwargs)
        if inspect.isawaitable(result):
            result = await result
        if result is not None:
            return result
    return default


def collect(name: str, *args: Any, **kwargs: Any) -> List[Any]:
    items: List[Any] = []
    for mod in iter_plugins():
        fn = getattr(mod, name, None)
        if fn is None:
            continue
        result = fn(*args, **kwargs)
        if not result:
            continue
        if isinstance(result, list):
            items.extend(result)
        elif isinstance(result, tuple):
            items.extend(result)
        elif isinstance(result, dict):
            items.append(result)
        else:
            items.append(result)
    return items


def init_all(scheduler_obj=None, restore_items: Optional[Iterable] = None) -> bool:
    loaded = False
    for mod in iter_plugins():
        fn = getattr(mod, "init_plugin", None)
        if fn is None:
            continue
        try:
            if fn(scheduler_obj, restore_items):
                loaded = True
        except Exception as exc:
            logger.error("Error initializing plugin %s: %s", mod.__name__, exc, exc_info=True)
    return loaded
