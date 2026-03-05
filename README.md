# EnvVault Python Client SDK

Python client EnvVault — a self-hosted environment variable management system.

## Installation

```bash
# From the project root
pip install -e .

# Or with pip directly
pip install .

# Or with pip github
pip install git+https://github.com/environment-vault/envvault-clients.git

```

## Quick Start

### 1. Auto-load secrets into `os.environ`

The simplest way to use EnvVault is to inject secrets at app startup:

```python
from envvault import load_env

# Load secrets into os.environ
load_env(
    server_url="https://example.com",
    service_token="xxxxxxxxxxxxxxxx",
    project_id="YOUR_PROJECT_ID",
    environment="dev",
    version_name="v1",  # optional — omit to use server default
    verify_ssl=True,    # or False to skip, or "/path/to/ca-bundle.crt"
    verbose=True,       # prints loaded keys
)

# Now use secrets like normal env vars
import os
db_url = os.environ["DATABASE_URL"]
api_key = os.environ["API_KEY"]
```

### 2. Use the client directly

```python
from envvault import EnvVaultClient

client = EnvVaultClient(
    server_url="https://example.com",
    service_token="xxxxxxxxxxxxxxxx",
    verify_ssl=True,  # False to skip SSL verification, or path to CA bundle
)

# Get all secrets as a dict
secrets = client.get_secrets(
    project_id="YOUR_PROJECT_ID",
    environment="dev",
    version_name="v1",  # optional
)
print(secrets)
# {"DATABASE_URL": "postgres://...", "API_KEY": "sk-..."}

# Get a single secret
db_url = client.get_secret("YOUR_PROJECT_ID", "dev", "DATABASE_URL", version_name="v1")
```

### 3. Export to `.env` file

```python
from envvault import EnvVaultClient

client = EnvVaultClient(
    server_url="http://example.com",
    service_token="xxxxxxxxxxxxxxxx",
)

# Generate .env file
client.export_dotenv("YOUR_PROJECT_ID", "dev", path=".env", version_name="v1")
```

### 4. Load from config file

Create `.envvault.json` in your project root:

```json
{
    "server_url": "https://example.com",
    "service_token": "xxxxxxxxxxxxxxxx",
    "project_id": "YOUR_PROJECT_ID",
    "environment": "dev",
    "version_name": "v1",
    "verify_ssl": true
}
```

Then in your app:

```python
from envvault import load_env_from_file

load_env_from_file(".envvault.json", verbose=True)
```

> **Tip:** You can also set the token via `ENVVAULT_SERVICE_TOKEN` env var instead of putting it in the config file.

## CLI Usage

The SDK includes a CLI tool:

```bash
# Set your token
export ENVVAULT_SERVICE_TOKEN="xxxxxxxxxxxxxxxx"

# Fetch secrets as JSON
envvault fetch --project-id YOUR_PROJECT_ID --env dev --version v1

# Export to .env file
envvault export --project-id YOUR_PROJECT_ID --env prod --version v2 --output .env.prod

# Run a command with secrets injected
envvault run --project-id YOUR_PROJECT_ID --env dev --version v1 -- python app.py
```

## Integration Examples

### Flask App

```python
# app.py
from envvault import load_env
load_env(
    server_url="http://example.com",
    service_token="xxx",
    project_id="abc123",
    environment="dev",
)

from flask import Flask
import os

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]

@app.route("/")
def hello():
    return f"Connected to: {os.environ.get('DATABASE_URL', 'not set')}"
```

### FastAPI App

```python
# main.py
from envvault import load_env
load_env(
    server_url="http://example.com",
    service_token="xxx",
    project_id="abc123",
    environment="dev",
)

from fastapi import FastAPI
import os

app = FastAPI()

@app.get("/config")
def get_config():
    return {
        "db_host": os.environ.get("DB_HOST"),
        "redis_url": os.environ.get("REDIS_URL"),
    }
```

### Django Settings

```python
# settings.py
from envvault import load_env
load_env(
    server_url="http://example.com",
    service_token="xxx",
    project_id="abc123",
    environment="prod",
    override=False,  # don't overwrite existing env vars
)

import os
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ["DB_HOST"],
        "PORT": os.environ.get("DB_PORT", "5432"),
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
    }
}
```

## Getting a Service Token

1. Open your EnvVault dashboard
2. Navigate to your project → **Settings**
3. Click **Create Service Token**
4. Set a name and scope (which environments the token can access)
5. Copy the generated token (starts with ``)

## API Reference

### `load_env(server_url, service_token, project_id, environment, version_name=None, override=False, verbose=False, verify_ssl=True)`

Fetches secrets and sets them in `os.environ`. Returns a dict of loaded secrets.

| Parameter | Description |
|---|---|
| `verify_ssl` | `True` (default) to verify SSL, `False` to skip, or a path string to a CA bundle |

### `load_env_from_file(config_path=".envvault.json", override=False, verbose=False, verify_ssl=True)`

Same as `load_env` but reads config from a JSON file. Supports `version_name` and `verify_ssl` in the config.

### `EnvVaultClient(server_url, service_token=None, jwt_token=None, verify_ssl=True)`

Low-level API client. All secret methods accept an optional `version_name` parameter:
- `get_secrets(project_id, environment, version_name=None)` → `dict[str, str]`
- `get_secrets_raw(project_id, environment, version_name=None)` → `list[dict]`
- `get_secret(project_id, environment, key, version_name=None)` → `str | None`
- `set_secret(project_id, environment, key, value, comment="", version_name=None)` → `dict`
- `delete_secret(secret_id)` → `None`
- `export_dotenv(project_id, environment, path=".env", version_name=None)` → `Path`
- `export_json(project_id, environment, path="env.json", version_name=None)` → `Path`
