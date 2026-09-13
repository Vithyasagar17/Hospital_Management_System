FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system medora \
    && adduser --system --ingroup medora --home /home/medora medora

COPY requirements.txt requirements-prod.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements-prod.txt

COPY . .

RUN chmod +x /app/docker/entrypoint.sh \
    && chown -R medora:medora /app /home/medora

USER medora

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "--config", "gunicorn.conf.py", "run:app"]
