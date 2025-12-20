"""
API router for v1 endpoints
"""

from app.api.api_v1.endpoints import crl, deviationlist, dsclist, masterlist, sync
from fastapi import APIRouter

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(masterlist.router, prefix="/masterlist", tags=["PKD"])
api_router.include_router(dsclist.router, prefix="/dsclist", tags=["PKD"])
api_router.include_router(crl.router, prefix="/crl", tags=["PKD"])
api_router.include_router(deviationlist.router, prefix="/deviationlist", tags=["PKD"])
api_router.include_router(sync.router, prefix="/sync", tags=["PKD"])
