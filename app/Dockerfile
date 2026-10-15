FROM node:26-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --include=dev
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AICADEMIYA_DATA_DIR=/data
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ ./backend/
COPY sample_data/ ./sample_data/
COPY --from=frontend /build/dist ./frontend/dist/
RUN useradd --create-home --uid 10001 aicademiya && mkdir -p /data && chown -R aicademiya:aicademiya /data /app
USER aicademiya
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=2)"
CMD ["python", "-m", "uvicorn", "backend.aicademiya.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
