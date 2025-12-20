"""
ISO/IEC 18013-5 Testing Package

This package provides comprehensive testing tools for ISO 18013-5 and 18013-7
implementations including test vectors, simulators, and CI test suites.

Modules:
- test_vectors: Test vector generation and mock implementations
- ci_tests: Continuous integration test suite
"""

from .ci_tests import (
    TestISO18013Applications,
    TestISO18013Protocol,
    TestSimulation,
    TestTestVectors,
)
from .test_vectors import MockmDLCredential, MockTransport, mDLSimulator, mDLTestVectorGenerator

__all__ = [
    # Test vector generation
    "mDLTestVectorGenerator",
    "mDLSimulator",
    "MockTransport",
    "MockmDLCredential",
    # CI test classes
    "TestISO18013Protocol",
    "TestISO18013Applications",
    "TestTestVectors",
    "TestSimulation",
]

# Version info
__version__ = "1.0.0"
__author__ = "ISO 18013 Test Suite"
__description__ = "Comprehensive testing tools for ISO/IEC 18013-5 mDL implementations"
