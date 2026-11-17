FROM python:3.12-slim

WORKDIR /app

# Logs sofort sichtbar (Brute-Force live mitlesen).
ENV PYTHONUNBUFFERED=1

# Reine Standardbibliothek, daher kein pip install noetig.
COPY app.py .env ./

EXPOSE 8099

CMD ["python3", "app.py"]
