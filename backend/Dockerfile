# Telegram 云控 —— API / Worker 共用镜像
#
# 构建上下文：backend/（见 docker-compose.yml 的 build.context）
# api 与 worker 用同一镜像，靠 compose 的 command 区分：
#   api    -> uvicorn app.api.main:app
#   worker -> python -m app.worker.main
#
# 密钥不进镜像：.env 被 .dockerignore 排除，配置全部由 compose 的
# env_file(.env) / environment 在运行时注入（pydantic-settings 优先读环境变量）。

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app \
    TZ=Asia/Shanghai

WORKDIR /app

# curl：compose healthcheck 打 /health、/metrics 用
# build-essential：少数包没有 cp312 wheel 时兜底编译（装完即卸，见下）
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl build-essential \
 && rm -rf /var/lib/apt/lists/*

# 先拷依赖清单再装包：业务代码改动不会让 pip 层缓存失效
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
 && apt-get purge -y --auto-remove build-essential \
 && rm -rf /var/lib/apt/lists/* /root/.cache

# 非 root 运行
RUN groupadd --gid 10001 appuser \
 && useradd --uid 10001 --gid 10001 --create-home --shell /bin/bash appuser

# 业务代码（api/worker 入口都在 app 包内）
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY entrypoint.sh ./
RUN chmod +x /app/entrypoint.sh \
 && chown -R appuser:appuser /app

USER appuser

# 8000 = API（/health /ready /metrics）；9101 = Worker 指标
EXPOSE 8000 9101

# 健康检查统一写在 docker-compose.yml（api 用 /health，worker 用 :9101/metrics）
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
