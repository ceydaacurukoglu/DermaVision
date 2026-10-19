FROM python:3.12-slim

# print() çıktıları ([MAIL], [Google] satırları) anında loglara düşsün
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Root olmayan kullanıcıyla çalış; /data (fotoğraflar) bu kullanıcıya ait olsun
RUN useradd -m uygulama && mkdir -p /data && chown uygulama /data
USER uygulama

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
