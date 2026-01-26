"""
Revocation Service Discovery

Discovers and resolves revocation endpoints from credentials and Trust Profile configuration.
Implements precedence rules: explicit endpoints override discovered when merge_discovered=false.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from digital_identity.domain.entities import TrustProfile

logger = logging.getLogger(__name__)


@dataclass
class RevocationEndpoints:
    """Resolved revocation endpoints for a credential type."""
    
    crl_endpoints: list[str] = field(default_factory=list)
    ocsp_urls: list[str] = field(default_factory=list)
    status_list_urls: list[str] = field(default_factory=list)
    
    def has_any_endpoint(self) -> bool:
        """Check if any endpoints are configured."""
        return bool(self.crl_endpoints or self.ocsp_urls or self.status_list_urls)


class RevocationServiceDiscovery:
    """
    Discovers and resolves revocation service endpoints.
    
    Handles:
    1. Auto-discovery from credential/certificate metadata
    2. Explicit configuration from Trust Profile
    3. Precedence rules and merging strategies
    4. Per-credential-type caching
    """
    
    def __init__(self):
        """Initialize discovery service."""
        self._endpoint_cache: dict[str, RevocationEndpoints] = {}
    
    def resolve_endpoints(
        self,
        trust_profile: TrustProfile,
        credential_type: str,
        credential_metadata: dict[str, Any] | None = None,
    ) -> RevocationEndpoints:
        """
        Resolve revocation endpoints for a credential type.
        
        Args:
            trust_profile: Trust profile with revocation service config
            credential_type: Type of credential (for caching)
            credential_metadata: Optional credential/cert metadata for discovery
            
        Returns:
            Resolved revocation endpoints
        """
        # Check cache
        cache_key = f"{trust_profile.id}:{credential_type}"
        if cache_key in self._endpoint_cache:
            logger.debug(f"Using cached endpoints for {cache_key}")
            return self._endpoint_cache[cache_key]
        
        # Get explicit endpoints from Trust Profile
        explicit_endpoints = self._get_explicit_endpoints(trust_profile)
        
        # Check if auto-discovery is enabled
        if trust_profile.should_auto_discover_revocation() and credential_metadata:
            discovered_endpoints = self._discover_endpoints(credential_metadata)
            
            # Apply merge strategy
            if trust_profile.should_merge_discovered_endpoints():
                final_endpoints = self._merge_endpoints(explicit_endpoints, discovered_endpoints)
            else:
                # Explicit takes precedence, only use discovered if no explicit
                final_endpoints = self._prefer_explicit(explicit_endpoints, discovered_endpoints)
        else:
            final_endpoints = explicit_endpoints
        
        # Cache and return
        self._endpoint_cache[cache_key] = final_endpoints
        return final_endpoints
    
    def _get_explicit_endpoints(self, trust_profile: TrustProfile) -> RevocationEndpoints:
        """Extract explicit endpoints from Trust Profile configuration."""
        return RevocationEndpoints(
            crl_endpoints=trust_profile.get_explicit_revocation_endpoints("CRL"),
            ocsp_urls=trust_profile.get_explicit_revocation_endpoints("OCSP"),
            status_list_urls=trust_profile.get_explicit_revocation_endpoints("STATUS_LIST"),
        )
    
    def _discover_endpoints(self, credential_metadata: dict[str, Any]) -> RevocationEndpoints:
        """
        Discover revocation endpoints from credential/certificate metadata.
        
        Supports:
        - X.509 CRL Distribution Points (CDP)
        - X.509 Authority Information Access (AIA) for OCSP
        - JWT 'status' claim for Status Lists
        - mDoc statusInfo for Status Lists
        """
        endpoints = RevocationEndpoints()
        
        # X.509 Certificate discovery
        if "certificate_extensions" in credential_metadata:
            exts = credential_metadata["certificate_extensions"]
            
            # CRL Distribution Points (OID 2.5.29.31)
            if "crl_distribution_points" in exts:
                endpoints.crl_endpoints = self._extract_crl_distribution_points(
                    exts["crl_distribution_points"]
                )
            
            # Authority Information Access (OID 1.3.6.1.5.5.7.1.1)
            if "authority_information_access" in exts:
                endpoints.ocsp_urls = self._extract_ocsp_urls(
                    exts["authority_information_access"]
                )
        
        # JWT/SD-JWT status claim
        if "status" in credential_metadata:
            status_claim = credential_metadata["status"]
            if isinstance(status_claim, dict):
                if "status_list" in status_claim:
                    # IETF OAuth Status List (draft-ietf-oauth-status-list)
                    status_list = status_claim["status_list"]
                    if "uri" in status_list:
                        endpoints.status_list_urls.append(status_list["uri"])
                elif "status_assertion" in status_claim:
                    # W3C Bitstring Status List
                    endpoints.status_list_urls.append(status_claim["status_assertion"])
        
        # mDoc statusInfo (ISO 18013-5)
        if "statusInfo" in credential_metadata:
            status_info = credential_metadata["statusInfo"]
            if isinstance(status_info, dict) and "statusListURI" in status_info:
                endpoints.status_list_urls.append(status_info["statusListURI"])
        
        logger.debug(f"Discovered endpoints: {endpoints}")
        return endpoints
    
    def _extract_crl_distribution_points(self, cdp_data: list[Any]) -> list[str]:
        """Extract CRL URLs from Certificate Distribution Points extension."""
        urls = []
        for cdp in cdp_data:
            if isinstance(cdp, str):
                urls.append(cdp)
            elif isinstance(cdp, dict) and "uri" in cdp:
                urls.append(cdp["uri"])
        return urls
    
    def _extract_ocsp_urls(self, aia_data: list[Any]) -> list[str]:
        """Extract OCSP URLs from Authority Information Access extension."""
        urls = []
        for aia in aia_data:
            if isinstance(aia, dict):
                if aia.get("access_method") == "OCSP" and "access_location" in aia:
                    urls.append(aia["access_location"])
            elif isinstance(aia, str) and "ocsp" in aia.lower():
                urls.append(aia)
        return urls
    
    def _merge_endpoints(
        self,
        explicit: RevocationEndpoints,
        discovered: RevocationEndpoints,
    ) -> RevocationEndpoints:
        """
        Merge explicit and discovered endpoints (union).
        
        Explicit endpoints are added first, then discovered endpoints that aren't duplicates.
        """
        return RevocationEndpoints(
            crl_endpoints=self._unique_merge(explicit.crl_endpoints, discovered.crl_endpoints),
            ocsp_urls=self._unique_merge(explicit.ocsp_urls, discovered.ocsp_urls),
            status_list_urls=self._unique_merge(explicit.status_list_urls, discovered.status_list_urls),
        )
    
    def _prefer_explicit(
        self,
        explicit: RevocationEndpoints,
        discovered: RevocationEndpoints,
    ) -> RevocationEndpoints:
        """
        Prefer explicit endpoints, fall back to discovered if explicit is empty.
        
        This is the default strategy when merge_discovered=false.
        """
        return RevocationEndpoints(
            crl_endpoints=explicit.crl_endpoints or discovered.crl_endpoints,
            ocsp_urls=explicit.ocsp_urls or discovered.ocsp_urls,
            status_list_urls=explicit.status_list_urls or discovered.status_list_urls,
        )
    
    def _unique_merge(self, list1: list[str], list2: list[str]) -> list[str]:
        """Merge two lists, preserving order and removing duplicates."""
        seen = set()
        result = []
        for item in list1 + list2:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result
    
    def clear_cache(self, trust_profile_id: str | None = None) -> None:
        """
        Clear endpoint cache.
        
        Args:
            trust_profile_id: Clear only for specific profile, or all if None
        """
        if trust_profile_id:
            self._endpoint_cache = {
                k: v for k, v in self._endpoint_cache.items()
                if not k.startswith(f"{trust_profile_id}:")
            }
        else:
            self._endpoint_cache.clear()
