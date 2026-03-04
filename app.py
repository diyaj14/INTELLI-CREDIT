
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import shutil
import uuid
from typing import List, Optional
from orchestrator import orchestrate

app = FastAPI()

# Temporary directory for uploads
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Static files and templates
os.makedirs("static", exist_ok=True)
templates = Jinja2Templates(directory="templates") if os.path.exists("templates") else None

@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open("index.html", "r") as f:
        return f.read()

@app.post("/analyze")
async def analyze(
    files: List[UploadFile] = File(None),
    company_name: str = Form(None),
    gstin: str = Form(None),
    promoter_names: str = Form(None),
    primary_insights: str = Form(None),
    demo_mode: bool = Form(False)
):
    # Process files
    file_paths = []
    if files:
        session_id = str(uuid.uuid4())
        session_dir = os.path.join(UPLOAD_DIR, session_id)
        os.makedirs(session_dir, exist_ok=True)
        
        for file in files:
            if file.filename:
                file_path = os.path.join(session_dir, file.filename)
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                file_paths.append(file_path)

    # Process promoters list
    promoters_list = [p.strip() for p in promoter_names.split(",")] if promoter_names else []

    # Run orchestration
    try:
        # If no files and no company name, we can't do much unless it's a demo
        if not file_paths and not company_name:
            demo_mode = True
            company_name = "Apex Textiles" # Default demo company
            
        result = orchestrate(
            uploaded_files=file_paths,
            company_name=company_name,
            gstin=gstin,
            promoter_names=promoters_list,
            primary_insights=primary_insights
        )
        return JSONResponse(content=result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(content={"error": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
