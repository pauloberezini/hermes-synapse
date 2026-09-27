from backend import plugins


def test_plugin_bus_api():
    assert hasattr(plugins, "hook")
    assert hasattr(plugins, "hook_async")
    assert hasattr(plugins, "collect")
    assert hasattr(plugins, "init_all")
    assert plugins.hook("definitely_missing_hook", default="ok") == "ok"
