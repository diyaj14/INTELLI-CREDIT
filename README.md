<target_file>d:\GITHUB\IITH\README.md</target_file>
<file_contents>
# Intelli-Credit: Next-Gen Corporate Credit Appraisal 🏦⚡

**Intelli-Credit** is an AI-powered system designed to replace a senior bank credit manager's 3-week manual credit appraisal workflow with a seamless **3-minute AI workflow**. Developed for the Indian corporate credit ecosystem, it bridges the intelligence gap by automating data ingestion, synthesizing market research, cross-validating GST compliance, and generating a transparent, regulator-ready Credit Appraisal Memo (CAM).

![Intelli-Credit Dashboard](frontend/assets/dashboard_preview.png) *(Note: Ensure you have your screenshots here)*

---

## 🚀 The Core Problem & Solution

**The Problem:** The Indian corporate credit lifecycle is bogged down by manual document collection, cross-linking of 40+ documents from 8+ sources, and slow, opaque decision-making. 
**The Solution:** Intelli-Credit solves this by ingesting PDFs, Excel files, and CA-certified documents, running them through an advanced AI pipeline, and outputting an Explainable AI (XAI) rating.

### Three Pillars of Intelli-Credit:
1. **M1: Document Intelligence (Data Ingest)**
   - Extracts structured and unstructured data from Indian financial documents using `pdfplumber` and `PaddleOCR`.
   - Computes the "Five Cs of Credit" (Character, Capacity, Capital, Collateral, Conditions) and key Indian banking ratios (DSCR, Current Ratio).
   - Simulates GST mismatch detection (GSTR-2A vs GSTR-3B) to flag potential circular trading.

2. **M2: Live Web Research Agent (Market Sentiment)**
   - Active ReAct agent that searches the web in real-time.
   - Monitors **MCA (Ministry of Corporate Affairs) data**, checks **e-Courts** for director litigation history, and aggregates latest news sentiment.

3. **M3: Decision Engine & Explainability (Scorer)**
   - Fuses extracted financials, qualitative risks, and market sentiment into a transparent scorecard.
   - Uses localized Indian parameters aligned with RBI Early Warning Signals (EWS) to determine risk.
   - Outputs a professional, downloadable **PDF Credit Appraisal Memo (CAM)** with fully cited sources.

---

## 🏗️ System Architecture

The project employs a modern, localized stack tailored specifically to Indian financial structures.

*   **Frontend:** Premium dark-mode interface built with HTML5, CSS3 (Vanilla), and JavaScript. Fully responsive glassmorphic UI.
*   **Backend Server:** **Python FastAPI / Flask** (via `backend/app.py`).
*   **AI Orchestration:** **LangChain** and **LlamaIndex** managing the ReAct web research agent.
*   **LLM Engine:** Local **Ollama** integration for secure financial processing, with fallbacks to **Groq** (Llama-3), **Gemini 3 Pro**, or **OpenRouter**.
*   **Data Processing:** `Pandas`, `NumPy`, `pdfplumber`, `unstructured.io`. Web research powered by `Tavily API`.

### Workflow Diagram
1. **Upload:** User uploads Annual Reports (PDF) & GST Returns.
2. **Ingest (Split):** Text goes to LLM extraction, Tables go to deterministic parsing.
3. **Research:** RAG architecture searches live news/legal repositories using the extracted Director/Company names.
4. **Score:** Transparent Logistic Regression assigns weights to Financial Health, GST Compliance, and Litigation.
5. **Output:** Dashboard visualizes risk matrices; user downloads generated CAM.

---

## 💻 How to Run Locally

Follow these steps to deploy Intelli-Credit on your local machine.

### Prerequisites
*   Python 3.11+
*   Git

### 1. Clone the Repository
```bash
git clone https://github.com/diyaj14/INTELLI-CREDIT.git
cd INTELLI-CREDIT
```

### 2. Install Dependencies
Set up your virtual environment and install the required Python packages.
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Environment Variables
Create a `.env` file in the root directory and add your API keys:
```env
# Required for Web Research Agent
TAVILY_API_KEY=your_tavily_api_key_here

# LLM Providers (Add whichever you plan to use)
GROQ_API_KEY=your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
OPENROUTER_API_KEY=your_openrouter_api_key_here

# (Optional) For Local LLM usage, ensure Ollama is installed and running
```

### 4. Run the Application
Start the unified Python backend server:
```bash
python backend/app.py
```
*(The server typically runs on port 8001 or 8000).*

### 5. Access the Dashboard
Open your web browser and navigate to:
```
http://localhost:8001/
```
From here, click "Start Analysis" to land on the `dashboard.html`, upload a PDF Document (e.g., Annual Report), and click **Execute Full Audit** to watch the AI in action!

---

## 🏆 Hackathon Context
This project was built for the **IIT Hyderabad Intelli-Credit Challenge**. 

**Distinguishing Wow Factors:**
*   **Explainable Rejections:** Not just a black box score. Every penalty has a source citation (e.g. *"-18 pts due to active litigation found on eCourts"*).
*   **"3 Minutes vs. 3 Weeks":** A live demonstration of massive operational cost reduction in loan underwriting.
*   **Indian Context:** Built natively to handle Indian accounting standards, GSTIN validation simulated logic, and MSME constraints.
</file_contents>
