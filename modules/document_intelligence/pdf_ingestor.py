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

def _try_import_cv2():
    try:
        import cv2
        return cv2
    except ImportError:
        logger.warning("cv2 not installed. Image preprocessing unavailable.")
        return None

def _try_import_numpy():
    try:
        import numpy as np
        return np
    except ImportError:
        logger.warning("numpy not installed. Image preprocessing unavailable.")
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

    def _preprocess_image_for_ocr(self, image_path: str) -> str:
        """
        Preprocesses image for OCR using OpenCV to handle skewed, noisy bank/tax documents.
        Steps: Deskew -> Denoise -> Binarize/Contrast Enhancement.
        """
        cv2 = _try_import_cv2()
        np = _try_import_numpy()

        if cv2 is None or np is None:
            return image_path

        try:
            img = cv2.imread(image_path)
            if img is None:
                return image_path

            # 1. Grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # 2. Deskew (Deskewing Indian stamped documents)
            thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
            coords = np.column_stack(np.where(thresh > 0))
            if len(coords) > 0:
                angle = cv2.minAreaRect(coords)[-1]
                if angle < -45:
                    angle = -(90 + angle)
                else:
                    angle = -angle

                if abs(angle) > 0.5 and abs(angle) < 45:  # Only deskew if confident
                    (h, w) = img.shape[:2]
                    center = (w // 2, h // 2)
                    M = cv2.getRotationMatrix2D(center, angle, 1.0)
                    gray = cv2.warpAffine(
                        gray, M, (w, h),
                        flags=cv2.INTER_CUBIC,
                        borderMode=cv2.BORDER_REPLICATE
                    )

            # 3. Denoise
            denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)

            # 4. Enhance contrast / Binarize
            processed = cv2.adaptiveThreshold(
                denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 11, 2
            )

            processed_path = image_path.replace(".jpg", "_processed.jpg")
            cv2.imwrite(processed_path, processed)
            
            logger.debug(f"Applied OpenCV preprocessing to {image_path}")
            return processed_path

        except Exception as e:
            logger.warning(f"OpenCV preprocessing failed: {e}")
            return image_path

    def extract_text_from_scanned_pdf(self, filepath: str) -> dict:
        """
        Extracts text from a scanned (image-based) PDF using PaddleOCR with a 
        robust Gemini Vision fallback.
        """
        convert_from_path = _try_import_pdf2image()
        PaddleOCR = _try_import_paddleocr()
        page_text = {}

        # ── Strategy 1: Attempt PaddleOCR (Local) ─────────────────────────────
        if PaddleOCR is not None and convert_from_path is not None:
            if self._ocr_engine is None:
                logger.info("Initializing PaddleOCR engine...")
                try:
                    self._ocr_engine = PaddleOCR(lang=self.ocr_language, use_angle_cls=True, show_log=False)
                except Exception as e:
                    logger.warning(f"PaddleOCR init failed: {e}. Switching to Vision Fallback.")
                    PaddleOCR = None

            if self._ocr_engine:
                try:
                    images = convert_from_path(filepath, dpi=200, fmt="jpeg")
                    for i, image in enumerate(images, start=1):
                        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                            tmp_path = tmp.name
                            image.save(tmp_path, "JPEG")
                        final_img_path = self._preprocess_image_for_ocr(tmp_path)
                        result = self._ocr_engine.ocr(final_img_path, cls=True)
                        lines = [line[1][0] for line in result[0]] if result and result[0] else []
                        page_text[i] = "\n".join(lines)
                        os.unlink(tmp_path)
                    return page_text
                except Exception as e:
                    logger.warning(f"PaddleOCR processing failed: {e}. Switching to Vision Fallback.")

        # ── Strategy 2: Gemini Vision Fallback (Agentic) ──────────────────────
        logger.info("🚀 PaddleOCR unavailable/failed. Engaging Gemini Vision Fallback...")
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.error("Vision Fallback failed: GEMINI_API_KEY missing.")
            return {}

        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            
            # Since we can't use pdf2image without poppler, we try to get images via pdfplumber
            pdfplumber = _try_import_pdfplumber()
            if not pdfplumber: return {}
            
            with pdfplumber.open(filepath) as pdf:
                # We limit vision to first 10 pages for cost/speed
                target_pages = pdf.pages[:10]
                for i, page in enumerate(target_pages, start=1):
                    # Representation to Gemini
                    img = page.to_image(resolution=150)
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                        img_path = tmp.name
                        img.save(img_path)
                    
                    with open(img_path, "rb") as f:
                        img_data = f.read()
                    
                    resp = model.generate_content([
                        "Transcribe all text from this financial document page. Maintain tables as plain text.",
                        {"mime_type": "image/png", "data": img_data}
                    ])
                    page_text[i] = resp.text
                    os.unlink(img_path)
            
            return page_text
        except Exception as e:
            logger.error(f"Vision Fallback totally failed: {e}")
            return {}

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
