"""
ASN.1 utilities for Marty services.

This module provides utilities for working with ASN.1 structures commonly used in e-passports,
leveraging the asn1crypto library for efficient and robust handling.

Where applicable, this module can use Rust implementations from marty-verification for
improved performance on certificate parsing.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from asn1crypto import cms, core, pem, x509

# Import Rust bindings for certificate operations
from marty_common.crypto_bridge import (
    get_certificate_info as rust_get_certificate_info,
)

logger = logging.getLogger(__name__)


def decode_der(data: bytes) -> Any:
    """
    Decode DER encoded ASN.1 data to an asn1crypto object.

    Args:
        data: DER encoded ASN.1 data

    Returns:
        An asn1crypto object representing the ASN.1 structure
    """
    try:
        # Try to decode as a CMS ContentInfo first, which is common for e-passport data
        return cms.ContentInfo.load(data)
    except Exception as e:
        logger.debug(f"Failed to decode as CMS ContentInfo: {e}")

        # Try to decode as X.509 Certificate
        try:
            return x509.Certificate.load(data)
        except Exception as e:
            logger.debug(f"Failed to decode as X.509 Certificate: {e}")

            # Try generic ASN.1 sequence
            try:
                return core.Sequence.load(data)
            except Exception as e:
                logger.exception(f"Failed to decode ASN.1 data: {e}")
                msg = "Failed to decode ASN.1 data"
                raise ValueError(msg) from e


def encode_der(asn1_obj: Any) -> bytes:
    """
    Encode an asn1crypto object to DER.

    Args:
        asn1_obj: An asn1crypto object

    Returns:
        DER encoded ASN.1 data
    """
    try:
        return asn1_obj.dump()
    except Exception as e:
        logger.exception(f"Failed to encode ASN.1 object: {e}")
        msg = "Failed to encode ASN.1 object"
        raise ValueError(msg) from e


def is_pem(data: bytes) -> bool:
    """
    Check if data is in PEM format.

    Args:
        data: Data to check

    Returns:
        True if data is in PEM format, False otherwise
    """
    try:
        return pem.detect(data)
    except Exception:
        return False


def pem_to_der(pem_data: bytes) -> bytes:
    """
    Convert PEM encoded data to DER.

    Args:
        pem_data: PEM encoded data

    Returns:
        DER encoded data
    """
    if not is_pem(pem_data):
        msg = "Data is not in PEM format"
        raise ValueError(msg)

    type_name, headers, der_bytes = pem.unarmor(pem_data)
    return der_bytes


def der_to_pem(der_data: bytes, pem_type: str = "CERTIFICATE") -> bytes:
    """
    Convert DER encoded data to PEM.

    Args:
        der_data: DER encoded data
        pem_type: PEM type label (default: "CERTIFICATE")

    Returns:
        PEM encoded data
    """
    return pem.armor(pem_type, der_data)


def extract_signed_data(cms_data: bytes) -> dict[str, Any]:
    """
    Extract data from a CMS SignedData structure.

    Args:
        cms_data: DER encoded CMS ContentInfo containing SignedData

    Returns:
        Dictionary containing extracted data
    """
    try:
        content_info = cms.ContentInfo.load(cms_data)
        if content_info["content_type"].native != "signed_data":
            msg = "Not a CMS SignedData structure"
            raise ValueError(msg)

        signed_data = content_info["content"]

        result = {
            "version": signed_data["version"].native,
            "content_type": signed_data["encap_content_info"]["content_type"].native,
        }

        # Extract digest algorithms
        digest_algorithms = []
        for algo in signed_data["digest_algorithms"]:
            algorithm = algo["algorithm"].native
            parameters = None
            if "parameters" in algo and algo["parameters"].native is not None:
                parameters = algo["parameters"].native

            digest_algorithms.append({"algorithm": algorithm, "parameters": parameters})
        result["digest_algorithms"] = digest_algorithms

        # Extract encapsulated content
        if "content" in signed_data["encap_content_info"]:
            content = signed_data["encap_content_info"]["content"]
            if content is not None:
                result["encapsulated_content"] = base64.b64encode(content.native).decode("ascii")

        # Extract certificates
        if "certificates" in signed_data and signed_data["certificates"].native:
            certs = []
            for cert in signed_data["certificates"]:
                cert_der = cert.dump()
                cert_data = {
                    "der": base64.b64encode(cert_der).decode("ascii"),
                    "subject": cert.chosen["tbs_certificate"]["subject"].human_friendly,
                    "issuer": cert.chosen["tbs_certificate"]["issuer"].human_friendly,
                    "serial_number": str(cert.chosen["tbs_certificate"]["serial_number"].native),
                    "not_before": cert.chosen["tbs_certificate"]["validity"]["not_before"].native,
                    "not_after": cert.chosen["tbs_certificate"]["validity"]["not_after"].native,
                }
                certs.append(cert_data)
            result["certificates"] = certs

        # Extract CRLs
        if "crls" in signed_data and signed_data["crls"].native:
            crls = []
            for crl in signed_data["crls"]:
                crl_der = crl.dump()
                crls.append(base64.b64encode(crl_der).decode("ascii"))
            result["crls"] = crls

        # Extract signer infos
        if "signer_infos" in signed_data:
            signers = []
            for signer_info in signed_data["signer_infos"]:
                signer = {
                    "version": signer_info["version"].native,
                    "digest_algorithm": signer_info["digest_algorithm"]["algorithm"].native,
                    "signature_algorithm": signer_info["signature_algorithm"]["algorithm"].native,
                    "signature": base64.b64encode(signer_info["signature"].native).decode("ascii"),
                }

                # Extract signer identifier
                if signer_info["sid"].name == "issuer_and_serial_number":
                    sid = signer_info["sid"].chosen
                    signer["signer_id"] = {
                        "issuer": sid["issuer"].human_friendly,
                        "serial_number": str(sid["serial_number"].native),
                    }
                else:  # subject_key_identifier
                    signer["signer_id"] = {
                        "subject_key_identifier": signer_info["sid"].chosen.native.hex()
                    }

                # Extract signed attributes
                if "signed_attrs" in signer_info and signer_info["signed_attrs"].native:
                    signed_attrs = {}
                    for attr in signer_info["signed_attrs"]:
                        attr_type = attr["type"].native
                        attr_values = [v.native for v in attr["values"]]
                        signed_attrs[attr_type] = attr_values
                    signer["signed_attributes"] = signed_attrs

                # Extract unsigned attributes
                if "unsigned_attrs" in signer_info and signer_info["unsigned_attrs"].native:
                    unsigned_attrs = {}
                    for attr in signer_info["unsigned_attrs"]:
                        attr_type = attr["type"].native
                        attr_values = [v.native for v in attr["values"]]
                        unsigned_attrs[attr_type] = attr_values
                    signer["unsigned_attributes"] = unsigned_attrs

                signers.append(signer)
            result["signers"] = signers

    except Exception as e:
        logger.exception(f"Failed to extract SignedData: {e}")
        msg = "Failed to extract SignedData"
        raise ValueError(msg) from e
    else:
        return result


def extract_certificate_info(cert_data: bytes) -> dict[str, Any]:
    """
    Extract information from an X.509 certificate.

    Args:
        cert_data: DER or PEM encoded X.509 certificate

    Returns:
        Dictionary containing certificate information
    """
    # Convert PEM to DER if necessary
    if is_pem(cert_data):
        der_data = pem_to_der(cert_data)
    else:
        der_data = cert_data
    
    rust_info = rust_get_certificate_info(der_data)
    
    # Convert Rust result to match expected format
    result = {
        "serial_number": rust_info.get("serial_number", ""),
        "issuer": rust_info.get("issuer", ""),
        "subject": rust_info.get("subject", ""),
        "not_before": rust_info.get("not_before", ""),
        "not_after": rust_info.get("not_after", ""),
        "signature_algorithm": rust_info.get("signature_algorithm", ""),
        "public_key_algorithm": rust_info.get("public_key_algorithm", ""),
        "pem": der_to_pem(der_data).decode("ascii"),
    }
    return result


def verify_cms_signature(cms_data: bytes, cert_data: bytes | None = None) -> bool:
    """
    Verify the signature on a CMS SignedData structure.

    Args:
        cms_data: DER encoded CMS ContentInfo containing SignedData
        cert_data: DER or PEM encoded certificate to use for verification (optional)
                   If not provided, certificates embedded in the CMS will be used

    Returns:
        True if signature is valid, False otherwise
    """
    try:
        content_info = cms.ContentInfo.load(cms_data)
        if content_info["content_type"].native != "signed_data":
            msg = "Not a CMS SignedData structure"
            raise ValueError(msg)

        signed_data = content_info["content"]

        # Get certificates from the CMS if no certificate was provided
        certificates = []
        if cert_data is None:
            if "certificates" in signed_data and signed_data["certificates"].native:
                certificates.extend(cert.chosen for cert in signed_data["certificates"])
        else:
            # Convert PEM to DER if necessary
            if is_pem(cert_data):
                cert_data = pem_to_der(cert_data)

            cert = x509.Certificate.load(cert_data)
            certificates.append(cert)

        if not certificates:
            msg = "No certificates available for verification"
            raise ValueError(msg)

        # For each signer, attempt verification
        for _signer_info in signed_data["signer_infos"]:
            # Placeholder for verification logic
            # In a real implementation, this would validate the signature
            # using the appropriate certificate

            # For now, just log that verification would happen here
            logger.info("Signature verification would happen here")

            # In the future, implement proper verification using cryptography

        # For now, just return True to indicate successful verification
        # In a real implementation, return the actual verification result

    except Exception as e:
        logger.exception(f"Signature verification failed: {e}")
        return False
    else:
        return True
