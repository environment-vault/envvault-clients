# EnvVault Python Client SDK

Python client EnvVault — a self-hosted environment variable management system.

## Installation
#### Python >= 3.10.11
## Features

- **One-time setup**: `Settings.from_file(".envvault.json")` or `Settings.configure(...)` at process start.
- **Cached reads**: responses are reused for `Settings.cache_ttl` seconds (default `5`) to limit API calls.
- **Safe logging**: `verbose=True` prints **key names only**, never secret values.

## Install

From the repo root:

```bash
# From the project root
pip install -e .

# Or with pip directly
pip install .

# Or with pip github
pip install git+https://github.com/environment-vault/envvault-clients.git@0.2.0

```

## Quick Start

### 1. An initialization place (main, settings, app bootstrap)

```python
from envvault import Settings

Settings.from_file(".envvault.json")
# or
Settings.configure( 
server_url="http://localhost:8000", 
project_id="abc123", 
service_token="evst_xxx", 
environment="dev",
)
```

### 2. Anywhere is just a call away

```python
from envvault import load_env_config, load_yaml_config

data = load_env_config(name=".env")
config = load_yaml_config(name="config.yaml")
```

- Cache 5s: if last request < 5s → return cache, do not send new request.
- Change TTL: `Settings.cache_ttl = 10`

### Config file `.envvault.json`

Copy the example and fill in your project:

```bash
cp clients/envvault-python/.envvault.json.example .envvault.json
```

| Field | Meaning |
|--------|--------|
| `server_url` | EnvVault API base, e.g. `http://localhost:8000` |
| `service_token` | Service token (`evst_…`); use `null` and set `ENVVAULT_SERVICE_TOKEN` instead |
| `project_id` | Project UUID |
| `environment` | Slug, e.g. `dev`, `staging`, `prod` |
| `version_name` | Optional config version, e.g. `v1` |
| `fetch` | What to pull in one shot (see below) |
| `yaml_inject_to_env` | If `true`, flatten YAML dicts into `os.environ` (batch loaders) |
| `yaml_env_prefix` | Prefix for keys when injecting from YAML |

### `fetch` object

| Key | Effect |
|-----|--------|
| `secrets` | If `true`, load key-value secrets (one request). |
| `env_config_names` | List of stored `.env` config names (one request each). |
| `yaml_config_names` | List of YAML config names (one request each). |

Example:

```json
{
  "server_url": "http://localhost:8000",
  "service_token": null,
  "project_id": "YOUR_PROJECT_ID",
  "environment": "dev",
  "version_name": "v1",
  "fetch": {
    "secrets": true,
    "env_config_names": [".env"],
    "yaml_config_names": ["config.yaml"]
  },
  "yaml_inject_to_env": false,
  "yaml_env_prefix": ""
}
```

## Usage patterns

### 1. Configure once, call anywhere (recommended)

```python
from envvault import Settings, load_env_config, load_yaml_config

Settings.from_file(".envvault.json")

env_vars = load_env_config(name=".env", override=False, verbose=True)
app_yaml = load_yaml_config(name="config.yaml")
```

Tune cache: `Settings.cache_ttl = 10`.

### 2. Batch load into the environment

`load_from_file` reads the JSON **once**, applies settings, then fetches only what `fetch` lists and injects into `os.environ` (and returns metadata).

```python
from envvault import load_from_file

result = load_from_file(".envvault.json", verbose=True)
# result["loaded_keys"] — names only; result["yaml"] — parsed YAML per name
# Do not log `result` in production if it might contain sensitive structure.
```

Same behavior from an in-memory dict:

```python
from envvault import load_from_config

load_from_config(config_dict, verbose=True)
```

Optional SSL override (overrides `verify_ssl` inside the config for that call):

```python
load_from_file(".envvault.json", verify_ssl=False)
```

### 3. One-off client (no `Settings`)

```python
from envvault import load_env, EnvVaultClient

load_env(
    server_url="http://localhost:8000",
    service_token="evst_xxx",
    project_id="...",
    environment="dev",
    verbose=True,
)

# Or imperative API:
client = EnvVaultClient(server_url="http://localhost:8000", service_token="evst_xxx")
secrets = client.get_secrets("PROJECT_ID", "dev")
client.export_dotenv("PROJECT_ID", "dev", path=".env")
```

