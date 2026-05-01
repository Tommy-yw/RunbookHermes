FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app
EXPOSE 8080 8081 8082
CMD python -m uvicorn main:app --host 0.0.0.0 --port ${SERVICE_PORT:-8080}
