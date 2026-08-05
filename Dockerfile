FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml ./backend/
COPY backend/app ./backend/app
RUN printf '# resume-agent-backend\n' > ./backend/README.md

WORKDIR /app/backend
RUN pip install --no-cache-dir -e .

ENV APP_HOST=0.0.0.0
ENV APP_PORT=8000
ENV STORAGE_BACKEND=postgres
ENV DATABASE_URL=postgresql+psycopg://resume_agent:resume_agent_dev@postgres:5432/resume_agent

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
