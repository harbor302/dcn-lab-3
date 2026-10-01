FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home appuser
COPY server.py .
USER appuser
EXPOSE 9090
CMD ["python", "-u", "server.py"]
