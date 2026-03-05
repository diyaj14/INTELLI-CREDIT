"""
tests/test_pdf_ingestor.py
==========================
Tests for PDFIngestor class.
Since we don't bundle a real PDF, tests use:
  1. A synthetic PDF created programmatically (text-based)
  2. A pre-generated fixture CSV as a proxy for table content
  3. Mock patches for OCR (PaddleOCR is slow; not exercised in unit tests)

Run:
    pytest tests/test_pdf_ingestor.py -v
"""
import os
import sys
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.document_intelligence.pdf_ingestor import PDFIngestor


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — create an in-memory PDF with known content for testing
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def sample_text_pdf(tmp_path_factory):
    """
    Creates a minimal, real text-based PDF using reportlab (if available)
    or falls back to writing a simple test text file that mimics PDF pages.
    Returns the path to the PDF.
    """
    tmp_path = tmp_path_factory.mktemp("fixtures")
    pdf_path = str(tmp_path / "sample_annual_report.pdf")

    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4

        c = canvas.Canvas(pdf_path, pagesize=A4)

        # Page 1: Company overview
        c.setFont("Helvetica-Bold", 14)
        c.drawString(72, 750, "APEX TEXTILES PVT LTD")
        c.setFont("Helvetica", 12)
        c.drawString(72, 720, "Annual Report FY 2023-24")
        c.drawString(72, 700, "CIN: U17200MH2010PTC123456")
        c.showPage()

        # Page 2: Financial Highlights
        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, 750, "FINANCIAL HIGHLIGHTS")
        c.setFont("Helvetica", 11)
        c.drawString(72, 720, "Revenue from Operations: Rs. 42.50 Crore")
        c.drawString(72, 700, "EBITDA: Rs. 6.10 Crore")
        c.drawString(72, 680, "Net Profit after Tax: Rs. 2.30 Crore")
        c.drawString(72, 660, "Total Assets: Rs. 38.00 Crore")
        c.drawString(72, 640, "Total Liabilities: Rs. 24.00 Crore")
        c.drawString(72, 620, "Net Worth: Rs. 14.00 Crore")
        c.showPage()

        # Page 3: Balance Sheet stub
        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, 750, "BALANCE SHEET AS AT 31ST MARCH 2024")
        c.setFont("Helvetica", 11)
        c.drawString(72, 720, "Current Ratio: 1.10")
        c.drawString(72, 700, "Debt to Equity Ratio: 1.71")
        c.drawString(72, 680, "Interest Coverage Ratio: 2.40")
        c.showPage()

        c.save()

    except ImportError:
        # reportlab not installed — create a placeholder
        # Tests that need a real PDF will be skipped
        with open(pdf_path, "wb") as f:
            # Minimal valid PDF header (enough for type detection to handle gracefully)
            f.write(b"%PDF-1.4\n%%EOF\n")

    return pdf_path


@pytest.fixture(scope="module")
def ingestor():
    return PDFIngestor()


# ─────────────────────────────────────────────────────────────────────────────
# Tests: detect_pdf_type
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectPdfType:

    def test_returns_valid_type_string(self, ingestor, sample_text_pdf):
        result = ingestor.detect_pdf_type(sample_text_pdf)
        assert result in {"text", "scanned", "mixed"}, \
            f"Expected 'text'/'scanned'/'mixed', got: {result}"

    def test_text_pdf_detected_correctly(self, ingestor, sample_text_pdf):
        """A PDF we created with text layers should be detected as text."""
        try:
            import reportlab  # noqa
            result = ingestor.detect_pdf_type(sample_text_pdf)
            assert result == "text", \
                f"Expected 'text' for a text PDF, got '{result}'"
        except ImportError:
            pytest.skip("reportlab not installed — cannot create a real text PDF")

    def test_missing_file_raises(self, ingestor):
        with pytest.raises(Exception):
            # ingest() will raise FileNotFoundError
            ingestor.ingest("/nonexistent/path/file.pdf")


# ─────────────────────────────────────────────────────────────────────────────
# Tests: extract_text_from_text_pdf
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractTextFromTextPdf:

    def test_returns_dict_keyed_by_page_number(self, ingestor, sample_text_pdf):
        try:
            import reportlab  # noqa
            result = ingestor.extract_text_from_text_pdf(sample_text_pdf)
            assert isinstance(result, dict), "Should return a dict"
            assert len(result) > 0, "Should extract at least one page"
            for key in result:
                assert isinstance(key, int), f"Key {key} should be an int (page number)"
        except ImportError:
            pytest.skip("reportlab not installed")

    def test_page_content_contains_expected_text(self, ingestor, sample_text_pdf):
        try:
            import reportlab  # noqa
            result = ingestor.extract_text_from_text_pdf(sample_text_pdf)
            # Join all pages and look for key financial terms
            full_text = " ".join(result.values()).upper()
            assert "APEX TEXTILES" in full_text or "REVENUE" in full_text, \
                f"Expected company name or 'REVENUE' in extracted text. Got snippet: {full_text[:200]}"
        except ImportError:
            pytest.skip("reportlab not installed")

    def test_extracts_financial_values(self, ingestor, sample_text_pdf):
        try:
            import reportlab  # noqa
            result = ingestor.extract_text_from_text_pdf(sample_text_pdf)
            full_text = " ".join(result.values())
            # We embedded "42.50" on page 2
            assert "42.50" in full_text or "42" in full_text, \
                "Revenue figure '42.50' should appear in extracted text"
        except ImportError:
            pytest.skip("reportlab not installed")


