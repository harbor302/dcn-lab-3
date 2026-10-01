FROM python:3.12-slim
WORKDIR /app
RUN useradd --create-home appuser && mkdir /data && chown appuser /data
COPY server.py .
USER appuser
EXPOSE 53533/udp
CMD ["python", "-u", "server.py"]
