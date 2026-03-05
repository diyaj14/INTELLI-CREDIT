"""
test_low_confidence_fields.py — Tests for Feature 5: Low Confidence Fields
======================================================================
Tests that the pipeline includes `low_confidence_fields` in Output.
"""

import pytest
from modules.document_intelligence.document_pipeline import run_pipeline

class TestLowConfidenceFields:

    def test_demo_mode_includes_low_confidence_fields(self):
        result = run_pipeline([], demo_mode=True)
        assert "low_confidence_fields" in result
        assert isinstance(result["low_confidence_fields"], list)

    def test_non_demo_mode_includes_low_confidence_fields(self):
        result = run_pipeline([], demo_mode=False)
        assert "low_confidence_fields" in result
        assert isinstance(result["low_confidence_fields"], list)

        # In a fully default pipeline (no PDFs), everything is defaulted,
        # so all fields have confidence 0.20 or 0.50 (default).
        # We expect all basic financial fields to be populated as low confidence!
        assert len(result["low_confidence_fields"]) >= 10
        assert "revenue_cr" in result["low_confidence_fields"]
        assert "ebitda_cr" in result["low_confidence_fields"]
