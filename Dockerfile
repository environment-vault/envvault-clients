# One-shot image: run EnvVault CLI to write .env into a bind-mounted project directory.
# Used by docker-compose.envvault.yml — not a long-running service.
FROM python:3.12-slim

COPY ./envvault-python /tmp/envvault-python
RUN pip install --no-cache-dir /tmp/envvault-python && rm -rf /tmp/envvault-python

COPY ./scripts/envvault-compose-sync.sh /usr/local/bin/envvault-compose-sync.sh
RUN chmod +x /usr/local/bin/envvault-compose-sync.sh

WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/envvault-compose-sync.sh"]
