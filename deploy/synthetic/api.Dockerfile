FROM python:3.12-slim
ARG SOURCE_COMMIT=unknown
LABEL org.opencontainers.image.revision=$SOURCE_COMMIT \
      org.opencontainers.image.source="https://github.com/sambohon325/dealerOS"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
COPY hub/requirements.txt /app/hub/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt -r hub/requirements.txt
COPY backend/api /app/backend/api
COPY backend/core /app/backend/core
COPY backend/chrono /app/backend/chrono
COPY backend/intelligence /app/backend/intelligence
COPY backend/ore /app/backend/ore
COPY backend/db /app/backend/db
COPY backend/imports /app/backend/imports
COPY backend/entity_types.py /app/backend/entity_types.py
COPY hub/hub_core /app/hub/hub_core
COPY scripts/synthetic_dealership.py scripts/synthetic_dealer.py scripts/synthetic_hub.py scripts/staging_container.py /app/scripts/
RUN useradd --uid 10001 --create-home fixture && mkdir /data && chown fixture:fixture /data
USER 10001:10001
ENTRYPOINT ["python", "/app/scripts/staging_container.py"]
