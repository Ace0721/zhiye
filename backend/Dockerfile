FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ZHIYE_HOST=0.0.0.0 ZHIYE_DATA_DIR=/data
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
VOLUME ["/data"]
CMD ["python", "-m", "app.main"]
