"""
OpenXPKI Service - Integration layer for OpenXPKI Certificate Management (PKD Service)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from marty_common.services.base_openxpki_service import BaseOpenXPKIService

logger = logging.getLogger(__name__)


class OpenXPKIService(BaseOpenXPKIService):
    """
    PKD Service specific OpenXPKI integration.
    Extends base functionality with PKD-specific operations.
    """

    def import_master_list(
        self, master_list_data: bytes, format_type: str = "DER"
    ) -> dict[str, Any]:
        """Import a master list into OpenXPKI"""
        try:
            import_data = {
                "method": "import_certificate",
                "params": {
                    "data": (
                        master_list_data.hex()
                        if format_type == "DER"
                        else master_list_data.decode("utf-8")
                    ),
                    "format": format_type.lower(),
                    "import_type": "masterlist",
                    "profile": "csca",
                },
            }

            success, data = self._api_request("certificate/import", "POST", import_data)
            if success:
                result: dict[str, Any] = {
                    "success": True,
                    "certificates_imported": len(data.get("certificates", [])),
                    "certificates": [],
                }
                for cert in data.get("certificates", []):
                    cert_info = {
                        "subject": cert.get("subject", ""),
                        "issuer": cert.get("issuer", ""),
                        "serial_number": cert.get("serial", ""),
                        "not_before": cert.get("not_before", ""),
                        "not_after": cert.get("not_after", ""),
                        "fingerprint": cert.get("fingerprint", ""),
                    }
                    subject = cert_info["subject"]
                    if "C=" in subject:
                        parts = [p for p in subject.split(",") if "C=" in p]
                        if parts:
                            cert_info["country_code"] = parts[0].split("=")[1].strip()
                    result["certificates"].append(cert_info)
                return result
            return {
                "success": False,
                "error": data.get("error", "Unknown error during import"),
                "certificates_imported": 0,
            }
        except Exception:  # pragma: no cover
            logger.exception("Error importing master list")
            return {"success": False, "error": "Import error", "certificates_imported": 0}

    def get_master_list(self, format_type: str = "DER") -> dict[str, Any]:
        try:
            success, data = self._api_request("certificate/list?profile=csca")
            if success:
                certificates = data.get("certificates", [])
                result: dict[str, Any] = {
                    "certificate_count": len(certificates),
                    "is_valid": True,
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                }
                if format_type == "JSON":
                    result["format"] = "JSON"
                    result["master_list_data"] = json.dumps(certificates)
                else:
                    cert_data: list[str | bytes] = []
                    for cert in certificates:
                        cert_id = cert.get("identifier")
                        if cert_id:
                            _, cert_detail = self._api_request(
                                f"certificate/{cert_id}/raw?format={format_type.lower()}"
                            )
                            if format_type == "PEM":
                                cert_data.append(cert_detail.get("data", ""))
                            else:
                                cert_data.append(bytes.fromhex(cert_detail.get("data", "")))
                    if format_type == "PEM":
                        result["format"] = "PEM"
                        result["master_list_data"] = "\n".join(cert_data)  # type: ignore[arg-type]
                    else:
                        result["format"] = "DER"
                        result["master_list_data"] = b"".join(cert_data)  # type: ignore[arg-type]
                return result
            return {
                "certificate_count": 0,
                "is_valid": False,
                "error": data.get("error", "Failed to retrieve certificates"),
            }
        except Exception:  # pragma: no cover
            logger.exception("Error getting master list")
            return {"certificate_count": 0, "is_valid": False, "error": "Master list error"}

    def verify_certificate(
        self, certificate_data: bytes, format_type: str = "DER", check_revocation: bool = True
    ) -> dict[str, Any]:
        try:
            verify_data = {
                "method": "verify_certificate",
                "params": {
                    "data": (
                        certificate_data.hex()
                        if format_type == "DER"
                        else certificate_data.decode("utf-8")
                    ),
                    "format": format_type.lower(),
                    "check_revocation": check_revocation,
                },
            }
            success, data = self._api_request("certificate/verify", "POST", verify_data)
            if success:
                return {
                    "is_valid": data.get("valid", False),
                    "is_trusted": data.get("trusted", False),
                    "is_revoked": data.get("revoked", False),
                    "subject": data.get("subject", ""),
                    "issuer": data.get("issuer", ""),
                    "validation_errors": data.get("errors", []),
                    "revocation_reason": data.get("revocation_reason", ""),
                }
            return {
                "is_valid": False,
                "is_trusted": False,
                "validation_errors": [data.get("error", "Verification request failed")],
            }
        except Exception:  # pragma: no cover
            logger.exception("Error verifying certificate")
            return {
                "is_valid": False,
                "is_trusted": False,
                "validation_errors": ["Verification error"],
            }

    def sync_to_local_store(self, force: bool = False) -> dict[str, Any]:
        try:
            success, data = self._api_request("certificate/list?profile=csca")
            if not success:
                return {
                    "success": False,
                    "certificates_synced": 0,
                    "errors": [data.get("error", "Failed to retrieve certificates")],
                }
            certificates = data.get("certificates", [])
            sync_count = 0
            errors: list[str] = []
            for cert in certificates:
                cert_id = cert.get("identifier")
                if not cert_id:
                    continue
                _, cert_detail = self._api_request(f"certificate/{cert_id}")
                subject = cert_detail.get("subject", "")
                country_code = "XX"
                if "C=" in subject:
                    parts = [p for p in subject.split(",") if "C=" in p]
                    if parts:
                        country_code = parts[0].split("=")[1].strip()
                country_dir = Path(self.local_store_path) / country_code
                country_dir.mkdir(parents=True, exist_ok=True)
                cert_file = country_dir / f"{cert_id}.cer"
                if not force and cert_file.exists():
                    stat = cert_file.stat()
                    if datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc) > datetime.now(
                        timezone.utc
                    ) - timedelta(days=1):
                        continue
                _, raw_cert = self._api_request(f"certificate/{cert_id}/raw?format=der")
                if "data" in raw_cert:
                    try:
                        cert_file.write_bytes(bytes.fromhex(raw_cert["data"]))
                        sync_count += 1
                    except OSError as e:  # pragma: no cover
                        errors.append(f"Failed to save certificate {cert_id}: {e!s}")
            return {
                "success": True,
                "certificates_synced": sync_count,
                "sync_timestamp": datetime.now(timezone.utc).isoformat(),
                "errors": errors,
            }
        except Exception:  # pragma: no cover
            logger.exception("Error during synchronization")
            return {"success": False, "certificates_synced": 0, "errors": ["Sync error"]}

    def check_expiring_certificates(self, days: int = 90) -> dict[str, Any]:
        try:
            expiry_date = datetime.now(timezone.utc) + timedelta(days=days)
            expiry_date_str = expiry_date.strftime("%Y-%m-%d")
            success, data = self._api_request(
                f"certificate/list?profile=csca&valid_until={expiry_date_str}"
            )
            if not success:
                return {
                    "expiring_certificates": [],
                    "error": data.get("error", "Failed to retrieve certificates"),
                }
            certificates = data.get("certificates", [])
            expiring: list[dict[str, Any]] = []
            for cert in certificates:
                cert_id = cert.get("identifier")
                if not cert_id:
                    continue
                _, cert_detail = self._api_request(f"certificate/{cert_id}")
                subject = cert_detail.get("subject", "")
                country_code = "XX"
                if "C=" in subject:
                    parts = [p for p in subject.split(",") if "C=" in p]
                    if parts:
                        country_code = parts[0].split("=")[1].strip()
                not_after = cert_detail.get("not_after", "")
                days_remaining = 0
                try:
                    expiry_dt = datetime.strptime(not_after, "%Y-%m-%d %H:%M:%S").replace(
                        tzinfo=timezone.utc
                    )
                    days_remaining = (expiry_dt - datetime.now(timezone.utc)).days
                except (ValueError, TypeError):  # pragma: no cover
                    pass
                expiring.append(
                    {
                        "subject": cert_detail.get("subject", ""),
                        "issuer": cert_detail.get("issuer", ""),
                        "serial_number": cert_detail.get("serial", ""),
                        "not_after": not_after,
                        "days_remaining": days_remaining,
                        "country_code": country_code,
                    }
                )
        except Exception:  # pragma: no cover
            logger.exception("Error checking expiring certificates")
            return {"expiring_certificates": [], "error": "Expiry check error"}
        else:
            return {"expiring_certificates": expiring}
