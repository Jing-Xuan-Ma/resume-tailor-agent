# Resume Tailor Agent

> AI-powered resume customization agent that tailors your real experiences to match any job description — without fabrication.

## Features

- **Evidence-First Tailoring**: Every claim in the tailored resume is traceable to your original experience.
- **ATS-Optimized Output**: Single-column, standard fonts, keyword-matched PDFs that pass automated screening.
- **Conversational UI**: Chat with your resume advisor like talking to a human career coach.
- **Long-Term Memory**: The agent remembers your experiences, preferences, and conversation history across sessions.
- **Plugin-Ready Architecture**: Auto-apply, cold outreach, and growth advisor modules can be added later without touching core code.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 14 + Tailwind CSS + shadcn/ui |
| Backend | FastAPI + Python 3.11+ |
| Agent Framework | LangGraph |
| LLM | Claude 3.5 Sonnet (tailoring) + GPT-4o (parsing) |
| Vector DB | Chroma (local) / Pineapple (prod) |
| Relational DB | PostgreSQL |
| PDF Generation | Playwright / WeasyPrint |

## Project Structure

```
resume-agent/
├── AGENT_CONTEXT.md          # Project context for AI assistants (KEEP UPDATED)
├── docker-compose.yml        # Local infra (Postgres + Chroma)
├── backend/                  # FastAPI application
│   ├── app/
│   │   ├── main.py           # FastAPI entry point
│   │   ├── config.py         # Pydantic settings
│   │   ├── core/             # Domain models & events
│   │   ├── modules/          # Business modules
│   │   │   ├── chat/         # Conversation API
│   │   │   ├── resume_tailor/# Core resume tailoring engine
│   │   │   └── memory/       # Long-term memory system
│   │   └── ...
│   └── pyproject.toml        # Python dependencies
└── frontend/                 # Next.js application
    ├── app/                  # App Router pages
    ├── components/           # React components
    └── lib/                  # API clients & utilities
```

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose

### 1. Clone & Enter Project

```bash
cd C:\Users\HP\resume-agent
```

### 2. Start Infrastructure

```bash
docker-compose up -d
```

This starts:
- PostgreSQL on port `5432`
- Chroma (vector DB) on port `8001`

### 3. Setup Backend

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
# source venv/bin/activate

pip install -e ".[dev]"
```

Copy environment variables:
```bash
cp ..\.env.example .env
# Edit .env and add your API keys
```

Run backend:
```bash
uvicorn app.main:app --reload --port 8000
```

API docs will be available at `http://localhost:8000/docs`.

### 4. Setup Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend will be at `http://localhost:3000`.

## Development Guide

### Adding a New Module

1. Create directory under `backend/app/modules/your_module/`
2. Define router in `router.py`, schemas in `schemas.py`, service in `service.py`
3. Register router in `backend/app/main.py`
4. If the module emits events consumed by others, define events in `app/core/events.py` and publish via `EventBus`

### Updating Agent Context

Whenever you make significant architecture or progress changes, **update `AGENT_CONTEXT.md`** so future AI assistants (or yourself in a new chat) can pick up where you left off.

## License

MIT
