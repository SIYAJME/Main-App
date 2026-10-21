FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ARG_DB_PATH=/app/data/redteam.sqlite3
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
RUN useradd -r -u 10001 appuser && mkdir -p /app/data && chown -R appuser:appuser /app/data
USER appuser
EXPOSE 8765
CMD ["python","-m","uvicorn","app.product:app","--host","0.0.0.0","--port","8765","--workers","1"]
