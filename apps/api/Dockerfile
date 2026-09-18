# syntax=docker/dockerfile:1
# RedCase API — production image (Task 1.7 step 5, step 5 artifact).
#
# BUILD CONTEXT MUST BE THE REPO ROOT (migrations live outside apps/api and
# alembic.ini resolves them via %(here)s/../../infra/supabase/migrations):
#
#     docker build -f apps/api/Dockerfile -t redcase-api .
#
# No secret appears in this file. Runtime configuration arrives exclusively
# as environment variables on the Cloud Run service/job, populated from GCP
# Secret Manager by NAME (secretKeyRef) — never values (HANDOFF.md 3).

FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Image layout mirrors the repo so alembic.ini's relative script_location
# keeps resolving inside the container: /srv/apps/api + /srv/infra/...
WORKDIR /srv/apps/api

# Dependency layer first (locked, reproducible).
COPY apps/api/pyproject.toml apps/api/uv.lock /srv/apps/api/
RUN uv sync --locked --no-dev --no-install-project

COPY apps/api/app /srv/apps/api/app
COPY apps/api/scripts /srv/apps/api/scripts
COPY apps/api/alembic.ini /srv/apps/api/alembic.ini
COPY infra/supabase/migrations /srv/infra/supabase/migrations

EXPOSE 8080

# create_app(settings=None) reads everything from the environment.
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8080"]
