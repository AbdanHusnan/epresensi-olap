FROM apache/superset@sha256:59cd4af66006fe4cc98906eda42a771dbefdacb432f9ab083e02cdc6ff01f29d
USER root
RUN uv pip install --python /app/.venv/bin/python psycopg2-binary==2.9.10
USER superset
