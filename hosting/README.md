# 🐳 Intelli-Credit — Hosting Guide

This folder contains deployment files for different platforms.

---

## Files

| File | Use For |
|---|---|
| `Dockerfile` | Railway, Fly.io, Render, any VPS |
| `Dockerfile.huggingface` | Hugging Face Spaces (port 7860) |
| `docker-compose.yml` | Running locally with Docker |

---

## 🤗 Hugging Face Spaces (Free — 16GB RAM)

1. Go to https://huggingface.co/new-space
2. Name: `intelli-credit`, SDK: **Docker**, Hardware: **CPU Basic (Free)**
3. In the Space repo, create a file called `Dockerfile`
4. Copy the contents of `Dockerfile.huggingface` into it
5. Also copy `requirements.txt`, `backend/`, `frontend/`, `modules/` into the Space repo
6. Go to **Settings → Variables and Secrets** and add:
   - `GOOGLE_API_KEY`
   - `GROQ_API_KEY`
   - `TAVILY_API_KEY`
   - `OPENROUTER_API_KEY`
7. The Space auto-deploys → your URL: `https://huggingface.co/spaces/YOUR_USERNAME/intelli-credit`

---

## 🚂 Railway (Free $5/month credit)

1. Go to https://railway.app → New Project → GitHub repo
2. Copy `Dockerfile` to the **root** of the repo (rename it from `hosting/Dockerfile` to just `Dockerfile`)
3. Railway auto-detects the Dockerfile and builds it
4. Add env variables in Railway Dashboard → Variables tab
5. Railway auto-generates a public URL

---

## ✈️ Fly.io (Free allowance)

```bash
# Install flyctl
winget install Fly.io.flyctl

# From repo root, copy Dockerfile to root first
copy hosting\Dockerfile Dockerfile

# Launch (one-time setup)
fly launch --name intelli-credit --no-deploy

# Set your secrets
fly secrets set GROQ_API_KEY=your_key GOOGLE_API_KEY=your_key TAVILY_API_KEY=your_key

# Deploy
fly deploy
```

---

## 🖥️ Local Docker (Test before deploying)

```bash
# From the hosting/ folder
cd hosting
docker-compose up --build

# App runs at http://localhost:8001
```

---

## ⚡ ngrok (Fastest — for live demo/presentation)

No Docker needed. Just run the app normally and expose it:

```powershell
# Terminal 1 — start backend
cd backend
python -m uvicorn app:app --host 0.0.0.0 --port 8001

# Terminal 2 — create public tunnel
ngrok http 8001
```

You get a link like `https://abc123.ngrok-free.app` — share this with judges!

---

## Required Environment Variables

Copy these from your `.env` file into whichever platform you use:

```
GOOGLE_API_KEY=
GROQ_API_KEY=
TAVILY_API_KEY=
OPENROUTER_API_KEY=
```
