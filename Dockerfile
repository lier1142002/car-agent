FROM python:3.10-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ curl \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY . .

# 暴露 Gateway 端口
EXPOSE 8000

# 默认启动 Gateway (生产由 supervisord 管理)
CMD ["uvicorn", "gateway.app:app", "--host", "0.0.0.0", "--port", "8000"]
