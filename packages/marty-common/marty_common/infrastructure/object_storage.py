"""Async object storage client abstraction."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any

import aioboto3
from botocore.config import Config  # type: ignore[import-untyped]


@dataclass(slots=True)
class ObjectStorageConfig:
    """Configuration for S3-compatible object storage."""

    bucket: str
    access_key: str
    secret_key: str
    region: str = "us-east-1"
    endpoint_url: str | None = None
    secure: bool = True
    path_style_access: bool = True

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ObjectStorageConfig:
        bucket = raw.get("bucket", "marty-dev")
        access_key = raw.get("access_key", "localdev")
        secret_key = raw.get("secret_key", "localdev")
        return cls(
            bucket=bucket,
            access_key=access_key,
            secret_key=secret_key,
            region=raw.get("region", "us-east-1"),
            endpoint_url=raw.get("endpoint_url"),
            secure=bool(raw.get("secure", True)),
            path_style_access=bool(raw.get("path_style_access", True)),
        )


class ObjectStorageClient:
    """Thin async wrapper over aioboto3 for service use."""

    def __init__(self, config: ObjectStorageConfig) -> None:
        self._config = config
        self._session = aioboto3.Session()

    def _client_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "aws_access_key_id": self._config.access_key,
            "aws_secret_access_key": self._config.secret_key,
            "region_name": self._config.region,
        }
        if self._config.endpoint_url:
            kwargs["endpoint_url"] = self._config.endpoint_url
        if not self._config.secure:
            kwargs["use_ssl"] = False
        if self._config.path_style_access:
            kwargs["config"] = Config(signature_version="s3v4", s3={"addressing_style": "path"})
        return kwargs

    async def put_object(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> None:
        async with self._session.client("s3", **self._client_kwargs()) as client:
            await client.put_object(
                Bucket=self._config.bucket, Key=key, Body=data, ContentType=content_type
            )

    async def get_object(self, key: str) -> bytes:
        async with self._session.client("s3", **self._client_kwargs()) as client:
            response = await client.get_object(Bucket=self._config.bucket, Key=key)
            async with response["Body"] as stream:
                data = await stream.read()
                return bytes(data) if data is not None else b""

    async def delete_object(self, key: str) -> None:
        async with self._session.client("s3", **self._client_kwargs()) as client:
            await client.delete_object(Bucket=self._config.bucket, Key=key)

    async def upload_stream(self, key: str, stream: BytesIO, content_type: str) -> None:
        data = stream.getvalue()
        await self.put_object(key, data, content_type)
