

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import os
import shutil
import uuid
from typing import List, Optional
from orchestrator import orchestrate

app = FastAPI()

# Allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow any origin (e.g. live server)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Temporary directory for uploads
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)





FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
REPORTS_DIR = os.path.abspath(os.path.join(os.getcwd(), "reports"))
os.makedirs(REPORTS_DIR, exist_ok=True)


app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")
app.mount("/reports", StaticFiles(directory=REPORTS_DIR), name="reports")

# Global progress tracker
progress_store = {}


@app.get("/status/{session_id}")
async def get_status(session_id: str):
    data = progress_store.get(session_id, {"status": "starting", "progress": 0})
    if data.get("status") == "ERROR":
        # Pass the error message to the frontend if available
        return JSONResponse(content={"status": f"ERROR: {data.get('error', 'Unknown Error')}", "progress": 85})
    return JSONResponse(content=data)


@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        # Check root dir for index.html if frontend folder is missing
        if os.path.exists("index.html"):
            with open("index.html", "r", encoding="utf-8") as f:
                return f.read()
    return "Index not found"


@app.get("/{filename}")
async def get_frontend_file(filename: str):
    from fastapi.responses import FileResponse
    file_path = os.path.join(FRONTEND_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return JSONResponse(content={"error": "File not found"}, status_code=404)




from fastapi import BackgroundTasks

def run_orchestration_task(session_id, file_paths, company_name, gstin, promoters_list, primary_insights, demo_mode, llm_provider):
    try:
        # If no files and no company name, activate demo mode
        if not file_paths and not company_name:
            demo_mode = True
            company_name = "Apex Textiles" 
            
        def update_progress(msg, progress_val):
            progress_store[session_id] = {"status": msg, "progress": progress_val}

        result = orchestrate(
            uploaded_files=file_paths,
            company_name=company_name,
            gstin=gstin,
            promoter_names=promoters_list,
            primary_insights=primary_insights,
            demo_mode=demo_mode,
            progress_callback=update_progress,
            llm_provider=llm_provider
        )
        
        # Store final result when done
        progress_store[session_id] = {
            "status": "COMPLETED", 
            "progress": 100, 
            "result": result
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        progress_store[session_id] = {"status": "ERROR", "error": str(e)}

@app.post("/analyze")
async def analyze(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(None),
    company_name: str = Form(None),
    gstin: str = Form(None),
    promoter_names: str = Form(None),
    primary_insights: str = Form(None),
    demo_mode: bool = Form(False),
    llm_provider: Optional[str] = Form(None)
):
    session_id = str(uuid.uuid4())
    print(f"DEBUG: Starting Async Analysis for Session {session_id}")
    
    file_paths = []
    if files:
        session_dir = os.path.join(UPLOAD_DIR, session_id)
        os.makedirs(session_dir, exist_ok=True)
        for file in files:
            if file.filename:
                file_path = os.path.join(session_dir, file.filename)
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                file_paths.append(file_path)

    promoters_list = [p.strip() for p in promoter_names.split(",")] if promoter_names else []
    
    # Initialize status
    progress_store[session_id] = {"status": "Uploading & Initializing...", "progress": 0}

    # Start background task
    background_tasks.add_task(
        run_orchestration_task, 
        session_id, file_paths, company_name, gstin, promoters_list, primary_insights, demo_mode, llm_provider
    )

    return JSONResponse(content={"session_id": session_id})


if __name__ == "__main__":
    import uvicorn
    # Use actual absolute path for backend to avoid issues
    uvicorn.run(app, host="0.0.0.0", port=8001)
