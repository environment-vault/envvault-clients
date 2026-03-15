"""
EnvVault API Client

Communicates with the EnvVault server to fetch, create, and manage secrets.
Supports two auth modes:
  1. Service Token (for CI/CD, server apps) — uses X-Service-Token header
  2. JWT (for interactive apps) — uses Authorization: Bearer header

Uses only Python standard library (http.client) — no external dependencies.
"""

from __future__ import annotations

import http.client
import json
import socket
import ssl
from typing import Any, Dict, List, Optional
from pathlib import Path
from urllib.parse import urlparse, urlencode, quote


class EnvVaultError(Exception):
    """Base exception for EnvVault client errors."""
    pass


class AuthenticationError(EnvVaultError):
    """Raised when authentication fails."""
    pass


class NotFoundError(EnvVaultError):
    """Raised when a resource is not found."""
    pass


def _make_connection(
    parsed_url,
    timeout: int = 30,
    verify_ssl: bool | str = True,
) -> http.client.HTTPConnection | http.client.HTTPSConnection:
    """Create an HTTP(S) connection from a parsed URL."""
    host = parsed_url.hostname
    port = parsed_url.port

    if parsed_url.scheme == "https":
        if verify_ssl is False:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        elif isinstance(verify_ssl, str):
            ctx = ssl.create_default_context(cafile=verify_ssl)
        else:
            ctx = ssl.create_default_context()
        return http.client.HTTPSConnection(host, port=port or 443, timeout=timeout, context=ctx)
    else:
        return http.client.HTTPConnection(host, port=port or 80, timeout=timeout)


def _do_request(
    method: str,
    url: str,
    headers: Dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: int = 30,
    verify_ssl: bool | str = True,
):
    """Low-level helper: perform a single HTTP(S) request and return (status, body_str)."""
    parsed = urlparse(url)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    conn = _make_connection(parsed, timeout=timeout, verify_ssl=verify_ssl)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        resp_body = resp.read().decode("utf-8")
        return resp.status, resp_body
    finally:
        conn.close()


