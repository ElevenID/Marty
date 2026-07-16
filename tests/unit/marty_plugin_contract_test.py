from mmf.core.plugins import BasePlugin, PluginContext, PluginStatus

from marty_plugin.plugin import MartyPlugin


def test_plugin_implements_released_mmf_contract():
    plugin = MartyPlugin()
    assert isinstance(plugin, BasePlugin)
    assert plugin.get_metadata().license == "AGPL-3.0-only"
    assert {service.name for service in plugin.get_service_definitions()} == {
        "trust-anchor",
        "pkd",
        "document-signer",
        "csca",
    }


async def test_plugin_lifecycle_uses_mmf_context():
    plugin = MartyPlugin()
    await plugin.initialize(PluginContext(plugin_id="marty", config={}))
    assert plugin.status is PluginStatus.LOADED
    await plugin.start()
    assert plugin.status is PluginStatus.ACTIVE
    assert (await plugin.health_check())["status"] == "healthy"
    await plugin.stop()
    await plugin.cleanup()
    assert plugin.status is PluginStatus.UNLOADED
