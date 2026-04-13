FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    FORWARDED_ALLOW_IPS=*

WORKDIR /app

RUN useradd --system --create-home --shell /usr/sbin/nologin appuser

COPY requirements.txt /app/requirements.txt

RUN pip install --upgrade pip \
    && pip install -r /app/requirements.txt

COPY app /app/app
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini
COPY scripts /app/scripts

RUN chmod +x /app/scripts/entrypoint.sh \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os; from urllib.request import urlopen; port = os.getenv('PORT', '8080'); urlopen(f'http://127.0.0.1:{port}/health').read()"

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["python", "-m", "app.server"]
