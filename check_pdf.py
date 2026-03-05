
import pdfplumber
import sys

def check_pdf(path):
    try:
        with pdfplumber.open(path) as pdf:
            print(f"Total pages: {len(pdf.pages)}")
            for i, page in enumerate(pdf.pages[:10]):
                text = page.extract_text() or ""
                print(f"Page {i+1} text length: {len(text)}")
                if text:
                    print(f"Sample text from page {i+1}: {text[:200]}")
                print("-" * 20)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_pdf(r"e:\itellicredit-final\INTELLI-CREDIT\sample-cam.pdf")
