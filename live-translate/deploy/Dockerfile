FROM python:3.11-slim

# 控制 Python 行为
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 国内 ECS 换阿里云 debian 镜像源 + 清华 pip 源（缺一不可：阿里云 PyPI 镜像会漏 uvicorn 等包）
RUN sed -i "s|deb.debian.org|mirrors.aliyun.com|g" /etc/apt/sources.list.d/*.sources 2>/dev/null || true; \
    sed -i "s|deb.debian.org|mirrors.aliyun.com|g" /etc/apt/sources.list 2>/dev/null || true; \
    apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 非 root 用户（uid 1001 避开头 1000 的用户冲突）
RUN groupadd --system --gid 1001 appuser \
    && useradd --system --uid 1001 --gid appuser --create-home --shell /bin/bash appuser

WORKDIR /app

# 先装 Python 依赖（充分利用 Docker 缓存层：requirements.txt 不变就不重装）
COPY requirements.txt .
# 清华 PyPI 镜像：阿里云 PyPI 镜像会漏 uvicorn 等较新包，导致 "No matching distribution found"
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple/ -r requirements.txt

# 复制应用代码（属主改为 appuser）
COPY --chown=appuser:appuser . /app

USER appuser

EXPOSE 8000

# 容器内健康检查（被 docker-compose 的 healthcheck 引用）
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz', timeout=3)" || exit 1

# 2 核 CPU 配 2 worker；--proxy-headers 让 nginx 代理的 X-Forwarded-* 正确传递
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--proxy-headers", \
     "--log-level", "info", \
     "--access-log"]
