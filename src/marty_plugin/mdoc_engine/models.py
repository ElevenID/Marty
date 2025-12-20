import datetime
import enum

from sqlalchemy import (  # type: ignore  # type: ignore  # type: ignore  # type: ignore  # type: ignore  # type: ignore  # type: ignore  # type: ignore  # type: ignore  # type: ignore  # type: ignore  # type: ignore  # type: ignore  # type: ignore  # type: ignore  # type: ignore
    JSON,
    Column,
    DateTime,
    Integer,
    String,
)
from sqlalchemy import Enum as SAEnum

from marty_plugin.shared.database import Base


class MDocStatus(enum.Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    PENDING_SIGNATURE = "pending_signature"
    CREATED = "created"


class MDocMimeTypeChoices(enum.Enum):
    APPLICATION_CBOR = "application/cbor"
    APPLICATION_XML = "application/xml"
    APPLICATION_JSON = "application/json"


class MobileDocument(Base):
    __tablename__ = "mobile_documents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    device_id = Column(String, index=True, nullable=True)
    document_id = Column(String, unique=True, index=True, nullable=False)
    document_type = Column(String, index=True, nullable=False)

    issue_date = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    expiry_date = Column(DateTime, nullable=False)
    issuing_authority = Column(String, nullable=False)
    data_groups = Column(JSON, nullable=False)
    mime_type = Column(SAEnum(MDocMimeTypeChoices), nullable=True)
    status = Column(SAEnum(MDocStatus), default=MDocStatus.PENDING_SIGNATURE, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    device_key_identifier = Column(String, nullable=True)
    document_data_signed = Column(String, nullable=True)
    device_engagement_data_encoded = Column(String, nullable=True)
