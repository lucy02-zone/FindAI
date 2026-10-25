# FindAI

FindAI is an AI-powered visual lost-and-found matcher. The project is organized as a React + Vite frontend and a FastAPI backend. The planned matching stack includes PyTorch CLIP, FAISS CPU, and MySQL; those integrations are not part of the initial project scaffold.

## Project structure

```text
FindAI/
├── backend/        # FastAPI service
└── frontend/       # React application built with Vite
```

## Prerequisites

- Python 3.10 or newer
- Node.js 18 or newer and npm

## Run the backend

From the repository root:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API responds at <http://127.0.0.1:8000/>. Interactive API documentation is at <http://127.0.0.1:8000/docs>.

## Run the frontend

In a second terminal, from the repository root:

```bash
cd frontend
npm install
npm run dev
```

Vite prints the local development URL when it starts.

## Current scope

The frontend and backend currently provide minimal health-check entry points. Database models, authentication, image embeddings, and similarity search will be added in later steps.
