"""
EnvVault CLI — Simple command-line interface for managing secrets.
env configs (.env files), and YAML configs.

Usage:
    envvault [--no-verify-ssl|-k] [--ca-bundle PATH] fetch --project-id <id> --env <env>
    envvault export --project-id <id> --env <env> [--output .env | --stdout]
    envvault env-config get|dist --project-id <id> --env <env> [--name .env] [--stdout]
    envvault yaml-config get|dist --project-id <id> --env <env> --name config.yaml
    envvault run --project-id <id> --env <env> [--name .env] -- <command> ...
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from envvault.client import EnvVaultClient, EnvVaultError


def main():
    parser = argparse.ArgumentParser(
        prog="envvault",
        description="EnvVault CLI - Manage environment variables from your terminal",
    )
    parser.add_argument(
        "--server", "-s",
        default=os.environ.get("ENVVAULT_SERVER_URL", "http://localhost:8000"),
        help="EnvVault server URL (default: ENVVAULT_SERVER_URL or http://localhost:8000)",
    )
    parser.add_argument(
        "--token", "-t",
        default=os.environ.get("ENVVAULT_SERVICE_TOKEN"),
        help="Service token (default: ENVVAULT_SERVICE_TOKEN env var)",
    )
    parser.add_argument(
        "--no-verify-ssl",
        "-k",
        action="store_true",
        help="Skip TLS certificate verification for HTTPS (insecure)",
    )
    parser.add_argument(
        "--ca-bundle",
        metavar="PATH",
        default=None,
        help="Path to PEM CA bundle for HTTPS (default: ENVVAULT_CA_BUNDLE if set)",
    )

    sub = parser.add_subparsers(dest="command", help="Command to run")

    # ── fetch ─────────────────────────────────────────────────────
    fetch_parser = sub.add_parser("fetch", help="Fetch and print secrets as JSON")
    fetch_parser.add_argument("--project-id", "-p", required=True, help="Project ID")
    fetch_parser.add_argument("--env", "-e", default="dev", help="Environment slug")
    fetch_parser.add_argument("--version", "-v", default=None, dest="version_name", help="Version name (e.g. v1, v2)")

    # ── export ────────────────────────────────────────────────────
    export_parser = sub.add_parser("export", help="Export secrets to .env file")
    export_parser.add_argument("--project-id", "-p", required=True, help="Project ID")
    export_parser.add_argument("--env", "-e", default="dev", help="Environment slug")
    export_parser.add_argument("--version", "-v", default=None, dest="version_name", help="Version name (e.g. v1, v2)")
    export_parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print dotenv text to stdout (no file). Use with: set -a && source <(envvault export ... --stdout) && set +a",
    )
    export_parser.add_argument("--output", "-o", default=".env", help="Output file path (ignored with --stdout)")

    # ── env-config ────────────────────────────────────────────────
    env_config = sub.add_parser("env-config", help="Env config (.env file) commands")
    env_sub = env_config.add_subparsers(dest="env_config_cmd", help="env-config subcommand")

    ec_get = env_sub.add_parser("get", help="Get env config content")
    ec_get.add_argument("--project-id", "-p", required=True, help="Project ID")
    ec_get.add_argument("--env", "-e", default="dev", help="Environment slug")
    ec_get.add_argument("--name", "-n", default=".env", help="Env config name")
    ec_get.add_argument("--version", "-v", default=None, dest="version_name", help="Version name")

    ec_dist = env_sub.add_parser("dist", help="Distribute env config to file")
    ec_dist.add_argument("--project-id", "-p", required=True, help="Project ID")
    ec_dist.add_argument("--env", "-e", default="dev", help="Environment slug")
    ec_dist.add_argument("--name", "-n", default=".env", help="Env config name")
    ec_dist.add_argument(
        "--stdout",
        action="store_true",
        help="Print env config content to stdout (no file)",
    )
    ec_dist.add_argument("--output", "-o", default=".env", help="Output file path (ignored with --stdout)")
    ec_dist.add_argument("--version", "-v", default=None, dest="version_name", help="Version name")

    # ── yaml-config ───────────────────────────────────────────────
    yaml_config = sub.add_parser("yaml-config", help="YAML config commands")
    yaml_sub = yaml_config.add_subparsers(dest="yaml_config_cmd", help="yaml-config subcommand")

    yc_get = yaml_sub.add_parser("get", help="Get YAML config (parsed JSON)")
    yc_get.add_argument("--project-id", "-p", required=True, help="Project ID")
    yc_get.add_argument("--env", "-e", default="dev", help="Environment slug")
    yc_get.add_argument("--name", "-n", default="config.yaml", help="YAML config name")
    yc_get.add_argument("--version", "-v", default=None, dest="version_name", help="Version name")

    yc_dist = yaml_sub.add_parser("dist", help="Distribute YAML config to file")
    yc_dist.add_argument("--project-id", "-p", required=True, help="Project ID")
    yc_dist.add_argument("--env", "-e", default="dev", help="Environment slug")
    yc_dist.add_argument("--name", "-n", default="config.yaml", help="YAML config name")
    yc_dist.add_argument("--output", "-o", default=None, help="Output file path")
    yc_dist.add_argument("--version", "-v", default=None, dest="version_name", help="Version name")

    # ── run ───────────────────────────────────────────────────────
    run_parser = sub.add_parser(
        "run",
        help="Run a command with env vars injected (secrets or a named env config)",
    )
    run_parser.add_argument("--project-id", "-p", required=True, help="Project ID")
    run_parser.add_argument("--env", "-e", default="dev", help="Environment slug")
    run_parser.add_argument("--version", "-v", default=None, dest="version_name", help="Version name (e.g. v1, v2)")
    run_parser.add_argument(
        "--name",
        "-n",
        default=None,
        metavar="ENV_CONFIG",
        help="Named env config to inject (e.g. .env) instead of key-value secrets",
    )
    run_parser.add_argument("cmd", nargs=argparse.REMAINDER, help="Command to run")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.no_verify_ssl and args.ca_bundle:
        parser.error("--no-verify-ssl and --ca-bundle are mutually exclusive")

    ca_from_env = os.environ.get("ENVVAULT_CA_BUNDLE")
    verify_ssl: bool | str = True
    if args.no_verify_ssl:
        verify_ssl = False
    elif args.ca_bundle is not None:
        verify_ssl = args.ca_bundle
    elif ca_from_env:
        verify_ssl = ca_from_env
    else:
        flag = os.environ.get("ENVVAULT_VERIFY_SSL", "").strip().lower()
        if flag in ("0", "false", "no", "off"):
            verify_ssl = False

    if not args.token:
        print("Error: Service token required. Set ENVVAULT_SERVICE_TOKEN or use --token", file=sys.stderr)
        sys.exit(1)
    try:
        client = EnvVaultClient(
            server_url=args.server,
            service_token=args.token,
            verify_ssl=verify_ssl,
        )

        def fetch():
            secrets = client.get_secrets(args.project_id, args.env, version_name=args.version_name)
            print(json.dumps(secrets, indent=2))

        def export():
            if args.stdout:
                sys.stdout.write(
                    client.render_secrets_dotenv(
                        args.project_id, args.env, version_name=args.version_name
                    )
                )
                return
            path = client.export_dotenv(
                args.project_id, args.env, path=args.output, version_name=args.version_name
            )
            print(f"Exported {args.env} secrets to {path}", file=sys.stderr)

        def env_config_cmd():
            if not getattr(args, "env_config_cmd", None):
                env_config.print_help()
                sys.exit(1)
            if args.env_config_cmd == "get":
                config = client.get_env_config(
                    args.project_id, args.env, args.name, version_name=args.version_name
                )
                print(config.get("content", ""))
            elif args.env_config_cmd == "dist":
                if getattr(args, "stdout", False):
                    cfg = client.get_env_config(
                        args.project_id,
                        args.env,
                        args.name,
                        version_name=args.version_name,
                    )
                    content = cfg.get("content", "")
                    sys.stdout.write(content)
                    if content and not content.endswith("\n"):
                        sys.stdout.write("\n")
                    return
                path = client.export_env_config(
                    args.project_id, args.env, name=args.name,
                    path=args.output, version_name=args.version_name,
                )
                print(f"Distributed env config '{args.name}' to {path}", file=sys.stderr)

        def yaml_config_cmd():
            if not getattr(args, "yaml_config_cmd", None):
                yaml_config.print_help()
                sys.exit(1)
            if args.yaml_config_cmd == "get":
                data = client.get_yaml_config_parsed(
                    args.project_id, args.env, args.name, version_name=args.version_name
                )
                print(json.dumps(data, indent=2))
            elif args.yaml_config_cmd == "dist":
                path = client.export_yaml_config(
                    args.project_id, args.env, args.name,
                    path=args.output, version_name=args.version_name,
                )
                print(f"Distributed YAML config '{args.name}' to {path}")

        def run_cmd():
            if not args.cmd:
                print("Error: No command specified", file=sys.stderr)
                sys.exit(1)
            # Remove leading '--' if present
            cmd = args.cmd
            if cmd and cmd[0] == "--":
                cmd = cmd[1:]
            # Inject secrets or parsed env config into env
            if getattr(args, "name", None):
                from envvault.loader import _parse_env_content

                raw = client.get_env_config(
                    args.project_id,
                    args.env,
                    args.name,
                    version_name=args.version_name,
                )
                injected = _parse_env_content(raw.get("content", ""))
            else:
                injected = client.get_secrets(
                    args.project_id, args.env, version_name=args.version_name
                )
            env = os.environ.copy()
            env.update(injected)
            # Execute command
            os.execvpe(cmd[0], cmd, env)

        handlers = {
            "fetch": fetch,
            "export": export,
            "env-config": env_config_cmd,
            "yaml-config": yaml_config_cmd,
            "run": run_cmd,
        }
        handlers[args.command]()
    except EnvVaultError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
