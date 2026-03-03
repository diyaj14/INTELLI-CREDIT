"""
pdf_ingestor.py — Module 1: Document Intelligence
==================================================
Handles all PDF ingestion for Intelli-Credit.

Supports:
  - Text-based PDFs (pdfplumber)      — annual reports, financial statements
  - Table extraction (Camelot/pdfplumber) — P&L, Balance Sheet grids
  - Scanned/image PDFs (PaddleOCR)    — old bank-stamped documents, ITRs

Usage:
    ingestor = PDFIngestor()
    result = ingestor.ingest("path/to/annual_report.pdf")
    # result = {
    #     "raw_text": {1: "Page 1 text...", 2: "Page 2 text..."},
    #     "tables":   [DataFrame1, DataFrame2, ...],
    #     "page_count": 42,
    #     "pdf_type": "text",   # or "scanned"
    #     "confidence": 0.95,
    # }
"""

import os
import logging
import tempfile
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: safe import guard for heavy libs (they take time to import)
# ─────────────────────────────────────────────────────────────────────────────

def _try_import_pdfplumber():
    try:
        import pdfplumber
        return pdfplumber
    except ImportError:
        logger.warning("pdfplumber not installed. Text extraction unavailable.")
        return None


def _try_import_camelot():
    try:
        import camelot
        return camelot
    except ImportError:
        logger.warning("camelot-py not installed. Table extraction via camelot unavailable.")
        return None


def _try_import_paddleocr():
    try:
        from paddleocr import PaddleOCR
        return PaddleOCR
    except ImportError:
        logger.warning("paddleocr not installed. OCR unavailable.")
        return None


def _try_import_pdf2image():
    try:
        from pdf2image import convert_from_path
        return convert_from_path
    except ImportError:
        logger.warning("pdf2image not installed. Scanned PDF conversion unavailable.")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Main Class
# ─────────────────────────────────────────────────────────────────────────────

