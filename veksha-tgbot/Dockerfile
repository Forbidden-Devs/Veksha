FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system veksha && adduser --system --ingroup veksha veksha

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=veksha:veksha bot.py ./

USER veksha
EXPOSE 8080
CMD ["python", "bot.py"]
