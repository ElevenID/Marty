"""
Wallet Backup API Module

Provides encrypted backup and restore functionality for wallet data.
Uses client-side encryption with server-side storage.

The encryption key is derived from the device's RSA keypair using HKDF,
ensuring only the device with the private key can decrypt the backup.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, LargeBinary, String, select
from sqlalchemy.orm import declarative_base

if TYPE_CHECKING:
    from marty_common.infrastructure.database import DatabaseManager

# Create a local Base for this module
# In production, this would be imported from shared infrastructure
Base = declarative_base()


# =============================================================================
# Database Models
# =============================================================================

class WalletBackup(Base):  # type: ignore[valid-type,misc]
    """Encrypted wallet backup storage."""
    __tablename__ = "wallet_backups"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    
    # Encrypted backup data (encrypted client-side with HKDF-derived key)
    encrypted_data = Column(LargeBinary, nullable=False)
    
    # Key derivation info (public, used for verification)
    key_id = Column(String(64), nullable=False)  # SHA-256 thumbprint of public key
    
    # Backup metadata
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc))
    
    # Optional backup description
    description = Column(String(500), nullable=True)


# =============================================================================
# API Models
# =============================================================================

class BackupRequest(BaseModel):
    """Request to store an encrypted backup."""
    device_id: str = Field(..., description="Device ID that owns this backup")
    encrypted_data: str = Field(..., description="Base64-encoded encrypted backup data")
    key_id: str = Field(..., description="Key ID (SHA-256 thumbprint) used for encryption")
    description: Optional[str] = Field(None, max_length=500, description="Optional backup description")


class BackupResponse(BaseModel):
    """Response after storing backup."""
    success: bool
    backup_id: int
    version: int
    created_at: datetime
    message: str


class RestoreRequest(BaseModel):
    """Request to retrieve an encrypted backup."""
    device_id: str = Field(..., description="Device ID to retrieve backup for")
    key_id: str = Field(..., description="Key ID to verify ownership")


class RestoreResponse(BaseModel):
    """Response with encrypted backup data."""
    success: bool
    encrypted_data: str
    version: int
    created_at: datetime
    updated_at: Optional[datetime]
    description: Optional[str]


class BackupInfoResponse(BaseModel):
    """Information about existing backup without the data."""
    exists: bool
    device_id: Optional[str] = None
    key_id: Optional[str] = None
    version: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    description: Optional[str] = None


class DeleteBackupRequest(BaseModel):
    """Request to delete a backup."""
    device_id: str
    key_id: str  # Must match to authorize deletion


# =============================================================================
# API Router
# =============================================================================

router = APIRouter(prefix="/api/v1/wallet", tags=["wallet"])

# Database manager instance - should be configured on app startup
_db_manager: Optional[Any] = None


def set_database_manager(manager: Any) -> None:
    """Set the database manager for the wallet backup API."""
    global _db_manager  # noqa: PLW0603
    _db_manager = manager


def get_database_manager() -> Any:
    """Get the database manager, raising if not configured."""
    if _db_manager is None:
        raise HTTPException(
            status_code=500,
            detail="Database not configured for wallet backup API"
        )
    return _db_manager


@router.post("/backup", response_model=BackupResponse)
async def create_or_update_backup(
    request: BackupRequest,
    x_user_id: str = Header(..., alias="X-User-ID"),
):
    """
    Store or update an encrypted wallet backup.
    
    The backup data must be encrypted client-side using a key derived from
    the device's RSA keypair (using HKDF). This ensures only the device
    with the private key can decrypt the backup.
    
    If a backup already exists for this device, it will be updated.
    """
    # Validate encrypted data is valid base64
    try:
        encrypted_bytes = base64.b64decode(request.encrypted_data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid base64 encoded data") from exc
    
    if len(encrypted_bytes) == 0:
        raise HTTPException(status_code=400, detail="Encrypted data cannot be empty")
    
    if len(encrypted_bytes) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="Backup data exceeds 10MB limit")
    
    db = get_database_manager()
    async with db.session_scope() as session:
        # Check for existing backup
        result = await session.execute(
            select(WalletBackup).where(WalletBackup.device_id == request.device_id)
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            # Verify key_id matches (only the same device can update)
            if existing.key_id != request.key_id:
                raise HTTPException(
                    status_code=403,
                    detail="Key ID mismatch. Only the original device can update its backup."
                )
            
            # Update existing backup
            existing.encrypted_data = encrypted_bytes
            existing.version += 1
            existing.updated_at = datetime.now(timezone.utc)
            existing.description = request.description
            
            # Commit is handled by session_scope context manager
            await session.flush()
            await session.refresh(existing)
            
            return BackupResponse(
                success=True,
                backup_id=int(existing.id),
                version=int(existing.version),
                created_at=existing.created_at,
                message="Backup updated successfully",
            )
        else:
            # Create new backup
            backup = WalletBackup(
                device_id=request.device_id,
                user_id=x_user_id,
                encrypted_data=encrypted_bytes,
                key_id=request.key_id,
                description=request.description,
            )
            session.add(backup)
            await session.flush()
            await session.refresh(backup)
            
            return BackupResponse(
                success=True,
                backup_id=int(backup.id),
                version=int(backup.version),
                created_at=backup.created_at,
                message="Backup created successfully",
            )


@router.post("/restore", response_model=RestoreResponse)
async def restore_backup(request: RestoreRequest):
    """
    Retrieve an encrypted wallet backup.
    
    The caller must provide the correct key_id to retrieve the backup.
    This provides basic ownership verification - the caller must know
    the key ID that was used when creating the backup.
    
    The returned data is still encrypted and must be decrypted client-side.
    """
    db = get_database_manager()
    async with db.session_scope() as session:
        result = await session.execute(
            select(WalletBackup).where(WalletBackup.device_id == request.device_id)
        )
        backup = result.scalar_one_or_none()
        
        if not backup:
            raise HTTPException(status_code=404, detail="No backup found for this device")
        
        if backup.key_id != request.key_id:
            raise HTTPException(status_code=403, detail="Key ID mismatch")
        
        return RestoreResponse(
            success=True,
            encrypted_data=base64.b64encode(backup.encrypted_data).decode('utf-8'),
            version=int(backup.version),
            created_at=backup.created_at,
            updated_at=backup.updated_at,
            description=backup.description,
        )


@router.get("/backup/info", response_model=BackupInfoResponse)
async def get_backup_info(
    device_id: str,
    x_user_id: str = Header(..., alias="X-User-ID"),
):
    """
    Get information about an existing backup without retrieving the data.
    
    This can be used to check if a backup exists and its version before
    deciding to restore or create a new backup.
    """
    db = get_database_manager()
    async with db.session_scope() as session:
        result = await session.execute(
            select(WalletBackup).where(WalletBackup.device_id == device_id)
        )
        backup = result.scalar_one_or_none()
        
        if not backup:
            return BackupInfoResponse(exists=False)
        
        # Only return info if user matches
        if backup.user_id != x_user_id:
            return BackupInfoResponse(exists=False)
        
        return BackupInfoResponse(
            exists=True,
            device_id=str(backup.device_id),
            key_id=str(backup.key_id),
            version=int(backup.version),
            created_at=backup.created_at,
            updated_at=backup.updated_at,
            description=backup.description,
        )


@router.delete("/backup")
async def delete_backup(
    request: DeleteBackupRequest,
    x_user_id: str = Header(..., alias="X-User-ID"),
):
    """
    Delete an encrypted wallet backup.
    
    Requires both the device_id and correct key_id to authorize deletion.
    """
    db = get_database_manager()
    async with db.session_scope() as session:
        result = await session.execute(
            select(WalletBackup).where(WalletBackup.device_id == request.device_id)
        )
        backup = result.scalar_one_or_none()
        
        if not backup:
            raise HTTPException(status_code=404, detail="No backup found for this device")
        
        if backup.key_id != request.key_id:
            raise HTTPException(status_code=403, detail="Key ID mismatch")
        
        if backup.user_id != x_user_id:
            raise HTTPException(status_code=403, detail="User ID mismatch")
        
        await session.delete(backup)
        # Commit handled by session_scope
        
        return {"success": True, "message": "Backup deleted successfully"}
