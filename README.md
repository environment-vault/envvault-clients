# EnvVault Python Client SDK

Python client EnvVault — a self-hosted environment variable management system.

## Installation
#### Python >= 3.10.11

```bash
# From the project root
pip install -e .

# Or with pip directly
pip install .

# Or with pip github
pip install git+https://github.com/environment-vault/envvault-clients.git

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

```json
{ 
"server_url": "http://localhost:8000", 
"service_token": null, 
"project_id": "YOUR_PROJECT_ID", 
"environment": "dev", 
"version_name": "v1"
"fetch": {"env_config_names": [".env"], "yaml_config_names": ["app"]},
}
}
```

`service_token`: use `ENVVAULT_SERVICE_TOKEN` if left `null`.

### Batch load (load_from_file)

```python
from envvault import load_from_file

result = load_from_file(".envvault.json")
# Also configure Settings, then load_env_config(name=".env") to use cache.
```

## Client API

```python
from envvault import EnvVaultClient

client = EnvVaultClient(server_url="...", service_token="...")

#Secrets
secrets = client.get_secrets(project_id="...", environment="dev")
client.export_dotenv(project_id="...", environment="dev", path=".env")

# Env configs
client.get_env_config(project_id="...", environment="dev", name=".env")
client.export_env_config(project_id="...", environment="dev", name=".env", path=".env")

# YAML configs
client.get_yaml_config_parsed(project_id="...", environment="dev", name="config.yaml")
client.export_yaml_config(project_id="...", environment="dev", name="config.yaml", path="config.yaml")
```

## CLI

```bash
export ENVVAULT_SERVICE_TOKEN="evst_xxx"

envvault fetch --project-id PROJECT_ID --env dev
envvault export --project-id PROJECT_ID --env prod --output .env
envvault env-config get --project-id PROJECT_ID --env dev --name .env
envvault env-config dist --project-id PROJECT_ID --env dev --name .env --output .env
envvault yaml-config get --project-id PROJECT_ID --env dev --name config.yaml
envvault yaml-config dist --project-id PROJECT_ID --env dev --name config.yaml --output config.yaml
envvault run --project-id PROJECT_ID --env dev -- python app.py
```

## Security

- `verbose` prints **key names only**, never values.
- Use `ENVVAULT_SERVICE_TOKEN` instead of putting token in `.envvault.json`.
- Do not log `load_from_file()` / `load_from_config()` return value (contains loaded data).
- Store `.envvault.json` outside version control or use env vars for credentials.

## Service Tokens

1. EnvVault dashboard → Project → **Settings** → **Create Service Token**
2. Set scopes: `secrets:read`, `env_configs:read`, `yaml_configs:read`
3. Copy token (`evst_` prefix)

## API Reference

| Function | Description |
|----------|-------------|
| `load_from_file(path)` | Load from `.envvault.json`; fetches only items in `fetch` |
| `load_from_config(config)` | Same as above, config from dict |
| `load_env(...)` | Fetch secrets and inject |
| `load_env_config(...)` | Fetch one .env config and inject |
| `load_yaml_config(...)` | Fetch YAML; return dict or inject with `inject_to_env=True` |