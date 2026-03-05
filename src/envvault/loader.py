"""
EnvVault Environment Loader

Convenience functions to load secrets directly into os.environ
or from a config file.
"""

from __future__ import annotations

import os
import json
from typing import Optional
from pathlib import Path

from envvault.client import EnvVaultClient, EnvVaultError


def load_env(
    server_url: str,
    service_token: Optional[str] = None,
    jwt_token: Optional[str] = None,
    project_id: Optional[str] = None,
    environment: str = "dev",
    version_name: Optional[str] = None,
    override: bool = False,
    verbose: bool = False,
    verify_ssl: bool | str = True,
) -> dict[str, str]:
    """
    Fetch secrets from EnvVault and inject them into os.environ.

    Args:
        server_url: EnvVault server URL
        service_token: Service token for auth
        jwt_token: JWT token for auth (alternative)
        project_id: Project ID to fetch secrets from
        environment: Environment slug (default: 'dev')
        version_name: Project version (e.g. 'v1', 'v2'). If None, uses
                      the server's default resolution.
        override: If True, overwrite existing env vars (default: False)
        verbose: If True, print loaded keys to stdout
        verify_ssl: SSL verification — True (default), False to skip, or path to CA bundle

    Returns:
        Dictionary of loaded secrets

    Raises:
        EnvVaultError: If connection or auth fails

    Example:
        >>> from envvault import load_env
        >>> load_env(
        ...     server_url="http://localhost:8000",
        ...     service_token="evst_xxxx",
        ...     project_id="abc123",
        ...     environment="dev",
        ...     version_name="v2",
        ... )
    """
    if not project_id:
        raise EnvVaultError("project_id is required")

    client = EnvVaultClient(
        server_url=server_url,
        service_token=service_token,
        jwt_token=jwt_token,
        verify_ssl=verify_ssl,
    )

    secrets = client.get_secrets(project_id, environment, version_name=version_name)

    loaded = {}
    for key, value in secrets.items():
        if override or key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
            if verbose:
                print(f"  [envvault] Loaded: {key}")
        elif verbose:
            print(f"  [envvault] Skipped (exists): {key}")

    version_label = f" (version: {version_name})" if version_name else ""
    if verbose:
        print(f"  [envvault] Total: {len(loaded)} secrets loaded from '{environment}'{version_label}")

    return loaded


def load_env_from_file(
    config_path: str = ".envvault.json",
    override: bool = False,
    verbose: bool = False,
    verify_ssl: bool | str = True,
) -> dict[str, str]:
    """
    Load secrets using a JSON config file.

    Config file format (.envvault.json):
    {
        "server_url": "http://localhost:8000",
        "service_token": "evst_xxxxx",
        "project_id": "abc123",
        "environment": "dev"
    }

    The service_token can also be set via ENVVAULT_SERVICE_TOKEN env var.

    Args:
        config_path: Path to config file (default: .envvault.json)
        override: If True, overwrite existing env vars
        verbose: If True, print loaded keys
        verify_ssl: SSL verification — True (default), False to skip, or path to CA bundle

    Returns:
        Dictionary of loaded secrets
    """
    path = Path(config_path)
    if not path.exists():
        raise EnvVaultError(f"Config file not found: {config_path}")

    with open(path) as f:
        config = json.load(f)

    return load_env(
        server_url=config["server_url"],
        service_token=config.get("service_token") or os.environ.get("ENVVAULT_SERVICE_TOKEN"),
        project_id=config.get("project_id"),
        environment=config.get("environment", "dev"),
        version_name=config.get("version_name"),
        override=override,
        verbose=verbose,
        verify_ssl=config.get("verify_ssl", verify_ssl),
    )
