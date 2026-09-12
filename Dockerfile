FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    python -c "import nltk; nltk.download('punkt', quiet=True); nltk.download('vader_lexicon', quiet=True)" 2>/dev/null; true

COPY . .

EXPOSE 8000

CMD ["python", "-m", "app.main"]