import os
import sys

# Minimal path: ONLY current dir and venv site-packages
project_root = os.path.abspath(os.path.dirname(__file__))
venv_site = os.path.join(project_root, "venv", "Lib", "site-packages")
venv_lib = os.path.join(project_root, "venv", "Lib")
# Need standard lib for basic types, but let's see if we can get it from venv
# Actually, venv on windows usually only has site-packages.

sys.path = [project_root, venv_site, venv_lib]

# Add back ONLY the standard lib (no site-packages)
sys.path.append(r"D:\python 3.12\Lib")
sys.path.append(r"D:\python 3.12\DLLs")

print("--- 🔬 Minimal Path Test ---")
for p in sys.path:
    print(f"  {p}")

try:
    from langchain.agents import AgentExecutor
    print("✅ AgentExecutor imported successfully from venv!")
    
    from modules.research_agent.research_pipeline import run_research
    print("✅ Pipeline imported successfully!")
    
    res = run_research("Apex Textiles", ["Ramesh Gupta"], demo_mode=True)
    import json
    print(json.dumps(res, indent=2))
    
except Exception as e:
    print(f"❌ Failed: {e}")
    import traceback
    traceback.print_exc()
