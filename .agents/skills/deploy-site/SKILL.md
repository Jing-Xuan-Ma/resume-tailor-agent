---
name: deploy-site
description: Build the resume-tailor-agent Docker image, push to Aliyun ACR, and deploy to the ecs-yiling-infra server. Use when the user asks to deploy, publish, ship, release, or roll out the app to the server, or says "部署"、"发布"、"上线"、"deploy". Covers the full build→push→scp→run workflow.
---

# Deploy resume-tailor-agent

All-in-one single-container deployment. Target server: `ecs-yiling-infra`. Image registry: Aliyun ACR.

## Prerequisites

- Docker daemon running locally
- `deploy.sh` at project root
- SSH access to `ecs-yiling-infra`
- Aliyun ACR login (run once): `docker login registry.cn-hangzhou.aliyuncs.com -u <account>`

## Workflow

### 1. Build + push image

From project root:

```bash
rtk docker build --platform linux/amd64 -t registry.cn-hangzhou.aliyuncs.com/ozx/resume-agent:<tag> .
rtk docker push registry.cn-hangzhou.aliyuncs.com/ozx/resume-agent:<tag>
```

Or use the helper: `rtk bash deploy.sh build <tag> --push`

Default tag: `latest`. Use semantic tag like `v1.0` for releases.

### 2. Sync config to server

If `.env.docker.example` or `deploy.sh` changed, re-upload:

```bash
rtk scp .env.docker.example deploy.sh ecs-yiling-infra:/root/resume-agent/
```

### 3. Deploy on server

```bash
rtk ssh ecs-yiling-infra "cd /root/resume-agent && bash deploy.sh run <tag>"
```

This reads `.env.docker` (real secrets, never committed) and starts the container with port mapping + volume.

## Key files

| File | Purpose |
|------|---------|
| `deploy.sh` | build / run / stop commands |
| `.env.docker.example` | config template (safe to commit) |
| `.env.docker` | real config (gitignored, on server only) |
| `docker-compose.yml` | single-service compose alias |

## Ports

Configured in `.env.docker`:

- `HOST_FRONTEND_PORT` (default 3000) → container 3000 (Next.js)
- `HOST_BACKEND_PORT` (default 8000) → container 8000 (FastAPI)

## Verification

After deploy, confirm:

- Health: `curl http://ecs-yiling-infra:<HOST_BACKEND_PORT>/health` → `{"status":"healthy"}`
- Frontend: browser to `http://ecs-yiling-infra:<HOST_FRONTEND_PORT>`
- Swagger: `http://ecs-yiling-infra:<HOST_BACKEND_PORT>/docs`

## Notes

- Platform MUST be `linux/amd64` (server is x86 Linux, dev may be arm64 Mac).
- SQLite + Chroma data persist in volume `resume_agent_data` → `/app/backend/data`.
- `.env.docker` is gitignored — never commit real API keys.
- Rollback: `bash deploy.sh run <previous-tag>`.
