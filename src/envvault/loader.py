"""
EnvVault loader — settings-first, short-TTL cache.

1. Configure once: ``Settings.configure()`` or ``Settings.from_file()``.
2. Use anywhere: ``load_env_config(name=".env")``, ``load_yaml_config(name="config.yaml")``.
3. Default cache TTL is 5s; adjust with ``Settings.cache_ttl``.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

from envvault.client import EnvVaultClient, EnvVaultError


def _mask_dict(data: dict[str, str], mask: str = "***") -> dict[str, str]:
    """Mask every value in a flat string dict (for safe display)."""
    return {k: mask for k in data}


def _mask_any(data: Any, mask: str = "***") -> Any:
    """Recursively mask string/scalar leaves in dicts and lists."""
    if isinstance(data, dict):
        return {k: _mask_any(v, mask) for k, v in data.items()}
    if isinstance(data, list):
        return [_mask_any(v, mask) for v in data]
    if isinstance(data, str) or (data is not None and not isinstance(data, (dict, list))):
        return mask
    return data


def _load_config_file_or_dict(
    config_path: Optional[str],
    config: Optional[dict],
) -> dict:
    """Load JSON from path or return a shallow copy of ``config``."""
    if config is not None:
        return dict(config)
    path = Path(config_path or ".envvault.json")
    if not path.exists():
        raise EnvVaultError(f"Config file not found: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _service_token_from_dict(c: dict) -> str:
    token = c.get("service_token") or os.environ.get("ENVVAULT_SERVICE_TOKEN")
    if not token:
        raise EnvVaultError("service_token required in config or set ENVVAULT_SERVICE_TOKEN")
    return token


def _client_params_from_config_dict(
    c: dict,
    verify_ssl_fallback: bool | str,
) -> tuple[str, str, str, str, Optional[str], bool | str]:
    """Return (server_url, token, project_id, environment, version_name, verify_ssl)."""
    server_url = c.get("server_url")
    project_id = c.get("project_id")
    if not server_url or not project_id:
        raise EnvVaultError("server_url and project_id required in config")
    token = _service_token_from_dict(c)
    environment = c.get("environment", "dev")
    version_name = c.get("version_name")
    verify_ssl = c.get("verify_ssl", verify_ssl_fallback)
    return server_url, token, project_id, environment, version_name, verify_ssl


def _client_from_resolved(
    server_url: str,
    token: str,
    verify_ssl: bool | str,
) -> EnvVaultClient:
    return EnvVaultClient(server_url=server_url, service_token=token, verify_ssl=verify_ssl)


class _Settings:
    """Process-wide settings and response cache. Configure once, reuse everywhere."""

    cache_ttl: float = 5.0
    mask_values: bool = False  # when True, loaders may return masked values instead of secrets

    def __init__(self) -> None:
        self._config: Optional[dict] = None
        self._client: Optional[EnvVaultClient] = None
        self._cache: dict[str, tuple[Any, float]] = {}

    def configure(
        self,
        server_url: str,
        project_id: str,
        *,
        service_token: Optional[str] = None,
        environment: str = "dev",
        version_name: Optional[str] = None,
        verify_ssl: bool | str = True,
        fetch: Optional[dict] = None,
    ) -> None:
        """Set credentials. Call once at app startup."""
        token = service_token or os.environ.get("ENVVAULT_SERVICE_TOKEN")
        if not token:
            raise EnvVaultError("service_token required or set ENVVAULT_SERVICE_TOKEN")
        self._config = {
            "server_url": server_url,
            "service_token": token,
            "project_id": project_id,
            "environment": environment,
            "version_name": version_name,
            "verify_ssl": verify_ssl,
            "fetch": fetch or {},
        }
        self._client = EnvVaultClient(
            server_url=server_url,
            service_token=token,
            verify_ssl=verify_ssl,
        )
        self._cache.clear()
        if fetch:
            self._prefetch(fetch)

    def from_file(self, config_path: str = ".envvault.json") -> None:
        """Load config from file. Call once at app startup. Fetches according to fetch list."""
        path = Path(config_path)
        if not path.exists():
            raise EnvVaultError(f"Config file not found: {config_path}")
        with open(path) as f:
            cfg = json.load(f)
        self._apply_config(cfg)

    def from_config(self, config: dict) -> None:
        """Load config from dict. Call once at app startup."""
        self._apply_config(config)

    def _apply_config(self, cfg: dict) -> None:
        server_url = cfg.get("server_url")
        if not server_url:
            raise EnvVaultError("server_url required in config")
        project_id = cfg.get("project_id")
        if not project_id:
            raise EnvVaultError("project_id required in config")
        token = cfg.get("service_token") or os.environ.get("ENVVAULT_SERVICE_TOKEN")
        if not token:
            raise EnvVaultError("service_token required in config or ENVVAULT_SERVICE_TOKEN")
        fetch = cfg.get("fetch", {})
        self.configure(
            server_url=server_url,
            project_id=project_id,
            service_token=token,
            environment=cfg.get("environment", "dev"),
            version_name=cfg.get("version_name"),
            verify_ssl=cfg.get("verify_ssl", True),
            fetch=fetch,
        )

    def _prefetch(self, fetch: dict) -> None:
        """Prefetch only items in fetch list. Minimizes requests."""
        pid = self._config["project_id"]
        env = self._config["environment"]
        ver = self._config.get("version_name")
        now = time.time()
        if fetch.get("secrets"):
            data = self._client.get_secrets(pid, env, version_name=ver)
            self._cache["secrets"] = (data, now)
        for name in fetch.get("env_config_names", []):
            cfg = self._client.get_env_config(pid, env, name, version_name=ver)
            parsed = _parse_env_content(cfg.get("content", ""))
            self._cache[f"env_config:{name}"] = (parsed, now)
        for name in fetch.get("yaml_config_names", []):
            data = self._client.get_yaml_config_parsed(pid, env, name, version_name=ver)
            self._cache[f"yaml_config:{name}"] = (data, now)

    def _is_expired(self, key: str) -> bool:
        if key not in self._cache:
            return True
        _, ts = self._cache[key]
        return (time.time() - ts) > self.cache_ttl

    def _ensure_configured(self, config_path: str = ".envvault.json") -> None:
        """Auto-load from .envvault.json if not configured."""
        if self._config and self._client:
            return
        path = Path(config_path)
        if path.exists():
            self.from_file(str(path))
        else:
            raise EnvVaultError(
                "Settings not configured. Call Settings.from_file() or Settings.configure() first, "
                f"or create {config_path}"
            )

    def get_env_config(self, name: str = ".env", config_path: str = ".envvault.json") -> dict[str, str]:
        """Fetch parsed .env config; uses cache when still fresh (see ``cache_ttl``)."""
        self._ensure_configured(config_path)
        key = f"env_config:{name}"
        if not self._is_expired(key):
            return self._cache[key][0]
        cfg = self._client.get_env_config(
            self._config["project_id"],
            self._config["environment"],
            name,
            version_name=self._config.get("version_name"),
        )
        parsed = _parse_env_content(cfg.get("content", ""))
        self._cache[key] = (parsed, time.time())
        return parsed

    def get_yaml_config(self, name: str = "config.yaml", config_path: str = ".envvault.json") -> Any:
        """Fetch parsed YAML config; uses cache when still fresh (see ``cache_ttl``)."""
        self._ensure_configured(config_path)
        key = f"yaml_config:{name}"
        if not self._is_expired(key):
            return self._cache[key][0]
        data = self._client.get_yaml_config_parsed(
            self._config["project_id"],
            self._config["environment"],
            name,
            version_name=self._config.get("version_name"),
        )
        self._cache[key] = (data, time.time())
        return data

    def get_secrets(self, config_path: str = ".envvault.json") -> dict[str, str]:
        """Fetch secrets map; uses cache when still fresh (see ``cache_ttl``)."""
        self._ensure_configured(config_path)
        key = "secrets"
        if not self._is_expired(key):
            return self._cache[key][0]
        data = self._client.get_secrets(
            self._config["project_id"],
            self._config["environment"],
            version_name=self._config.get("version_name"),
        )
        self._cache[key] = (data, time.time())
        return data


Settings = _Settings()


def _parse_env_content(content: str) -> dict[str, str]:
    """Parse .env-style content into key-value dict."""
    result: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" in line:
            key, val = line.split("=", 1)
            key = key.strip()
            if key and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
                val = val.strip()
                if val.startswith('"') and val.endswith('"'):
                    val = val[1:-1].replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
                elif val.startswith("'") and val.endswith("'"):
                    val = val[1:-1].replace("\\'", "'")
                result[key] = val
    return result


def _flatten_yaml_to_env(d: dict, prefix: str = "", env_prefix: str = "") -> dict[str, str]:
    """Flatten nested dict to env-like key-value. Keys only, no values in logs."""
    out: dict[str, str] = {}
    for k, v in d.items():
        key = f"{prefix}{k}" if prefix else k
        env_key = env_prefix + key.upper().replace(".", "_").replace("-", "_")
        if isinstance(v, dict):
            out.update(_flatten_yaml_to_env(v, f"{key}_", env_prefix))
        elif v is not None and not isinstance(v, (dict, list)):
            out[env_key] = str(v)
    return out


def _inject_to_env(
    data: dict[str, str],
    override: bool,
    verbose: bool,
) -> dict[str, str]:
    """Merge into ``os.environ``; if ``verbose``, print key names only (never values)."""
    loaded = {}
    for key in data:
        if override or key not in os.environ:
            os.environ[key] = data[key]
            loaded[key] = data[key]
            if verbose:
                print(f"  [envvault] Loaded: {key}")
        elif verbose:
            print(f"  [envvault] Skipped (exists): {key}")
    return loaded


def load_from_file(
    config_path: str = ".envvault.json",
    override: bool = False,
    verbose: bool = False,
    verify_ssl: bool | str | None = None,
) -> dict[str, Any]:
    """
    Load from a JSON config file (single read), apply settings, and inject per ``fetch``.

    Only requests resources listed under ``fetch`` (secrets, named env configs, named YAML).
    Never logs secret values; with ``verbose=True`` only key names are printed.

    Config shape (see ``.envvault.json.example``):

    - ``service_token``: omit or null and set ``ENVVAULT_SERVICE_TOKEN``
    - ``fetch.secrets``: if true, one request for key-value secrets
    - ``fetch.env_config_names``: list of named .env configs (one request each)
    - ``fetch.yaml_config_names``: list of YAML configs (one request each)
    - ``yaml_inject_to_env`` / ``yaml_env_prefix``: optional flatten-and-inject for YAML

    Returns:
        ``{"loaded_keys": [...], "yaml": {name: data}}``. Do not log this dict in production.

    Args:
        verify_ssl: If not ``None``, overrides ``verify_ssl`` from the file for this run.
    """
    path = Path(config_path)
    if not path.exists():
        raise EnvVaultError(f"Config file not found: {config_path}")
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    return load_from_config(cfg, override=override, verbose=verbose, verify_ssl=verify_ssl)


def load_from_config(
    config: dict,
    override: bool = False,
    verbose: bool = False,
    verify_ssl: bool | str | None = None,
) -> dict[str, Any]:
    """
    Apply ``config`` to ``Settings``, prefetch per ``fetch``, and inject into ``os.environ``.

    Only fetches ``fetch.secrets``, each name in ``fetch.env_config_names``, and each YAML name
    in ``fetch.yaml_config_names``.

    Args:
        verify_ssl: If not ``None``, overrides the value from ``config`` before connecting.
    """
    cfg = dict(config)
    if verify_ssl is not None:
        cfg["verify_ssl"] = verify_ssl
    Settings._apply_config(cfg)
    fetch = cfg.get("fetch", {})
    yaml_inject = cfg.get("yaml_inject_to_env", False)
    yaml_prefix = cfg.get("yaml_env_prefix", "")
    all_loaded: dict[str, str] = {}
    yaml_data: dict[str, Any] = {}

    if fetch.get("secrets"):
        s = Settings.get_secrets()
        all_loaded.update(_inject_to_env(s, override, verbose))

    for name in fetch.get("env_config_names", []):
        parsed = Settings.get_env_config(name)
        all_loaded.update(_inject_to_env(parsed, override, verbose))

    for name in fetch.get("yaml_config_names", []):
        data = Settings.get_yaml_config(name)
        yaml_data[name] = data
        if yaml_inject and isinstance(data, dict):
            flat = _flatten_yaml_to_env(data, env_prefix=yaml_prefix)
            all_loaded.update(_inject_to_env(flat, override, verbose))

    if verbose and all_loaded:
        print(f"  [envvault] Total: {len(all_loaded)} keys loaded")

    return {"loaded_keys": list(all_loaded.keys()), "yaml": yaml_data}


def load_env(
    override: bool = False,
    verbose: bool = False,
    *,
    server_url: Optional[str] = None,
    service_token: Optional[str] = None,
    project_id: Optional[str] = None,
    environment: str = "dev",
    version_name: Optional[str] = None,
    verify_ssl: bool | str = True,
    config_path: Optional[str] = None,
    config: Optional[dict] = None,
) -> dict[str, str]:
    """
    Fetch project secrets and optionally inject into ``os.environ``.

    If ``Settings`` is already configured and you pass no credentials or config file, uses the
    cached ``Settings`` client (see ``Settings.cache_ttl``).

    Otherwise pass explicit ``server_url`` / ``project_id`` / ``service_token``, or
    ``config_path`` / ``config`` to build a one-off client.
    """
    if server_url is None and project_id is None and not config_path and not config:
        data = Settings.get_secrets()
        return _inject_to_env(data, override, verbose)

    if config_path or config:
        c = _load_config_file_or_dict(config_path, config)
        server_url, token, project_id, environment, version_name, verify_ssl = _client_params_from_config_dict(
            c, verify_ssl
        )
        client = _client_from_resolved(server_url, token, verify_ssl)
        secrets = client.get_secrets(project_id, environment, version_name=version_name)
        return _inject_to_env(secrets, override, verbose)

    token = service_token or os.environ.get("ENVVAULT_SERVICE_TOKEN")
    if not project_id or not server_url or not token:
        raise EnvVaultError(
            "project_id, server_url, and service_token required (or configure Settings / pass config_path)"
        )
    client = _client_from_resolved(server_url, token, verify_ssl)
    secrets = client.get_secrets(project_id, environment, version_name=version_name)
    return _inject_to_env(secrets, override, verbose)


def load_env_config(
    name: str = ".env",
    override: bool = False,
    verbose: bool = False,
    mask_values: Optional[bool] = None,
    *,
    server_url: Optional[str] = None,
    service_token: Optional[str] = None,
    project_id: Optional[str] = None,
    environment: str = "dev",
    version_name: Optional[str] = None,
    verify_ssl: bool | str = True,
    config_path: Optional[str] = None,
    config: Optional[dict] = None,
) -> dict[str, str]:
    """
    Fetch a named .env-style config, parse to a dict, optionally inject into ``os.environ``.

    Uses ``Settings`` and cache when no explicit credentials or config file are passed.
    ``mask_values``: ``None`` follows ``Settings.mask_values``; ``True`` returns ``"***"`` per key.
    """
    use_mask = mask_values if mask_values is not None else Settings.mask_values
    if server_url is None and project_id is None and not config_path and not config:
        data = Settings.get_env_config(name, config_path=".envvault.json")
        _inject_to_env(data, override, verbose)
        return _mask_dict(data) if use_mask else data

    if config_path or config:
        c = _load_config_file_or_dict(config_path, config)
        server_url, token, project_id, environment, version_name, verify_ssl = _client_params_from_config_dict(
            c, verify_ssl
        )
        client = _client_from_resolved(server_url, token, verify_ssl)
        raw = client.get_env_config(project_id, environment, name, version_name=version_name)
        parsed = _parse_env_content(raw.get("content", ""))
        _inject_to_env(parsed, override, verbose)
        return _mask_dict(parsed) if use_mask else parsed

    token = service_token or os.environ.get("ENVVAULT_SERVICE_TOKEN")
    if not project_id or not server_url or not token:
        raise EnvVaultError(
            "project_id, server_url, and service_token required (or configure Settings / pass config_path)"
        )
    client = _client_from_resolved(server_url, token, verify_ssl)
    cfg = client.get_env_config(project_id, environment, name, version_name=version_name)
    parsed = _parse_env_content(cfg.get("content", ""))
    _inject_to_env(parsed, override, verbose)
    return _mask_dict(parsed) if use_mask else parsed


def load_yaml_config(
    name: str = "config.yaml",
    inject_to_env: bool = False,
    env_prefix: str = "",
    override: bool = False,
    verbose: bool = False,
    mask_values: Optional[bool] = None,
    *,
    server_url: Optional[str] = None,
    service_token: Optional[str] = None,
    project_id: Optional[str] = None,
    environment: str = "dev",
    version_name: Optional[str] = None,
    verify_ssl: bool | str = True,
    config_path: Optional[str] = None,
    config: Optional[dict] = None,
) -> Any:
    """
    Fetch and parse a YAML config. Optionally flatten dict values into ``os.environ``.

    With ``config_path`` / ``config``, file keys ``yaml_inject_to_env`` and ``yaml_env_prefix``
    apply when not overridden by function arguments.
    """
    use_mask = mask_values if mask_values is not None else Settings.mask_values
    if server_url is None and project_id is None and not config_path and not config:
        data = Settings.get_yaml_config(name, config_path=".envvault.json")
        if inject_to_env and isinstance(data, dict):
            prefix = env_prefix or (Settings._config or {}).get("yaml_env_prefix", "")
            flat = _flatten_yaml_to_env(data, env_prefix=prefix)
            _inject_to_env(flat, override, verbose)
        return _mask_any(data) if use_mask else data

    if config_path or config:
        c = _load_config_file_or_dict(config_path, config)
        server_url, token, project_id, environment, version_name, verify_ssl = _client_params_from_config_dict(
            c, verify_ssl
        )
        inject_to_env = inject_to_env or bool(c.get("yaml_inject_to_env", False))
        if env_prefix == "":
            env_prefix = c.get("yaml_env_prefix", "") or ""
        client = _client_from_resolved(server_url, token, verify_ssl)
        data = client.get_yaml_config_parsed(project_id, environment, name, version_name=version_name)
        if inject_to_env and isinstance(data, dict):
            flat = _flatten_yaml_to_env(data, env_prefix=env_prefix)
            _inject_to_env(flat, override, verbose)
        return _mask_any(data) if use_mask else data

    token = service_token or os.environ.get("ENVVAULT_SERVICE_TOKEN")
    if not project_id or not server_url or not token:
        raise EnvVaultError(
            "project_id, server_url, and service_token required (or configure Settings / pass config_path)"
        )
    client = _client_from_resolved(server_url, token, verify_ssl)
    data = client.get_yaml_config_parsed(project_id, environment, name, version_name=version_name)
    if inject_to_env and isinstance(data, dict):
        flat = _flatten_yaml_to_env(data, env_prefix=env_prefix)
        _inject_to_env(flat, override, verbose)
    return _mask_any(data) if use_mask else data
