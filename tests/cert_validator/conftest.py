import importlib

collect_ignore_glob = []

try:
    importlib.import_module("certvalidator")
except (ImportError, OSError):
    collect_ignore_glob = ["test_*.py"]