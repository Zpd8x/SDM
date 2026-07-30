from __future__ import annotations

import importlib.util
import json
import traceback
from dataclasses import dataclass, asdict
from pathlib import Path
from types import ModuleType
from typing import Any

PLUGIN_API_VERSION = 1


@dataclass(slots=True)
class PluginInfo:
    plugin_id: str
    name: str
    version: str
    path: str
    enabled: bool
    loaded: bool = False
    error: str = ""
    capabilities: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["capabilities"] = list(self.capabilities)
        return data


class PluginManager:
    """Fault-isolated local plugin loader.

    A plugin is a folder containing plugin.json and plugin.py. The Python module
    may expose register(context) and return a mapping of capabilities. Failures
    are recorded and never abort SDM startup.
    """

    def __init__(self, plugin_root: str | Path, settings_path: str | Path | None = None):
        self.plugin_root = Path(plugin_root)
        self.settings_path = Path(settings_path) if settings_path else self.plugin_root / "plugins.json"
        self._settings = self._load_settings()
        self._modules: dict[str, ModuleType] = {}
        self._plugins: dict[str, PluginInfo] = {}

    def _load_settings(self) -> dict[str, bool]:
        try:
            raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return {str(k): bool(v) for k, v in raw.items()}
        except (OSError, ValueError, TypeError):
            pass
        return {}

    def _save_settings(self) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(
            json.dumps(self._settings, indent=2, sort_keys=True), encoding="utf-8"
        )

    def discover(self) -> list[PluginInfo]:
        self.plugin_root.mkdir(parents=True, exist_ok=True)
        found: dict[str, PluginInfo] = {}
        for manifest_path in sorted(self.plugin_root.glob("*/plugin.json")):
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                plugin_id = str(payload["id"]).strip()
                if not plugin_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for ch in plugin_id):
                    raise ValueError("invalid plugin id")
                api = int(payload.get("api_version", 0))
                if api != PLUGIN_API_VERSION:
                    raise ValueError(f"unsupported API version {api}")
                entry = manifest_path.parent / str(payload.get("entry", "plugin.py"))
                if not entry.is_file():
                    raise ValueError("plugin entry file is missing")
                enabled = self._settings.get(plugin_id, bool(payload.get("enabled", True)))
                found[plugin_id] = PluginInfo(
                    plugin_id=plugin_id,
                    name=str(payload.get("name", plugin_id)),
                    version=str(payload.get("version", "0.0.0")),
                    path=str(entry),
                    enabled=enabled,
                    capabilities=tuple(str(x) for x in payload.get("capabilities", []) if str(x)),
                )
            except Exception as exc:
                fallback_id = manifest_path.parent.name
                found[fallback_id] = PluginInfo(
                    plugin_id=fallback_id,
                    name=fallback_id,
                    version="unknown",
                    path=str(manifest_path.parent),
                    enabled=False,
                    error=str(exc),
                )
        self._plugins = found
        return list(found.values())

    def load_enabled(self, context: dict[str, Any] | None = None) -> list[PluginInfo]:
        if not self._plugins:
            self.discover()
        context = context if context is not None else {}
        context.setdefault("plugin_api_version", PLUGIN_API_VERSION)
        for info in self._plugins.values():
            if not info.enabled or info.error:
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"sdm_plugin_{info.plugin_id}", info.path)
                if spec is None or spec.loader is None:
                    raise RuntimeError("unable to create module specification")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                register = getattr(module, "register", None)
                if callable(register):
                    register(context)
                self._modules[info.plugin_id] = module
                info.loaded = True
                info.error = ""
            except Exception:
                info.loaded = False
                info.error = traceback.format_exc(limit=8)
        return list(self._plugins.values())

    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        self._settings[str(plugin_id)] = bool(enabled)
        if plugin_id in self._plugins:
            self._plugins[plugin_id].enabled = bool(enabled)
        self._save_settings()

    def list_plugins(self) -> list[PluginInfo]:
        if not self._plugins:
            return self.discover()
        return list(self._plugins.values())
