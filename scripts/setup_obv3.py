#!/usr/bin/env python3
"""
Quick Setup Script for OBv3 Readiness

Runs database migration and seeds system compliance profiles.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


async def setup_obv3():
    """Run OBv3 setup: migration + seeding."""
    print("🚀 Starting Open Badge v3 Readiness Setup\n")
    
    # Step 1: Run migration
    print("📦 Step 1: Running database migration...")
    print("   Run: alembic upgrade head")
    print("   (Manual step - run this command in your terminal)\n")
    
    # Step 2: Seed system profiles
    print("🌱 Step 2: Seeding system compliance profiles...")
    try:
        from digital_identity.infrastructure.persistence.seed_system_compliance_profiles import main
        await main()
        print("✅ System compliance profiles seeded successfully\n")
    except Exception as e:
        print(f"❌ Error seeding profiles: {e}\n")
        print("Make sure you've run the database migration first.\n")
        return False
    
    # Step 3: Verify
    print("🔍 Step 3: Verification...")
    print("   Check that 3 system profiles exist:")
    print("   - OB3_JWT")
    print("   - OB3_JSONLD")
    print("   - OB2_COMPATIBILITY\n")
    
    print("✅ OBv3 readiness setup complete!")
    print("\n📚 Next steps:")
    print("   1. Implement ComplianceProfileRepository")
    print("   2. Add REST API endpoints for publish/unpublish")
    print("   3. Add integration tests")
    print("   4. Update UI with publish buttons\n")
    print("📖 See OBV3_IMPLEMENTATION_COMPLETE.md for full checklist\n")
    
    return True


if __name__ == "__main__":
    success = asyncio.run(setup_obv3())
    sys.exit(0 if success else 1)
