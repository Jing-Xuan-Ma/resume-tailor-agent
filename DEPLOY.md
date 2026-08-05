# 部署

单容器 all-in-one：前端(Next.js :3000) + 后端(FastAPI :8000) + SQLite + Chroma 嵌入式，一个镜像全打包。

## 构建

```bash
docker build -t resume-agent .
```

远程服务器需在构建时指定前端 API 地址（`NEXT_PUBLIC_API_URL` 是构建时注入）：

```bash
docker build \
  --build-arg NEXT_PUBLIC_API_URL=https://your-server:8000 \
  -t resume-agent .
```

## 运行

```bash
docker run -d \
  --name resume_agent \
  --restart unless-stopped \
  -p 3000:3000 \
  -p 8000:8000 \
  -v resume_agent_data:/app/backend/data \
  -e SECRET_KEY=$(openssl rand -hex 32) \
  -e OPENAI_API_KEY=sk-xxx \
  -e OPENAI_BASE_URL=https://your-openai-compatible-endpoint/v1 \
  -e LLM_PROVIDER=openai \
  -e CORS_ORIGINS=https://your-frontend-domain \
  resume-agent
```

| 端口 | 服务 |
|------|------|
| `3000` | 前端 Next.js |
| `8000` | 后端 FastAPI + Swagger(`/docs`) |

数据全部落在 volume `resume_agent_data` → 容器内 `/app/backend/data`（SQLite、Chroma、application artifacts）。

## 必填环境变量

| 变量 | 说明 |
|------|------|
| `SECRET_KEY` | JWT 签名密钥，生产必须改 |
| `OPENAI_API_KEY` | LLM API Key |
| `OPENAI_BASE_URL` | OpenAI 兼容端点（自建中转/代理） |
| `CORS_ORIGINS` | 允许的前端来源，逗号分隔 |

## 可选：docker-compose

`docker-compose.yml` 仍在，只是把上面的 `docker run` 存成文件，方便复用：

```bash
OPENAI_API_KEY=sk-xxx docker compose up -d --build
```

不需要可直接 `docker run`，compose 对单容器没有额外作用。

## 切换到 PostgreSQL

默认 SQLite 兜底，零配置开箱即用。切 PG 只改环境变量，代码已兼容：

```bash
docker run -d \
  -e DATABASE_URL="postgresql+asyncpg://user:pass@db-host:5432/resume_agent" \
  ...
  resume-agent
```

## 架构

```
单容器 (supervisord)
├── uvicorn app.main:app       :8000  FastAPI
├── node server.js (standalone) :3000  Next.js
├── SQLite           /app/backend/data/app.db
├── Chroma 嵌入式    /app/backend/data/chroma/
└── artifacts        /app/backend/data/application_artifacts/
```

weasyprint（PDF 生成）需要 `libpango`、`libcairo`、`libgdk-pixbuf` 等系统库，Dockerfile 已安装。
