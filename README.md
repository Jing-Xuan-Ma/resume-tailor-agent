# Resume Tailor Agent

> AI-powered job application agent that discovers jobs, tailors evidence-backed resumes, creates cover letters, prepares ATS application plans, and supports manual or automatic submission workflows.

## Current Status

The project has moved beyond the original resume-tailoring MVP.

- **Phase 1 complete**: Resume upload, parsing, tailoring, evidence guard, draft editing, Word/PDF/text export.
- **Phase 2 complete**: Job discovery via JobSpy provider with local fallback, job scoring, saved jobs, bookmarks.
- **Phase 3 MVP complete**: Application package generation, ATS detection, manual confirmation, auto-submit API, optional Playwright browser automation boundary.
- **Phase 4 MVP complete**: Cold outreach draft generation, saved outreach records, and user-confirmed sent status.
- **Phase 5 MVP complete**: Growth advisor skill-gap analysis, recommendations, and 4-week roadmap generation.
- **Frontend application workspace active**: Job discovery/import, saved jobs, application package preparation, and submission tracking are available in the web UI.
- **Frontend auth active**: Login/register UI uses the backend auth APIs and stores the current user locally for workspace requests.
- **Durable resume records active**: Resume uploads are stored in SQLite and return `resume_id` values used by tailoring and application-package flows.
- **Resume Workspace module (Phase 6)**: Three-column layout with JD panel, chat, version tabs, react-pdf preview, keyword gap analysis, and template .docx upload. 8 REST endpoints under `/api/v1/resume-workspace`.
- **Job List page (Phase 7)**: Filterable job table with search, source dropdown, threshold slider, score/date sort, Top10 toggle, color-coded match badges, and adaptation summary panel. "Go to Resume Workspace" navigation. 5 new endpoints under `/api/v1/jobs`.
- **Unified LLM client**: Single `get_chat_openai()` factory supporting OpenAI-compatible, Gemini, and Zhipu/GLM providers with `LLM_PROVIDER` env var switching.

## What The Agent Can Do

### Resume Tailoring

- Upload resumes as `.pdf`, `.docx`, `.txt`, or pasted plain text.
- Persist uploaded source resumes and retrieve the latest resume for the logged-in user.
- Parse and store resume experience chunks in local persistent Chroma.
- Parse job descriptions into structured skills, responsibilities, keywords, and job metadata.
- Generate tailored resumes from the user's real experience only.
- Run an evidence guard that checks for unsupported metrics, missing evidence, and weak claim support.
- Keep editable resume drafts and revision history.
- Export tailored resumes as plain text, Word `.docx`, and PDF.

### Job Discovery

- Discover jobs through an optional JobSpy provider.
- Fall back to deterministic local job leads when JobSpy is unavailable or blocked.
- Save discovered/imported jobs in local persistent storage.
- Score jobs against the query and parsed JD fields.
- Bookmark jobs for later application.

### Application Preparation

- Prepare a full application package for a saved job:
  - tailored resume
  - cover letter
  - application plan
  - ATS type detection
  - suggested answers for form questions
  - uploadable resume and cover letter artifacts
- Generate local upload files under `data/application_artifacts/`.
- Split full names into `first_name` and `last_name` where ATS forms require it.
- Match select/dropdown answers to the closest available option.

### Frontend Workspace

- Switch between resume tailoring and job/application management from the main workspace.
- Discover jobs or import a pasted JD with an optional ATS URL.
- Review saved jobs, bookmark jobs, prepare application packages, and track application runs.
- Confirm manual submissions or trigger the guarded auto-submit endpoint from the UI.
- Draft cold outreach messages and create growth plans from the job workspace.

### ATS Connectors

The agent detects and prepares plans for these ATS platforms:

- Greenhouse
- Lever
- Ashby
- Workday
- iCIMS
- Generic fallback

Each connector can provide platform-specific field selectors, field aliases, and submit button selectors for browser automation.

### Manual And Automatic Submission

- Manual review mode:
  - Agent prepares the application.
  - User reviews and submits in the browser.
  - User confirms submission through the API.
  - Status becomes `submitted_by_user`.
- Auto-submit mode:
  - Requires explicit `submit_mode="auto_submit"`.
  - Requires explicit `auto_submit=true` and `confirm_auto_submit=true`.
  - Controlled by `ENABLE_AUTO_SUBMIT`.
  - Records audit logs and submission results.
  - Optional browser automation is controlled by `ENABLE_BROWSER_AUTOMATION`.

By default, browser automation is disabled. With `ENABLE_BROWSER_AUTOMATION=false`, auto-submit uses the connector submission boundary and records the result without launching a browser. With `ENABLE_BROWSER_AUTOMATION=true` and Playwright installed, the agent attempts to open the ATS page, fill supported fields, upload files, and click submit.

### Cold Outreach

- Generate draft-only outreach messages for saved jobs.
- Support email, LinkedIn, and referral-oriented channels at the API level.
- Store outreach drafts in SQLite and allow users to mark messages as `sent_by_user`.
- Preserve the safety boundary: the app does not send emails or LinkedIn messages automatically.

### Growth Advisor

- Analyze the latest uploaded resume against a saved job or target role.
- Identify missing or partially supported skills.
- Generate prioritized recommendations and a 4-week execution roadmap.
- Persist growth plans for later review.

### User And Persistence

