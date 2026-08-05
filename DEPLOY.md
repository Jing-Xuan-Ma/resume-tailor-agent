# 部署

单容器 all-in-one：前端(Next.js :3000) + 后端(FastAPI :8000) + SQLite + Chroma 嵌入式，一个镜像全打包。

## 快速开始

```bash
# 1. 构建推送镜像
./deploy.sh build v1.0 --push

# 2. 在部署服务器上
cp .env.docker.example .env.docker   # 填入真实配置
./deploy.sh run v1.0                  # 读 .env.docker 启动容器
```

## deploy.sh 命令

```bash
./deploy.sh build [tag] [--push]   # 构建 (默认 tag=latest)，--push 推送到阿里云 ACR
./deploy.sh run  [tag]             # 从镜像运行，读 .env.docker 注入环境变量
./deploy.sh stop                   # 停止并删除容器
```

| 参数 | 默认值 |
|------|--------|
| `tag` | `latest` |
| 环境变量文件 | `.env.docker`（可用 `DEPLOY_ENV` 覆盖） |

## 镜像地址

`registry.cn-hangzhou.aliyuncs.com/ozx/resume-agent`

推送前需登录：

```bash
docker login registry.cn-hangzhou.aliyuncs.com -u <阿里云账号>
```

## 环境变量配置

复制 `.env.docker.example` 为 `.env.docker`，填入真实值：

```bash
cp .env.docker.example .env.docker
```

核心配置项：

| 变量 | 说明 |
|------|------|
| `SECRET_KEY` | JWT 签名密钥，生产必须改 |
| `OPENAI_API_KEY` | LLM API Key |
| `OPENAI_BASE_URL` | OpenAI 兼容端点（自建中转/代理） |
| `LLM_PROVIDER` | LLM 提供商，默认 `openai` |
| `CORS_ORIGINS` | 允许的前端来源，逗号分隔 |

## 远程服务器部署

```bash
# 拉取镜像
docker pull registry.cn-hangzhou.aliyuncs.com/ozx/resume-agent:v1.0

# 准备配置
cp .env.docker.example .env.docker
# 编辑 .env.docker 填入 SECRET_KEY、OPENAI_API_KEY 等

# 启动
./deploy.sh run v1.0
```

| 端口 | 服务 |
|------|------|
| `3000` | 前端 Next.js |
| `8000` | 后端 FastAPI + Swagger(`/docs`) |

数据持久化在 volume `resume_agent_data` → 容器内 `/app/backend/data`（SQLite、Chroma、application artifacts）。

## 架构

```
单容器 (supervisord, linux/amd64)
├── uvicorn app.main:app       :8000  FastAPI
├── node server.js (standalone) :3000  Next.js
├── SQLite           /app/backend/data/app.db
├── Chroma 嵌入式    /app/backend/data/chroma/
└── artifacts        /app/backend/data/application_artifacts/
```

weasyprint（PDF 生成）需要 `libpango`、`libcairo`、`libgdk-pixbuf` 等系统库，Dockerfile 已安装。
