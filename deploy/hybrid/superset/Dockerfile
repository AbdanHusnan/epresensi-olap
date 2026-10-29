FROM apache/superset:6.1.0
USER root
RUN . /app/.venv/bin/activate && uv pip install psycopg2-binary==2.9.11 redis==5.2.1
COPY --chown=superset:superset superset_config.py bootstrap.py /app/hybrid/
USER superset
ENV SUPERSET_CONFIG_PATH=/app/hybrid/superset_config.py
