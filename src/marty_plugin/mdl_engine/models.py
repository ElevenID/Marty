import datetime
import enum

from sqlalchemy import JSON, Column, DateTime, Integer, String
from sqlalchemy import Enum as SAEnum

# Removed ForeignKey and relationship as they are unused for now
from marty_plugin.shared.database import Base


class MDLStatus(enum.Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    PENDING_SIGNATURE = "pending_signature"
    DRAFT = "draft"  # Added DRAFT status


class MobileDrivingLicense(Base):
    __tablename__ = "mobile_driving_licenses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)  # Assuming a general user identifier
    device_id = Column(String, index=True, nullable=True)  # For device binding
    document_id = Column(
        String, unique=True, index=True, nullable=False
    )  # Unique ID for the mDL document itself

    issue_date = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    expiry_date = Column(DateTime, nullable=False)
    issuing_authority = Column(String, nullable=False)

    data_groups = Column(JSON, nullable=False)  # To store various mDL data elements

    status = Column(SAEnum(MDLStatus), default=MDLStatus.PENDING_SIGNATURE, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
