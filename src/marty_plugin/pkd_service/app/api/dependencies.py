"""
API dependencies for the PKD service
"""

import aiosqlite
from app.db.database import get_db_connection
from app.services.crl_service import CRLService
from app.services.deviationlist_service import DeviationListService
from app.services.dsclist_service import DSCListService
from app.services.masterlist_service import MasterListService
from fastapi import Depends


async def get_masterlist_service(
    db_connection: aiosqlite.Connection = Depends(get_db_connection),
) -> MasterListService:
    """
    Dependency for MasterListService with a database connection
    """
    return MasterListService(db_connection)


async def get_crl_service(
    db_connection: aiosqlite.Connection = Depends(get_db_connection),
) -> CRLService:
    """
    Dependency for CRLService with a database connection
    """
    return CRLService(db_connection)


async def get_dsclist_service(
    db_connection: aiosqlite.Connection = Depends(get_db_connection),
) -> DSCListService:
    """
    Dependency for DSCListService with a database connection
    """
    return DSCListService(db_connection)


async def get_deviationlist_service(
    db_connection: aiosqlite.Connection = Depends(get_db_connection),
) -> DeviationListService:
    """
    Dependency for DeviationListService with a database connection
    """
    return DeviationListService(db_connection)
