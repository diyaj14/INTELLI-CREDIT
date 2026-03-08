import sys
import os
sys.path.insert(0, os.getcwd())
try:
    from modules.document_intelligence.document_pipeline import run_pipeline
    print("Document Pipeline import successful")
except Exception as e:
    print(f"Import failed: {e}")
    import traceback
    traceback.print_exc()
