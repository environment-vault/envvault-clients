"""
EnvVault Python Client SDK

Settings-first, list-based config loading. Configure credentials and fetch list,
then load in minimal server requests. Values never logged; verbose shows key names only.

Usage:
    # Config file (recommended)
    from envvault import load_from_file
    load_from_file(".envvault.json", verbose=True)

    # Config dict (no file)
    from envvault import load_from_config
    load_from_config(config_dict, verbose=True)

    # Individual loaders
    from envvault import load_env, load_env_config, load_yaml_config
    load_env(server_url="...", service_token="...", project_id="...", environment="dev")
    load_env_config(..., name=".env")
    config = load_yaml_config(..., name="config.yaml")

    # Client API
    from envvault import EnvVaultClient
    client = EnvVaultClient(server_url="...", service_token="...")
"""

from envvault.client import EnvVaultClient, EnvVaultError
from envvault.loader import (
    Settings,
    load_env,
    load_env_config,
    load_from_config,
    load_from_file,
    load_yaml_config,
)

__version__ = "0.2.0"
__all__ = [
    "EnvVaultClient",
    "EnvVaultError",
    "Settings",
    "load_env",
    "load_env_config",
    "load_from_config",
    "load_from_file",
    "load_yaml_config",
]
