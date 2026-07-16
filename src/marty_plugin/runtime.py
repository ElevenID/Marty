"""Minimal artifact-native runtime for the Marty MMF plugin package."""

from importlib.metadata import version

from fastapi import FastAPI

from .plugin import MartyPlugin


app = FastAPI(title="Marty MMF Plugin", docs_url=None, redoc_url=None)


@app.get("/health")
async def health() -> dict[str, str]:
    """Report that the released package and its MMF entry point are loadable."""
    metadata = MartyPlugin().get_metadata()
    return {
        "status": "healthy",
        "component": metadata.name,
        "version": version("marty-trust-pki-plugin"),
    }


@app.get("/ready")
async def ready() -> dict[str, str]:
    return await health()


@app.get("/startup")
async def startup() -> dict[str, str]:
    return await health()