class EnvVaultClient:
    """
    Client for the EnvVault API.

    Args:
        server_url: Base URL of the EnvVault server (e.g. http://localhost:8000)
        service_token: Service token string for authentication (starts with evst_)
        jwt_token: JWT access token for user-based auth (alternative to service_token)
        timeout: Request timeout in seconds (default 30)
        verify_ssl: SSL verification — True (default), False to skip, or path to CA bundle
    """

    def __init__(
        self,
        server_url: str,
        service_token: Optional[str] = None,
        jwt_token: Optional[str] = None,
        timeout: int = 30,
        verify_ssl: bool | str = True,
    ):
        self.server_url = server_url.rstrip("/")
        self.api_base = f"{self.server_url}/api/v1"
        self.service_token = service_token
        self.jwt_token = jwt_token
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self._parsed = urlparse(self.server_url)

        if not service_token and not jwt_token:
            raise EnvVaultError("Either service_token or jwt_token must be provided")

    @property
    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.service_token:
            headers["X-Service-Token"] = self.service_token
        elif self.jwt_token:
            headers["Authorization"] = f"Bearer {self.jwt_token}"
        return headers

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.api_base}{path}"

        # Handle query params
        params = kwargs.pop("params", None)
        if params:
            url = f"{url}?{urlencode(params)}"

        # Handle JSON body
        body = None
        json_data = kwargs.pop("json", None)
        if json_data is not None:
            body = json.dumps(json_data).encode("utf-8")

        parsed = urlparse(url)
        request_path = parsed.path or "/"
        if parsed.query:
            request_path = f"{request_path}?{parsed.query}"

        conn = _make_connection(parsed, timeout=self.timeout, verify_ssl=self.verify_ssl)
        try:
            try:
                conn.request(method, request_path, body=body, headers=self._headers)
                resp = conn.getresponse()
                resp_body = resp.read().decode("utf-8")
                status = resp.status
            except (ConnectionError, OSError, socket.timeout):
                raise EnvVaultError(f"Cannot connect to EnvVault server at {self.server_url}")
            except socket.timeout:
                raise EnvVaultError(f"Request timed out after {self.timeout}s")
        finally:
            conn.close()

        if status == 401:
            raise AuthenticationError("Invalid or expired token")
        if status == 403:
            raise AuthenticationError("Insufficient permissions for this operation")
        if status == 404:
            raise NotFoundError(f"Resource not found: {path}")
        if status >= 400:
            detail = ""
            try:
                detail = json.loads(resp_body).get("detail", resp_body)
            except Exception:
                detail = resp_body
            raise EnvVaultError(f"API error {status}: {detail}")

        if status == 204:
            return None
        return json.loads(resp_body)

    # ── Auth (JWT mode) ──────────────────────────────────────────────

    @classmethod
    def login(cls, server_url: str, email: str, password: str, **kwargs: Any) -> "EnvVaultClient":
        """
        Authenticate with email/password and return a client with JWT token.

        Returns:
            EnvVaultClient configured with the JWT access token
        """
        verify_ssl = kwargs.pop("verify_ssl", True)
        url = f"{server_url.rstrip('/')}/api/v1/auth/login"
        body = json.dumps({"email": email, "password": password}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        status, resp_body = _do_request("POST", url, headers=headers, body=body, timeout=30, verify_ssl=verify_ssl)
        if status != 200:
            raise AuthenticationError("Login failed: invalid credentials")
        data = json.loads(resp_body)
        return cls(server_url=server_url, jwt_token=data["access_token"], verify_ssl=verify_ssl, **kwargs)

    # ── Projects ─────────────────────────────────────────────────────

    def list_projects(self, org_id: str) -> List[Dict]:
        """List all projects in an organization."""
        return self._request("GET", f"/projects?org_id={org_id}")

    def get_project(self, project_id: str) -> Dict:
        """Get project details by ID."""
        return self._request("GET", f"/projects/{project_id}")

    # ── Secrets ──────────────────────────────────────────────────────

    def get_secrets(
        self,
        project_id: str,
        environment: str,
        version_name: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Fetch all secrets for a project environment.

        Args:
            project_id: The project's ID
            environment: Environment slug (e.g. 'dev', 'staging', 'prod')
            version_name: Version name (e.g. 'v1', 'v2'). If None, uses the
                          server's default resolution.

        Returns:
            Dictionary mapping secret keys to their decrypted values
        """
        params = {}
        if version_name:
            params["version_name"] = version_name
        data = self._request("GET", f"/secrets/{project_id}/{environment}", params=params)
        items = data.get("items", data) if isinstance(data, dict) else data
        return {item["key"]: item["value"] for item in items}

    def get_secrets_raw(
        self,
        project_id: str,
        environment: str,
        version_name: Optional[str] = None,
    ) -> List[Dict]:
        """
        Fetch all secrets with full metadata (key, value, version, etc.).

        Args:
            project_id: The project's ID
            environment: Environment slug
            version_name: Version name (e.g. 'v1'). If None, server default.
        """
        params = {}
        if version_name:
            params["version_name"] = version_name
        data = self._request("GET", f"/secrets/{project_id}/{environment}", params=params)
        return data.get("items", data) if isinstance(data, dict) else data

    def get_secret(
        self,
        project_id: str,
        environment: str,
        key: str,
        version_name: Optional[str] = None,
    ) -> Optional[str]:
        """
        Fetch a single secret value by key.

        Args:
            project_id: The project's ID
            environment: Environment slug
            key: Secret key name
            version_name: Version name (e.g. 'v1'). If None, server default.

        Returns:
            The secret value string, or None if not found
        """
        secrets = self.get_secrets(project_id, environment, version_name=version_name)
        return secrets.get(key)

    def set_secret(
        self,
        project_id: str,
        environment: str,
        key: str,
        value: str,
        comment: str = "",
        version_name: Optional[str] = None,
    ) -> Dict:
        """Create or update a secret.

        Args:
            project_id: The project's ID
            environment: Environment slug
            key: Secret key
            value: Secret value
            comment: Optional comment
            version_name: Version name (e.g. 'v1'). If None, server default.
        """
        payload: Dict[str, Any] = {"key": key, "value": value, "comment": comment}
        if version_name:
            payload["version_name"] = version_name
        return self._request(
            "POST",
            f"/secrets/{project_id}/{environment}",
            json=payload,
        )

    def delete_secret(self, secret_id: str) -> None:
        """Delete a secret by its ID."""
        self._request("DELETE", f"/secrets/{secret_id}")

    # ── Env Configs (.env files) ───────────────────────────────────────

    def list_env_config_names(
        self,
        project_id: str,
        environment: str,
        version_name: Optional[str] = None,
    ) -> List[str]:
        """
        List env config file names in a project environment.

        Args:
            project_id: Project ID
            environment: Environment slug
            version_name: Version name (e.g. 'v1'). If None, server default.

        Returns:
            List of env config names (e.g. ['.env', 'config.env'])
        """
        params = {}
        if version_name:
            params["version_name"] = version_name
        data = self._request(
            "GET", f"/env-configs/{project_id}/{environment}/names", params=params
        )
        return data.get("names", [])

    def get_env_config(
        self,
        project_id: str,
        environment: str,
        name: str,
        version_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch a .env config file content by name.

        Args:
            project_id: Project ID
            environment: Environment slug
            name: Config name (e.g. '.env', 'config.env')
            version_name: Version name (e.g. 'v1'). If None, server default.

        Returns:
            Dict with id, project_id, environment_slug, name, content, etc.
        """
        params = {}
        if version_name:
            params["version_name"] = version_name
        name_enc = quote(name, safe=".-_")
        return self._request(
            "GET", f"/env-configs/{project_id}/{environment}/{name_enc}", params=params
        )

    def export_env_config(
        self,
        project_id: str,
        environment: str,
        name: str = ".env",
        path: str = ".env",
        overwrite: bool = True,
        version_name: Optional[str] = None,
    ) -> Path:
        """
        Export an env config to a .env file.

        Args:
            project_id: Project ID
            environment: Environment slug
            name: Env config name in EnvVault (default: '.env')
            path: Output file path
            overwrite: Whether to overwrite existing file
            version_name: Version name (e.g. 'v1'). If None, server default.

        Returns:
            Path to the created file
        """
        config = self.get_env_config(project_id, environment, name, version_name=version_name)
        output = Path(path)
        if output.exists() and not overwrite:
            raise EnvVaultError(f"File {path} already exists. Set overwrite=True to replace.")
        content = config.get("content", "")
        output.write_text(content, encoding="utf-8")
        return output

    # ── YAML Configs ───────────────────────────────────────────────────

    def list_yaml_config_names(
        self,
        project_id: str,
        environment: str,
        version_name: Optional[str] = None,
    ) -> List[str]:
        """
        List YAML config file names in a project environment.

        Args:
            project_id: Project ID
            environment: Environment slug
            version_name: Version name (e.g. 'v1'). If None, server default.

        Returns:
            List of YAML config names
        """
        params = {}
        if version_name:
            params["version_name"] = version_name
        data = self._request(
            "GET", f"/yaml-configs/{project_id}/{environment}/names", params=params
        )
        return data.get("names", [])

    def get_yaml_config(
        self,
        project_id: str,
        environment: str,
        name: str,
        version_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch a YAML config file content by name.

        Args:
            project_id: Project ID
            environment: Environment slug
            name: Config name (e.g. 'config.yaml', 'settings.yml')
            version_name: Version name (e.g. 'v1'). If None, server default.

        Returns:
            Dict with id, project_id, environment_slug, name, content, etc.
        """
        params = {}
        if version_name:
            params["version_name"] = version_name
        name_enc = quote(name, safe=".-_")
        return self._request(
            "GET", f"/yaml-configs/{project_id}/{environment}/{name_enc}", params=params
        )

    def get_yaml_config_parsed(
        self,
        project_id: str,
        environment: str,
        name: str,
        version_name: Optional[str] = None,
    ) -> Any:
        """
        Fetch a YAML config and parse it as a Python dict/list.

        Requires PyYAML: pip install pyyaml

        Args:
            project_id: Project ID
            environment: Environment slug
            name: Config name
            version_name: Version name. If None, server default.

        Returns:
            Parsed YAML as dict or list
        """
        try:
            import yaml
        except ImportError:
            raise EnvVaultError(
                "PyYAML required for get_yaml_config_parsed. Install with: pip install pyyaml"
            )
        config = self.get_yaml_config(project_id, environment, name, version_name=version_name)
        content = config.get("content", "")
        return yaml.safe_load(content) if content else {}

    def export_yaml_config(
        self,
        project_id: str,
        environment: str,
        name: str,
        path: Optional[str] = None,
        overwrite: bool = True,
        version_name: Optional[str] = None,
    ) -> Path:
        """
        Export a YAML config to a file.

        Args:
            project_id: Project ID
            environment: Environment slug
            name: YAML config name in EnvVault
            path: Output file path (default: same as name)
            overwrite: Whether to overwrite existing file
            version_name: Version name. If None, server default.

        Returns:
            Path to the created file
        """
        config = self.get_yaml_config(project_id, environment, name, version_name=version_name)
        output = Path(path or name)
        if output.exists() and not overwrite:
            raise EnvVaultError(
                f"File {output} already exists. Set overwrite=True to replace."
            )
        content = config.get("content", "")
        output.write_text(content, encoding="utf-8")
        return output

    # ── Export (secrets → .env) ────────────────────────────────────────

    def export_dotenv(
        self,
        project_id: str,
        environment: str,
        path: str = ".env",
        overwrite: bool = True,
        version_name: Optional[str] = None,
    ) -> Path:
        """
        Export secrets to a .env file.

        Args:
            project_id: Project ID
            environment: Environment slug
            path: Output file path (default: .env)
            overwrite: Whether to overwrite existing file
            version_name: Version name (e.g. 'v1'). If None, server default.

        Returns:
            Path to the created .env file
        """
        secrets = self.get_secrets(project_id, environment, version_name=version_name)
        output = Path(path)

        if output.exists() and not overwrite:
            raise EnvVaultError(f"File {path} already exists. Set overwrite=True to replace.")

        version_label = f" | Version: {version_name}" if version_name else ""
        lines = [
            f"# Generated by EnvVault SDK",
            f"# Project: {project_id} | Environment: {environment}{version_label}",
            "",
        ]
        for key, value in sorted(secrets.items()):
            # Escape special characters in values
            if any(c in value for c in [" ", '"', "'", "#", "\n", "\\", "$"]):
                escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
                lines.append(f'{key}="{escaped}"')
            else:
                lines.append(f"{key}={value}")

        output.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return output

    def export_json(
        self,
        project_id: str,
        environment: str,
        path: str = "env.json",
        version_name: Optional[str] = None,
    ) -> Path:
        """Export secrets to a JSON file.

        Args:
            project_id: Project ID
            environment: Environment slug
            path: Output file path (default: env.json)
            version_name: Version name (e.g. 'v1'). If None, server default.
        """
        secrets = self.get_secrets(project_id, environment, version_name=version_name)
        output = Path(path)
        output.write_text(json.dumps(secrets, indent=2) + "\n", encoding="utf-8")
        return output
