import json
import tempfile
import unittest
from pathlib import Path

from sdm.plugins import PluginManager


class PluginManagerTests(unittest.TestCase):
    def test_discovers_and_loads_plugin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugins"
            plugin = root / "sample"
            plugin.mkdir(parents=True)
            (plugin / "plugin.json").write_text(json.dumps({
                "id": "sample", "name": "Sample", "version": "1.0", "api_version": 1,
                "entry": "plugin.py", "capabilities": ["demo"]
            }), encoding="utf-8")
            (plugin / "plugin.py").write_text("def register(context):\n    context['loaded'] = True\n", encoding="utf-8")
            context = {}
            manager = PluginManager(root)
            manager.discover()
            plugins = manager.load_enabled(context)
            self.assertTrue(plugins[0].loaded)
            self.assertTrue(context["loaded"])

    def test_broken_plugin_is_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugins"
            plugin = root / "broken"
            plugin.mkdir(parents=True)
            (plugin / "plugin.json").write_text(json.dumps({
                "id": "broken", "api_version": 1, "entry": "plugin.py"
            }), encoding="utf-8")
            (plugin / "plugin.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")
            manager = PluginManager(root)
            manager.discover()
            result = manager.load_enabled()
            self.assertFalse(result[0].loaded)
            self.assertIn("boom", result[0].error)

    def test_enable_state_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugins"
            manager = PluginManager(root)
            manager.set_enabled("x", False)
            self.assertFalse(PluginManager(root)._load_settings()["x"])
