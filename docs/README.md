# LARS Documentation 📚

## Security Documentation

### 🔒 Schema-Only Prompting Feature

This directory contains documentation for the **Schema-Only Prompting** security feature implemented in LARS.

#### Files

1. **`SECURITY_SCHEMA_ONLY_PROMPTING.md`** (Arabic - العربية)
   - **Audience**: Management, Quality Managers, ISO 17025 Auditors
   - **Purpose**: Explains the security concept in Arabic for non-technical stakeholders
   - **Content**:
     - Problem statement
     - Solution explanation  
     - Security benefits
     - Compliance information
     - Management communication templates
   
2. **`SCHEMA_ONLY_PROMPTING_COMPARISON.md`** (English)
   - **Audience**: Developers, Security Officers, Technical Staff
   - **Purpose**: Technical comparison and implementation details
   - **Content**:
     - Before/after code examples
     - Performance metrics
     - Testing procedures
     - Impact analysis
     - Migration notes

#### Quick Start

**For Management** → Read `SECURITY_SCHEMA_ONLY_PROMPTING.md`  
**For Developers** → Read `SCHEMA_ONLY_PROMPTING_COMPARISON.md`  
**For Testing** → Run `/test_schema_only.py` in project root

#### Summary

Schema-Only Prompting prevents sensitive laboratory data from being transmitted to external AI services (OpenAI, Gemini) by sending only DataFrame metadata (column names, types, structure) instead of actual test results, client names, or sample IDs.

**Security Level**: 🔒 Maximum Privacy  
**Compliance**: ✅ ISO 17025, GDPR, Saudi PDPL  
**Status**: ✅ Implemented and Tested

---

**Last Updated**: 2025-12-08  
**Version**: 1.0