- Register, login, and `/me` auth APIs with JWT tokens.
- Frontend login/register gate with persisted token validation through `/api/v1/auth/me`.
- Local SQLite persistence for users, drafts, jobs, applications, cover letters, profiles, conversations, events, and audit logs.
- Local SQLite persistence for uploaded source resumes and their durable `resume_id` values.
- User profile and feedback learning endpoints.
- Conversation history storage and semantic memory fallback.
- Daily rate limits with Redis when available and in-memory fallback otherwise.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 14 + React 18 + Tailwind CSS |
| Backend | FastAPI + Python 3.11+ |
| Agent Flow | LangGraph |
| LLM | GPT-5.5 / Gemini / GLM via unified `LLM_PROVIDER` client |
| Vector DB | Chroma local persistent store |
| App State | SQLite local persistent store |
| Optional Cache/Rate Limit | Redis |
| Job Discovery | JobSpy provider + local fallback |
| Resume Parsing | python-docx + pdfplumber + plain text |
| Browser | ghost-driver MCP + skills（对话里填表，停在 Submit 前） |

## Project Structure

```text
resume-tailor-agent/
├── AGENTS.md                 # Agent entry (Cursor / Claude Code)
├── CLAUDE.md
├── RESUME_CONSTITUTION.md
├── backend/                  # FastAPI: scrape, profile, tailor APIs
├── frontend/                 # Next.js workspace
├── mcp/happy-ghost-driver/   # Browser MCP
├── .agents/skills/           # resume-tailor, jobright-apply, screen-locate, …
├── config/                   # intern-list scrape schedule
├── scripts/                  # dev-up / scheduled scrape
└── archive/                  # old iteration dumps (not on the hot path)
```

## Quick Start Windows

> Docker is optional. The default local workflow uses local Chroma and local SQLite.

### Backend

```powershell
cd D:\resume-agent\backend
python -m venv venv
.\venv\Scripts\activate
pip install -e ".[dev]"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Create `backend/.env`:

```env
# Provider: openai | gemini | zhipu
LLM_PROVIDER=openai

# OpenAI-compatible (used when LLM_PROVIDER=openai)
OPENAI_API_KEY=sk-your-key-here
OPENAI_BASE_URL=https://router.c.yiling.top/v1

# Gemini (used when LLM_PROVIDER=gemini)
# GEMINI_API_KEY=your-gemini-key

# Zhipu / GLM (used when LLM_PROVIDER=zhipu)
# BIGMODEL_API_KEY=your-zhipu-key

CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

API docs: `http://127.0.0.1:8000/docs`

### Frontend

```powershell
cd D:\resume-agent\frontend
npm install
npm run dev
```

Frontend: `http://localhost:3000`

## Optional JobSpy

JobSpy is optional. If it is not installed or a board blocks the request, job discovery falls back to local deterministic leads.

```powershell
cd D:\resume-agent\backend
.\venv\Scripts\activate
pip install python-jobspy
```

## Optional Browser Automation

Browser automation is off by default.

To enable it:

```env
ENABLE_AUTO_SUBMIT=true
ENABLE_BROWSER_AUTOMATION=true
BROWSER_HEADLESS=true
BROWSER_TIMEOUT_MS=30000
```

Install Playwright if needed:

```powershell
cd D:\resume-agent\backend
.\venv\Scripts\activate
pip install playwright
python -m playwright install chromium
```

## Core API Examples

### Upload Resume

`POST /api/v1/resume-tailor/upload-resume`

```json
{
  "user_id": "00000000-0000-0000-0000-000000000001",
  "resume_text": "Jane Doe\nData Analyst..."
}
```

### Tailor Resume For JD

`POST /api/v1/resume-tailor/tailor`

```json
{
  "user_id": "00000000-0000-0000-0000-000000000001",
  "resume_id": "00000000-0000-0000-0000-000000000002",
  "jd_text": "Software Engineer role..."
}
```

### Discover Jobs

`POST /api/v1/jobs/discover`

```json
{
  "user_id": "00000000-0000-0000-0000-000000000001",
  "query": "data analyst",
  "location": "Remote",
  "limit": 5,
  "provider": "jobspy"
}
```

### Prepare Full Application Package

`POST /api/v1/jobs/{job_id}/prepare-application`

```json
{
  "user_id": "00000000-0000-0000-0000-000000000001",
  "resume_id": "00000000-0000-0000-0000-000000000002",
  "include_cover_letter": true,
  "include_application_plan": true,
  "submit_mode": "manual_review"
}
```

### Auto Submit An Application Run

`POST /api/v1/applications/{application_run_id}/auto-submit`

```json
{
  "user_id": "00000000-0000-0000-0000-000000000001",
  "confirm_auto_submit": true
}
```

## Testing

```powershell
cd D:\resume-agent\backend
.\venv\Scripts\activate
python -m pytest
```

Current verified status: `16 passed`.

Frontend build:

```powershell
cd D:\resume-agent\frontend
npm run build
```

## Current Limitations

- Browser automation requires Playwright and real ATS page testing.
- File upload support exists, but each ATS may require additional selector tuning.
- Workday flows are multi-step and often need deeper page-specific automation.
- LinkedIn Easy Apply is intentionally not the first target due to account risk and rate limiting.
- SQLite is used for local persistence; production should migrate to PostgreSQL with migrations.
- Browser and ATS selectors remain the highest-risk area until validated against real application pages.
- Cold outreach is draft-only; production email sending would require OAuth, unsubscribe/compliance handling, and explicit user confirmation.

## License

MIT
