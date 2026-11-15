# CourseMate

CourseMate is a local study assistant for course PDFs. This setup runs the Vue app and the FastAPI server on one machine.

## Requirements

- Python 3.11
- Node.js 20 or newer

## Backend

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Put your DashScope and DeepSeek API keys in `backend/.env`. The keys stay on the server. Do not commit `.env`.

The server creates `data/` on startup. `GET /api/health` returns `{"status":"ok"}` even when the keys are empty.

## Frontend

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173. The dev server proxies `/api` to http://127.0.0.1:8000.

## Check the model clients

From `backend`, with the virtual environment active:

```bash
python -m app.check_models
```

A successful run prints an embedding dimension of 1024 and one short DeepSeek reply. If configuration is missing, the command names the empty variables and exits with an error. API failures print the provider error and do not print the keys.
