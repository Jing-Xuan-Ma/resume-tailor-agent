# Resume Tailor Agent

> AI-powered resume customization agent that tailors your real experiences to match any job description — without fabrication.

## Features

- **Evidence-First Tailoring**: Every claim in the tailored resume is traceable to your original experience.
- **ATS-Optimized Output**: Single-column, standard fonts, keyword-matched text output that passes automated screening.
- **File Upload**: Support `.docx`, `.pdf`, and `.txt` resume uploads with drag-and-drop.
- **Conversational UI**: Chat with your resume advisor; switch between Chat and Upload tabs.
- **Long-Term Memory**: Experiences are embedded into Chroma vector store for semantic retrieval across sessions.
- **Export**: Copy tailored resume as plain text (Markdown) with one click.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 14 + Tailwind CSS + shadcn/ui |
| Backend | FastAPI + Python 3.11+ |
| Agent Framework | LangGraph |
| LLM | GPT-5.5 via custom OpenAI-compatible provider |
| Vector DB | Chroma (local persistent) |
| Relational DB | PostgreSQL (optional, not required for MVP) |
| Resume Parsing | python-docx + pdfplumber + plain text |

## Project Structure

```
resume-agent/
├── AGENT_CONTEXT.md          # Project context for AI assistants (KEEP UPDATED)
├── backend/                  # FastAPI application
│   ├── app/
│   │   ├── main.py           # FastAPI entry point
│   │   ├── config.py         # Pydantic settings
│   │   ├── memory/           # Long-term memory (Chroma vector store)
│   │   │   ├── long_term.py  # Chroma client + embedding logic
│   │   │   └── experience_embedder.py
│   │   ├── modules/
│   │   │   ├── chat/         # Conversation API
│   │   │   └── resume_tailor/# Core resume tailoring engine
│   │   │       ├── router.py # API routes (tailor, upload, export)
│   │   │       ├── nodes/    # LangGraph nodes
│   │   │       └── prompts/  # System prompts
│   │   └── core/             # Domain models
│   ├── .env                  # API keys (gitignored)
│   └── pyproject.toml        # Python dependencies
└── frontend/                 # Next.js application
    ├── app/                  # App Router pages
    ├── components/           # React components (ChatPanel, ResumeWorkspace)
    └── lib/                  # API clients & utilities
```

## Quick Start (Windows)

> **Note**: Project is developed and tested on Windows. Docker is not required — Chroma runs in local persistent mode.

### 1. Clone & Enter Project

```powershell
cd D:\resume-agent
```

### 2. Setup Backend

```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install -e ".[dev]"
```

Create `.env` inside `backend/`:
```env
OPENAI_API_KEY=sk-your-key-here
OPENAI_BASE_URL=https://router.c.yiling.top/v1
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

Run backend:
```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

API docs: `http://127.0.0.1:8000/docs`

### 3. Setup Frontend

```powershell
cd frontend
npm install
npx next dev
```

Frontend: `http://localhost:3000`

> **Windows Tip**: Frontend uses `http://127.0.0.1:8000` to connect to backend (avoiding IPv6 localhost issues).

## Usage Flow

1. **Upload Resume**: Switch to the **Upload** tab → drag & drop or click to select `.docx`/`.pdf`/`.txt`
2. **Paste Job Description**: Go back to **Chat** tab → paste the JD text
3. **Get Tailored Resume**: The agent retrieves relevant experiences, tailors bullets with action verbs + metrics, and shows the result
4. **Copy as Text**: Click the **Copy as Text** button to copy the Markdown-formatted resume

## Known Limitations

- **Evidence Guard**: Currently returns `{"passed": True}` (mock). Full verification logic not yet implemented.
- **Embedding**: Uses deterministic SHA-256 hash-based embeddings (384-dim) as fallback. Replace with a real embedding model for production.
- **PDF Export**: Not yet implemented. Use **Copy as Text** and paste into Word / Google Docs.
- **PostgreSQL**: Optional. All state is currently in-memory or Chroma.

## License

MIT
