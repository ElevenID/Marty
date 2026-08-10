"""Minimal artifact-native runtime for the Marty MMF plugin package."""

from importlib.metadata import version

from fastapi import FastAPI

from .native_backends import backend_diagnostics
from .plugin import MartyPlugin


app = FastAPI(title="Marty MMF Plugin", docs_url=None, redoc_url=None)


@app.get("/health")
async def health() -> dict[str, object]:
    """Report package, plugin, and native backend health."""
    metadata = MartyPlugin().get_metadata()
    native = backend_diagnostics()
    native_healthy = all(item["available"] for item in native.values())
    return {
        "status": "healthy" if native_healthy else "unhealthy",
        "component": metadata.name,
        "version": version("marty-trust-pki-plugin"),
        "native_backends": native,
    }


@app.get("/ready")
async def ready() -> dict[str, object]:
    return await health()


@app.get("/startup")
async def startup() -> dict[str, object]:
    return await health()
