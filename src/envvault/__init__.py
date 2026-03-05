"""
EnvVault Python Client SDK

Fetch secrets from your EnvVault server and inject them
into your application as environment variables.

Usage:
    # Method 1: Auto-load into os.environ
    from envvault import load_env
    load_env(
        server_url="http://localhost:8000",
        service_token="evst_xxxxxxxx",
        project_slug="my-project",
        environment="dev",
        version_name="v1",
    )

    # Method 2: Get secrets as a dict
    from envvault import EnvVaultClient
    client = EnvVaultClient(
        server_url="http://localhost:8000",
        service_token="evst_xxxxxxxx",
    )
    secrets = client.get_secrets(project_slug="my-project", environment="dev", version_name="v2")

    # Method 3: Generate a .env file
    client.export_dotenv("my-project", "dev", path=".env", version_name="v1")
"""

from envvault.client import EnvVaultClient
from envvault.loader import load_env, load_env_from_file

__version__ = "0.1.0"
__all__ = ["EnvVaultClient", "load_env", "load_env_from_file"]