JWT login (interactive / user token):

```python
client = EnvVaultClient.login(
    "http://localhost:8000",
    email="you@example.com",
    password="...",
)
```

## CLI

Requires `ENVVAULT_SERVICE_TOKEN` (or `--token`). Default server: `ENVVAULT_SERVER_URL` or `http://localhost:8000`.

TLS for HTTPS:

- `--no-verify-ssl` / `-k` — disable certificate verification (insecure; dev/self-signed only).
- `--ca-bundle /path/to/ca.pem` — custom CA bundle (or set `ENVVAULT_CA_BUNDLE`).
- `ENVVAULT_VERIFY_SSL=0|false|no|off` — disable verification without a flag (when no `--ca-bundle`).

```bash
export ENVVAULT_SERVICE_TOKEN="evst_xxx"

envvault fetch --project-id PROJECT_ID --env dev
envvault export --project-id PROJECT_ID --env prod --output .env

envvault env-config get --project-id PROJECT_ID --env dev --name .env
envvault env-config dist --project-id PROJECT_ID --env dev --name .env --output .env

envvault yaml-config get --project-id PROJECT_ID --env dev --name config.yaml
envvault yaml-config dist --project-id PROJECT_ID --env dev --name config.yaml --output config.yaml

envvault run --project-id PROJECT_ID --env dev -- python app.py
# Inject a stored .env config instead of key-value secrets:
envvault run --project-id PROJECT_ID --env dev --name .env -- your-command
```

Print dotenv to stdout (no file on disk):

```bash
envvault export --project-id PROJECT_ID --env dev --stdout
envvault env-config dist --project-id PROJECT_ID --env dev --name .env --stdout
```

### Docker Compose without a committed `.env` file

Compose only reads **`env_file`** paths from disk; variables you `export` in the shell are **not** applied to services that only list `env_file: .env`. You can still avoid a long-lived `.env` file in three ways:

1. **`envvault run` (recommended)** — secrets are injected into the environment of the `docker compose` process. In your Compose file, pass each variable into the container using the [pass-through form](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/#substitute-from-the-shell) (value taken from the shell that runs Compose), for example:

   ```yaml
   services:
     backend:
       environment:
         - DATABASE_URL
         - MONGODB_PASSWORD
   ```

   Then:

   ```bash
   envvault run --project-id PROJECT_ID --env dev -- docker compose up -d
   ```

2. **`source` from stdout** (bash/zsh) — loads `KEY=value` lines into your current shell; Compose can substitute `${VAR}` in the YAML from that shell:

   ```bash
   set -a
   source <(envvault export --project-id PROJECT_ID --env dev --stdout)
   set +a
   docker compose up -d
   ```

   Again, services that use only `env_file: .env` will not see these unless you also reference `${VAR}` in `environment:` or switch to the pass-through list above.

3. **Short-lived file** — `envvault export -o .env` then `docker compose up`, then delete `.env` if you accept a temporary file.

## Security

- Prefer `ENVVAULT_SERVICE_TOKEN` over committing tokens in JSON.
- Do not commit `.envvault.json` if it contains secrets; add it to `.gitignore`.
- Do not log return values from loaders when they may contain secrets or full YAML trees.

## Service token

In the EnvVault UI: Project → **Settings** → create a service token with at least `secrets:read`, `env_configs:read`, and `yaml_configs:read` as needed.

## API quick reference

| Symbol | Role |
|--------|------|
| `EnvVaultClient` | Low-level HTTP API (secrets, env configs, YAML, export helpers). |
| `EnvVaultError`, `AuthenticationError`, `NotFoundError` | Errors from the client. |
| `Settings` | Singleton: `configure`, `from_file`, `from_config`; holds cache and defaults. |
| `load_from_file` / `load_from_config` | Batch fetch per `fetch` + inject. |
| `load_env` | Secrets → `os.environ`. |
| `load_env_config` | Named `.env` config → dict / `os.environ`. |
| `load_yaml_config` | YAML → Python object; optional flatten-to-env. |

Package version is defined in `pyproject.toml` and mirrored in `envvault.__version__`.