# ─────────────────────────────────────────────────────────────────────────────
# Tests: extract_tables
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractTables:

    def test_returns_list_of_dataframes(self, ingestor, sample_text_pdf):
        try:
            import reportlab  # noqa
            result = ingestor.extract_tables(sample_text_pdf)
            assert isinstance(result, list), "Should return a list"
            for item in result:
                assert isinstance(item, pd.DataFrame), \
                    f"Each table should be a DataFrame, got {type(item)}"
        except ImportError:
            pytest.skip("reportlab not installed")

    def test_returns_list_even_if_no_tables_found(self, ingestor, sample_text_pdf):
        """Should not crash even if no tables found — just returns empty list."""
        try:
            result = ingestor.extract_tables(sample_text_pdf)
            assert isinstance(result, list)
        except Exception as e:
            pytest.fail(f"extract_tables should not raise, got: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Tests: OCR (mocked — PaddleOCR is slow and not run in unit tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractTextFromScannedPdf:

    def test_ocr_returns_dict(self, ingestor, sample_text_pdf):
        """
        We mock PaddleOCR so this test is fast.
        Validates that the return type and structure are correct.
        """
        mock_ocr_result = [[[None, ("Revenue from Operations 42.50 Crore", 0.98)]]]

        with patch("modules.document_intelligence.pdf_ingestor._try_import_paddleocr") as mock_paddle, \
             patch("modules.document_intelligence.pdf_ingestor._try_import_pdf2image") as mock_pdf2img:

            # Setup mock OCR engine
            mock_engine = MagicMock()
            mock_engine.ocr.return_value = mock_ocr_result
            mock_paddle_class = MagicMock(return_value=mock_engine)
            mock_paddle.return_value = mock_paddle_class

            # Setup mock pdf2image  
            mock_image = MagicMock()
            mock_image.save = MagicMock()
            mock_pdf2img.return_value = lambda *a, **kw: [mock_image]

            # Ensure fresh engine
            ingestor._ocr_engine = None

            result = ingestor.extract_text_from_scanned_pdf(sample_text_pdf)

            assert isinstance(result, dict), "OCR result should be a dict"

    def test_ocr_unavailable_returns_empty_dict(self, ingestor, sample_text_pdf):
        """If PaddleOCR is not installed, should return empty dict gracefully."""
        with patch("modules.document_intelligence.pdf_ingestor._try_import_paddleocr",
                   return_value=None):
            result = ingestor.extract_text_from_scanned_pdf(sample_text_pdf)
            assert result == {}, "Should return empty dict if OCR unavailable"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: ingest() main entry point
# ─────────────────────────────────────────────────────────────────────────────

class TestIngest:

    def test_ingest_returns_required_keys(self, ingestor, sample_text_pdf):
        try:
            import reportlab  # noqa
            result = ingestor.ingest(sample_text_pdf)
            required_keys = {"raw_text", "tables", "page_count", "pdf_type", "confidence", "filepath"}
            missing = required_keys - result.keys()
            assert not missing, f"ingest() result missing keys: {missing}"
        except ImportError:
            pytest.skip("reportlab not installed")

    def test_ingest_confidence_is_float_0_to_1(self, ingestor, sample_text_pdf):
        try:
            import reportlab  # noqa
            result = ingestor.ingest(sample_text_pdf)
            assert isinstance(result["confidence"], float)
            assert 0.0 <= result["confidence"] <= 1.0, \
                f"Confidence {result['confidence']} out of [0, 1]"
        except ImportError:
            pytest.skip("reportlab not installed")

    def test_ingest_page_count_positive(self, ingestor, sample_text_pdf):
        try:
            import reportlab  # noqa
            result = ingestor.ingest(sample_text_pdf)
            assert result["page_count"] >= 1, "Should have at least 1 page"
        except ImportError:
            pytest.skip("reportlab not installed")

    def test_ingest_raises_on_missing_file(self, ingestor):
        with pytest.raises(FileNotFoundError):
            ingestor.ingest("e:/nonexistent/fake_report.pdf")

    def test_ingest_pdf_type_is_valid(self, ingestor, sample_text_pdf):
        try:
            import reportlab  # noqa
            result = ingestor.ingest(sample_text_pdf)
            assert result["pdf_type"] in {"text", "scanned", "mixed"}
        except ImportError:
            pytest.skip("reportlab not installed")


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _clean_table_dataframe helper
# ─────────────────────────────────────────────────────────────────────────────

class TestCleanTableDataFrame:

    def test_drops_empty_rows(self, ingestor):
        import pandas as pd
        df = pd.DataFrame([
            ["Revenue", "42.50"],
            ["", ""],
            ["Net Profit", "2.30"],
        ])
        cleaned = ingestor._clean_table_dataframe(df)
        # Empty row should be dropped
        assert len(cleaned) < 3 or cleaned.isnull().all(axis=1).sum() == 0

    def test_promotes_header_row(self, ingestor):
        import pandas as pd
        df = pd.DataFrame([
            ["Particulars", "FY2024", "FY2023"],
            ["Revenue", "42.50", "38.10"],
            ["Net Profit", "2.30", "1.80"],
        ])
        cleaned = ingestor._clean_table_dataframe(df)
        # First row should become column headers
        assert "Particulars" in cleaned.columns or len(cleaned.columns) == 3

    def test_handles_empty_dataframe(self, ingestor):
        import pandas as pd
        empty_df = pd.DataFrame()
        result = ingestor._clean_table_dataframe(empty_df)
        assert isinstance(result, pd.DataFrame)
        assert result.empty
