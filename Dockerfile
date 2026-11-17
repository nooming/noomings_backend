# Railway / 其他 Docker 托管：与 Zeabur 一致使用 PORT、/data 持久化
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    FLASK_DEBUG=false \
    DATABASE_PATH=/data/parking_pso.db

COPY requirements.txt .
RUN pip install --no-cache-dir \
    --default-timeout=300 \
    -i https://mirrors.cloud.tencent.com/pypi/simple \
    --trusted-host mirrors.cloud.tencent.com \
    -r requirements.txt

COPY . .

RUN mkdir -p /data

EXPOSE 8080

CMD ["python", "app.py"]