class PDFIngestor:
    """
    Ingests PDFs of any type — text-based or scanned — and returns
    structured text and table data for downstream financial extraction.
    """

    # Minimum number of characters per page to consider it "text-based"
    TEXT_CONFIDENCE_THRESHOLD = 50

    def __init__(self, ocr_language: str = "en"):
        """
        Args:
            ocr_language: Language code for PaddleOCR. Use 'en' for English-only,
                          or 'en' (PaddleOCR handles Hindi mixed docs reasonably well).
        """
        self.ocr_language = ocr_language
        self._ocr_engine = None  # lazy-loaded to avoid slow startup

    # ── Type Detection ────────────────────────────────────────────────────────

    def detect_pdf_type(self, filepath: str) -> str:
        """
        Detects whether a PDF is text-based (has a text layer) or scanned (image-only).

        Returns:
            "text"    — PDF has selectable text → use pdfplumber
            "scanned" — PDF is image-only → use PaddleOCR
            "mixed"   — Some pages have text, some are images
        """
        pdfplumber = _try_import_pdfplumber()
        if pdfplumber is None:
            return "scanned"  # fallback to OCR if pdfplumber unavailable

        text_pages = 0
        scanned_pages = 0

        try:
            with pdfplumber.open(filepath) as pdf:
                total = len(pdf.pages)
                # Sample up to 5 pages to determine type (avoid reading huge docs)
                sample_pages = pdf.pages[:min(5, total)]

                for page in sample_pages:
                    text = page.extract_text() or ""
                    char_count = len(text.strip())
                    if char_count >= self.TEXT_CONFIDENCE_THRESHOLD:
                        text_pages += 1
                    else:
                        scanned_pages += 1

        except Exception as e:
            logger.error(f"detect_pdf_type error on {filepath}: {e}")
            return "scanned"

        if scanned_pages == 0:
            return "text"
        elif text_pages == 0:
            return "scanned"
        else:
            return "mixed"

    # ── Text Extraction (Text-Based PDFs) ────────────────────────────────────

    def extract_text_from_text_pdf(self, filepath: str) -> dict:
        """
        Extracts text from a text-based PDF using pdfplumber.

        Returns:
            {page_num (1-indexed): extracted_text_string}
        """
        pdfplumber = _try_import_pdfplumber()
        if pdfplumber is None:
            return {}

        page_text = {}
        try:
            with pdfplumber.open(filepath) as pdf:
                for i, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text() or ""
                    page_text[i] = text.strip()
                    logger.debug(f"Page {i}: {len(text)} chars extracted")
        except Exception as e:
            logger.error(f"Text extraction failed on {filepath}: {e}")

        return page_text

    # ── Table Extraction ──────────────────────────────────────────────────────

    def extract_tables(self, filepath: str) -> list:
        """
        Extracts tables from a PDF.

        Strategy:
          1. First tries Camelot (better accuracy for structured financial tables)
          2. Falls back to pdfplumber table extraction if Camelot fails

        Returns:
            List of pandas DataFrames, one per detected table.
        """
        tables = []

        # ── Strategy 1: Camelot ──────────────────────────────────────────────
        camelot = _try_import_camelot()
        if camelot:
            try:
                # "lattice" mode works on tables with visible grid lines (most Indian financials)
                camelot_tables = camelot.read_pdf(
                    filepath,
                    pages="all",
                    flavor="lattice",
                    suppress_stdout=True,
                )

                if len(camelot_tables) == 0:
                    # Try "stream" mode for tables without grid lines
                    camelot_tables = camelot.read_pdf(
                        filepath,
                        pages="all",
                        flavor="stream",
                        suppress_stdout=True,
                    )

                for tbl in camelot_tables:
                    df = tbl.df
                    # Use first row as header if it looks like a header row
                    df = self._clean_table_dataframe(df)
                    if not df.empty:
                        tables.append(df)

                if tables:
                    logger.info(f"Camelot extracted {len(tables)} tables from {filepath}")
                    return tables

            except Exception as e:
                logger.warning(f"Camelot failed on {filepath}: {e} — trying pdfplumber fallback")

        # ── Strategy 2: pdfplumber fallback ──────────────────────────────────
        pdfplumber = _try_import_pdfplumber()
        if pdfplumber:
            try:
                with pdfplumber.open(filepath) as pdf:
                    for i, page in enumerate(pdf.pages, start=1):
                        page_tables = page.extract_tables()
                        if page_tables:
                            for raw_tbl in page_tables:
                                if raw_tbl:
                                    df = pd.DataFrame(raw_tbl)
                                    df = self._clean_table_dataframe(df)
                                    if not df.empty:
                                        tables.append(df)
                logger.info(f"pdfplumber extracted {len(tables)} tables from {filepath}")
            except Exception as e:
                logger.error(f"pdfplumber table extraction failed on {filepath}: {e}")

        return tables

    # ── OCR Extraction (Scanned PDFs) ─────────────────────────────────────────

    def extract_text_from_scanned_pdf(self, filepath: str) -> dict:
        """
        Extracts text from a scanned (image-based) PDF using PaddleOCR.

        Process:
          1. Convert PDF pages to images (pdf2image)
          2. Run PaddleOCR on each image
          3. Concatenate detected text lines per page

        Returns:
            {page_num (1-indexed): ocr_text_string}
        """
        convert_from_path = _try_import_pdf2image()
        PaddleOCR = _try_import_paddleocr()

        if convert_from_path is None or PaddleOCR is None:
            logger.error("Cannot perform OCR: pdf2image or paddleocr not installed.")
            return {}

        # Lazy init OCR engine (takes ~3-5 seconds first time)
        if self._ocr_engine is None:
            logger.info("Initializing PaddleOCR engine (first-time load)...")
            self._ocr_engine = PaddleOCR(
                lang=self.ocr_language,
                use_angle_cls=True,   # handles rotated text (common in Indian scans)
                show_log=False,
            )

        page_text = {}

        try:
            # Convert PDF → list of PIL images (one per page)
            images = convert_from_path(
                filepath,
                dpi=200,              # 200 DPI is sufficient for OCR accuracy
                fmt="jpeg",
            )
        except Exception as e:
            logger.error(f"PDF→image conversion failed for {filepath}: {e}")
            return {}

        for i, image in enumerate(images, start=1):
            # Save image to temp file for PaddleOCR (it needs a file path)
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp_path = tmp.name
                image.save(tmp_path, "JPEG")

            try:
                result = self._ocr_engine.ocr(tmp_path, cls=True)
                # result structure: [[[box, (text, confidence)], ...]]
                lines = []
                if result and result[0]:
                    for line in result[0]:
                        if line and len(line) >= 2:
                            text_conf = line[1]
                            if text_conf and len(text_conf) >= 1:
                                lines.append(text_conf[0])
                page_text[i] = "\n".join(lines)
                logger.debug(f"OCR page {i}: {len(lines)} text lines detected")
            except Exception as e:
                logger.warning(f"OCR failed on page {i} of {filepath}: {e}")
                page_text[i] = ""
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        return page_text

    # ── Main Entry Point ──────────────────────────────────────────────────────

    def ingest(self, filepath: str) -> dict:
        """
        Main entry point. Auto-detects PDF type and runs the appropriate pipeline.

        Args:
            filepath: Absolute or relative path to the PDF file.

        Returns:
            {
                "raw_text":   {page_num: text},
                "tables":     [DataFrame, ...],
                "page_count": int,
                "pdf_type":   "text" | "scanned" | "mixed",
                "confidence": float,   # 0–1, based on text density
                "filepath":   str,
            }
        """
        filepath = str(Path(filepath).resolve())

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"PDF not found: {filepath}")

        logger.info(f"Ingesting: {os.path.basename(filepath)}")

        pdf_type = self.detect_pdf_type(filepath)
        logger.info(f"Detected PDF type: {pdf_type}")

        raw_text = {}
        tables = []

        if pdf_type == "text":
            raw_text = self.extract_text_from_text_pdf(filepath)
            tables = self.extract_tables(filepath)

        elif pdf_type == "scanned":
            raw_text = self.extract_text_from_scanned_pdf(filepath)
            # Tables from scanned PDFs need OCR first; extract from raw_text later

        elif pdf_type == "mixed":
            # Extract text pages normally, OCR scanned pages
            pdfplumber = _try_import_pdfplumber()
            if pdfplumber:
                with pdfplumber.open(filepath) as pdf:
                    total_pages = len(pdf.pages)

                    for i, page in enumerate(pdf.pages, start=1):
                        text = (page.extract_text() or "").strip()
                        if len(text) >= self.TEXT_CONFIDENCE_THRESHOLD:
                            raw_text[i] = text
                        else:
                            # OCR this page individually
                            # Create a single-page temp PDF
                            pass  # fallback: use OCR on entire doc

                # Simple fallback: run full OCR and merge
                ocr_text = self.extract_text_from_scanned_pdf(filepath)
                for pg, text in ocr_text.items():
                    if pg not in raw_text or not raw_text[pg]:
                        raw_text[pg] = text

            tables = self.extract_tables(filepath)

        page_count = self._get_page_count(filepath)
        confidence = self._compute_confidence(raw_text, page_count)

        result = {
            "raw_text":   raw_text,
            "tables":     tables,
            "page_count": page_count,
            "pdf_type":   pdf_type,
            "confidence": round(confidence, 3),
            "filepath":   filepath,
        }

        total_chars = sum(len(t) for t in raw_text.values())
        logger.info(
            f"Ingest complete: {page_count} pages, {len(tables)} tables, "
            f"{total_chars} chars, confidence={confidence:.2f}"
        )
        return result

    # ── Private Helpers ───────────────────────────────────────────────────────

    def _get_page_count(self, filepath: str) -> int:
        """Returns total page count of the PDF."""
        pdfplumber = _try_import_pdfplumber()
        if pdfplumber:
            try:
                with pdfplumber.open(filepath) as pdf:
                    return len(pdf.pages)
            except Exception:
                pass
        return 0

    def _compute_confidence(self, raw_text: dict, page_count: int) -> float:
        """
        Estimates extraction confidence based on text density.
        A page with 300+ chars is considered well-extracted.
        Returns 0.0–1.0.
        """
        if page_count == 0 or not raw_text:
            return 0.0

        well_extracted = sum(
            1 for text in raw_text.values()
            if len(text) >= 300
        )
        return well_extracted / page_count

    def _clean_table_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Cleans a raw DataFrame extracted from PDF:
        - Drops fully empty rows/columns
        - Promotes first row to header if it looks like a header
        - Strips whitespace from all cells
        """
        if df is None or df.empty:
            return pd.DataFrame()

        # Strip whitespace (applymap was renamed to map in pandas 3.0)
        df = df.map(lambda x: str(x).strip() if x is not None else "")

        # Drop fully empty rows and columns (work with string data, not pd.NA)
        df = df[~df.apply(lambda row: all(v == "" or v == "None" for v in row), axis=1)]
        df = df.loc[:, ~df.apply(lambda col: all(v == "" or v == "None" for v in col), axis=0)]

        if df.empty:
            return pd.DataFrame()

        # If first row looks like a header (contains mostly strings, not numbers),
        # promote it
        first_row = df.iloc[0].tolist()
        numeric_count = sum(
            1 for v in first_row
            if str(v).replace(".", "").replace("-", "").replace(",", "").strip().isdigit()
        )
        if numeric_count < len(first_row) / 2:
            df.columns = [str(v) for v in first_row]
            df = df.iloc[1:].reset_index(drop=True)

        return df
