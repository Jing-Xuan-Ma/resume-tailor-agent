#!/usr/bin/env bash
set -euo pipefail

REGISTRY="registry.cn-hangzhou.aliyuncs.com/ozx/resume-agent"
ENV_FILE="${DEPLOY_ENV:-.env.docker}"
TAG="${2:-latest}"
IMAGE="${REGISTRY}:${TAG}"

usage() {
  cat <<EOF
用法:
  ./deploy.sh build [tag] [--push]   构建 (默认 tag=latest)
  ./deploy.sh run  [tag]             从镜像运行容器，读取 ${ENV_FILE}
  ./deploy.sh stop                   停止并删除容器

端口在 ${ENV_FILE} 中配置:
  HOST_FRONTEND_PORT (默认 3000)
  HOST_BACKEND_PORT  (默认 8000)

示例:
  ./deploy.sh build v1.0 --push
  ./deploy.sh run v1.0
  ./deploy.sh stop
EOF
  exit 1
}

load_ports() {
  FRONTEND_PORT="3000"
  BACKEND_PORT="8000"
  if [ -f "$ENV_FILE" ]; then
    # shellcheck disable=SC1090
    while IFS='=' read -r key val; do
      case "$key" in
        HOST_FRONTEND_PORT) FRONTEND_PORT="${val:-3000}" ;;
        HOST_BACKEND_PORT)  BACKEND_PORT="${val:-8000}" ;;
      esac
    done < "$ENV_FILE"
  fi
}

cmd="${1:-}"

case "$cmd" in
  build)
    echo "▶ Building ${IMAGE} (platform: linux/amd64)"
    docker build --platform linux/amd64 -t "${IMAGE}" .
    echo "✓ Built ${IMAGE}"
    if [ "${3:-}" = "--push" ]; then
      echo "▶ Pushing ${IMAGE}"
      docker push "${IMAGE}"
      echo "✓ Pushed ${IMAGE}"
    fi
    ;;

  run)
    if [ ! -f "$ENV_FILE" ]; then
      echo "✗ 找不到 ${ENV_FILE}，请复制 .env.docker.example 并填写"
      exit 1
    fi
    load_ports
    echo "▶ Running ${IMAGE} (frontend:${FRONTEND_PORT} backend:${BACKEND_PORT})"
    docker rm -f resume_agent 2>/dev/null || true
    docker run -d \
      --name resume_agent \
      --restart unless-stopped \
      --platform linux/amd64 \
      -p "${FRONTEND_PORT}:3000" \
      -p "${BACKEND_PORT}:8000" \
      -v resume_agent_data:/app/backend/data \
      --env-file "$ENV_FILE" \
      "$IMAGE"
    echo "✓ 容器已启动 resume_agent"
    echo "  前端:  http://localhost:${FRONTEND_PORT}"
    echo "  API:   http://localhost:${BACKEND_PORT}/docs"
    ;;

  stop)
    docker rm -f resume_agent 2>/dev/null && echo "✓ 已停止" || echo "容器不存在"
    ;;

  *)
    usage
    ;;
esac
