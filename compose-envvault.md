# Docker Compose + EnvVault (single `docker compose up`)

Use the merge file `docker-compose.envvault.yml` so a **one-shot** service `envvault-sync` runs first, writes `.env` into the project root (bind mount), then the rest of the stack starts.

## Quick start

1. **Create an empty `.env` in the repo root** (Compose requires the file if `env_file: .env` is set):

   ```bash
   touch .env
   ```

2. **Export EnvVault credentials** (host shell or add only these keys to `.env` — do not commit real tokens):

   ```bash
   export ENVVAULT_PROJECT_ID="your_project_id"
   export ENVVAULT_SERVICE_TOKEN="evst_..."
   export ENVVAULT_SERVER_URL="http://host.docker.internal:8000"   # API on host
   ```

   Self-signed HTTPS:

   ```bash
   export ENVVAULT_NO_VERIFY_SSL=1
   ```

3. **Run Compose with both files**:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.envvault.yml up -d
   ```

   To avoid repeating `-f`, set:

   ```bash
   export COMPOSE_FILE=docker-compose.yml:docker-compose.envvault.yml
   docker compose up -d
   ```

## What gets pulled

| Variable | Default | Meaning |
|----------|---------|--------|
| `ENVVAULT_EXPORT_MODE` | `secrets` | `secrets` → `envvault export`; `env-config` → `envvault env-config dist` |
| `ENVVAULT_ENV_CONFIG_NAME` | `.env` | Env config name when mode is `env-config` |
| `ENVVAULT_ENV` | `dev` | Environment slug |
| `ENVVAULT_VERSION_NAME` | _(empty)_ | Optional `--version` (e.g. `v1`) |
| `ENVVAULT_OUTPUT_FILE` | `.env` | File written under the project root |

Example: only the stored `.env` config (not key-value secrets):

```bash
export ENVVAULT_EXPORT_MODE=env-config
export ENVVAULT_ENV_CONFIG_NAME=.env
docker compose -f docker-compose.yml -f docker-compose.envvault.yml up -d
```

## `ENVVAULT_SERVER_URL` from containers

- API on the **host** (typical dev): `http://host.docker.internal:8000` (the merge file adds `extra_hosts: host.docker.internal:host-gateway`).
- API already in Docker on the **same compose file**: use `http://backend:8000` only if `envvault-sync` does **not** create a circular dependency (e.g. backend is not the EnvVault API you are calling). For this repo’s stack, the EnvVault API is usually run separately on the host or another deployment.

## Caveat: `${VAR}` in `docker-compose.yml`

Compose substitutes `${PASSWORD_REDIS}`, `${MONGODB_PASSWORD}`, etc. **when it loads the project**, before any container runs. The sync job updates `.env` **after** that pass.

- Variables consumed only via **`env_file`** inside containers are filled when each service **starts**, so they match the synced file as long as that service starts **after** `envvault-sync` (the merge file adds `depends_on` for that).
- Variables used **in the YAML itself** (e.g. `command: ... ${PASSWORD_REDIS:-redis}`) are fixed for that `docker compose up` invocation. If they must match Vault, either:
  - run **`docker compose up` again** after the first sync so Compose re-reads `.env`, or
  - export those variables in your shell before `docker compose up`.

## Optional: copy as override

If you prefer the default Compose behaviour of loading `docker-compose.override.yml` automatically:

```bash
cp docker-compose.envvault.yml docker-compose.override.yml
```

Consider adding `docker-compose.override.yml` to `.gitignore` if it contains local-only settings.
