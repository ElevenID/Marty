#!/usr/bin/env python3
"""
Refactored Comprehensive Feature Validation Script using DRY utilities

This script validates the implementation status of the passport verification system
using reusable validation utilities.
"""

import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from marty_backend_common.validation import FeatureValidator, QualityMetricsAnalyzer


def get_phase_1_crypto_specs() -> dict:
    """Define Phase 1 crypto feature specifications."""
    return {
        "sod_parser": {
            "module": "src.marty_common.crypto.sod_parser",
            "classes": ["SODParser", "LDSSecurityObject"],
            "functions": ["parse_sod", "extract_data_group_hashes"],
        },
        "data_group_hasher": {
            "module": "src.marty_common.crypto.data_group_hasher",
            "classes": ["DataGroupHasher", "DataGroupHashResult"],
            "functions": ["compute_hash", "compute_data_group_hash"],
        },
        "hash_comparison": {
            "module": "src.marty_common.crypto.hash_comparison",
            "classes": ["HashComparisonEngine", "IntegrityVerificationReport"],
            "functions": ["compare_hashes", "verify_integrity"],
        },
        "certificate_validator": {
            "module": "src.marty_common.crypto.certificate_validator",
            "classes": ["CertificateChainValidator", "ValidationResult"],
            "functions": ["validate_certificate_chain", "verify_signature"],
        },
    }


def get_phase_2_rfid_specs() -> dict:
    """Define Phase 2 RFID feature specifications."""
    return {
        "rfid_protocols": {
            "module": "src.marty_common.rfid.nfc_protocols",
            "classes": ["NFCProtocolHandler", "RFIDInterface"],
            "functions": ["establish_connection", "read_data_groups"],
        },
        "passport_apdu": {
            "module": "src.marty_common.rfid.passport_apdu",
            "classes": ["PassportAPDU", "APDUCommand"],
            "functions": ["select_elementary_file", "read_binary"],
        },
        "elementary_files": {
            "module": "src.marty_common.rfid.elementary_files",
            "classes": ["ElementaryFileParser", "DataGroup"],
            "functions": ["parse_dg1_mrz", "parse_dg2_biometric"],
        },
        "secure_messaging": {
            "module": "src.marty_common.rfid.secure_messaging",
            "classes": ["SecureMessaging", "SessionKeys"],
            "functions": ["establish_secure_channel", "encrypt_command"],
        },
    }


def get_phase_3_security_specs() -> dict:
    """Define Phase 3 advanced security feature specifications."""
    return {
        "eac_protocol": {
            "module": "src.marty_common.crypto.eac_protocol",
            "classes": ["EACProtocolHandler", "TerminalCertificate"],
            "functions": ["perform_terminal_authentication", "perform_chip_authentication"],
        },
        "active_authentication": {
            "module": "src.marty_common.security.active_authentication",
            "classes": ["ActiveAuthEngine", "ChallengeResponse"],
            "functions": ["generate_challenge", "verify_response"],
        },
        "biometric_processing": {
            "module": "src.marty_common.security.enhanced_biometric_processing",
            "classes": ["BiometricProcessor", "FaceRecognition"],
            "functions": ["process_facial_image", "extract_features"],
        },
        "csca_trust_store": {
            "module": "src.marty_common.crypto.csca_trust_store",
            "classes": ["CSCATrustStore", "TrustAnchor"],
            "functions": ["verify_csca_certificate", "load_trust_anchors"],
        },
    }


def get_phase_4_production_specs() -> dict:
    """Define Phase 4 production feature specifications."""
    return {
        "pkd_integration": {
            "module": "src.pkd_service.simple_pkd_mirror",
            "classes": ["PKDMirror", "CertificateDownloader"],
            "functions": ["sync_certificates", "download_masterlist"],
        },
        "crl_validation": {
            "module": "src.marty_common.crypto.certificate_validator",
            "classes": ["CRLValidator", "OCSPValidator"],
            "functions": ["check_revocation_status", "validate_crl"],
        },
        "hardware_integration": {
            "module": "src.marty_common.hardware.pcsc_reader",
            "classes": ["PCSCReader", "ReaderManager"],
            "functions": ["initialize_readers", "transmit_apdu"],
        },
        "monitoring": {
            "module": "src.marty_common.monitoring",
            "classes": ["SystemMonitor", "PerformanceMetrics"],
            "functions": ["collect_metrics", "generate_report"],
        },
    }


def main():
    """Main validation script using reusable utilities."""
    print("🚀 Starting Comprehensive Feature Validation...")

    # Initialize validator
    validator = FeatureValidator("src")

    # Validate all phases using the reusable validator
    validator.validate_feature_set(
        get_phase_1_crypto_specs(),
        "phase_1_core_crypto",
        "Phase 1: Core Cryptographic Verification",
    )

    validator.validate_feature_set(
        get_phase_2_rfid_specs(), "phase_2_rfid_testing", "Phase 2: RFID Testing Infrastructure"
    )

    validator.validate_feature_set(
        get_phase_3_security_specs(),
        "phase_3_advanced_security",
        "Phase 3: Advanced Security Features",
    )

    validator.validate_feature_set(
        get_phase_4_production_specs(),
        "phase_4_production",
        "Phase 4: Production Integration Features",
    )

    # Analyze quality metrics
    print("\n🔍 Analyzing Code Quality Metrics...")
    quality_analyzer = QualityMetricsAnalyzer()

    ruff_metrics = quality_analyzer.analyze_ruff_report()
    mypy_metrics = quality_analyzer.analyze_mypy_report()
    coverage_metrics = quality_analyzer.analyze_test_coverage()

    quality_summary = quality_analyzer.get_quality_summary()

    # Generate summary report
    print("\n📊 VALIDATION SUMMARY")
    print("=" * 50)

    overall_completion = validator.get_overall_completion()
    print(f"Overall Feature Completion: {overall_completion:.1f}%")

    missing_features = validator.get_missing_features()
    if missing_features:
        print(f"\nMissing Features ({len(missing_features)}):")
        for feature in missing_features[:10]:  # Show first 10
            print(f"  - {feature}")
        if len(missing_features) > 10:
            print(f"  ... and {len(missing_features) - 10} more")

    print("\nCode Quality Summary:")
    print(f"  Ruff Issues: {quality_summary['ruff_issues']}")
    print(f"  MyPy Errors: {quality_summary['mypy_errors']}")
    print(f"  Test Coverage: {quality_summary['test_coverage']}%")
    print(f"  Quality Score: {quality_summary['quality_score']:.1f}%")

    # Export detailed results
    import json

    output_file = "validation_results.json"

    full_results = {
        "feature_validation": validator.results,
        "quality_metrics": quality_analyzer.metrics,
        "summary": {
            "overall_completion": overall_completion,
            "missing_features": missing_features,
            "quality_summary": quality_summary,
        },
    }

    with open(output_file, "w") as f:
        json.dump(full_results, f, indent=2)

    print(f"\n📝 Detailed results saved to {output_file}")

    # Set exit code based on completion
    if overall_completion < 80:
        print("\n⚠️  Feature completion below 80%. Consider addressing missing features.")
        sys.exit(1)
    elif quality_summary["quality_score"] < 70:
        print("\n⚠️  Code quality below 70%. Consider addressing quality issues.")
        sys.exit(1)
    else:
        print("\n✅ Validation passed! System ready for deployment.")
        sys.exit(0)


if __name__ == "__main__":
    main()
