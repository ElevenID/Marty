"""
Conftest for digital_identity unit tests.

The root tests/conftest.py already installs a comprehensive
_MartyPluginCommonFinder that provides proper class stubs
(with ABCMeta-compatible BaseService, SODParsingError, etc.)
for the marty_plugin.common.* subtree.  No duplicate finder
is needed here.
"""
