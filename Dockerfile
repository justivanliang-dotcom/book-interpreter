FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY book_interpreter ./book_interpreter
COPY webapp ./webapp

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "webapp.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
