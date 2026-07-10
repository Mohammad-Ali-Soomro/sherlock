FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# HF Spaces requires port 7860, but keep flexible via PORT env var
ENV PORT=7860
EXPOSE 7860

# Create a non-root user (required by HF Spaces)
RUN useradd -m -u 1000 appuser
USER appuser

CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
