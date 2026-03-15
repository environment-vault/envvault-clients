"""
EnvVault CLI — Simple command-line interface for managing secrets.
env configs (.env files), and YAML configs.

Usage:
    envvault fetch --project-id <id> --env <env>
    envvault export --project-id <id> --env <env> --output .env
    envvault env-config get|dist --project-id <id> --env <env> --name .env
    envvault yaml-config get|dist --project-id <id> --env <env> --name config.yaml
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
    export_parser.add_argument("--output", "-o", default=".env", help="Output file path")

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
    ec_dist.add_argument("--output", "-o", default=".env", help="Output file path")
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
    run_parser = sub.add_parser("run", help="Run a command with secrets injected as env vars")
    run_parser.add_argument("--project-id", "-p", required=True, help="Project ID")
    run_parser.add_argument("--env", "-e", default="dev", help="Environment slug")
    run_parser.add_argument("--version", "-v", default=None, dest="version_name", help="Version name (e.g. v1, v2)")
    run_parser.add_argument("cmd", nargs=argparse.REMAINDER, help="Command to run")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if not args.token:
        print("Error: Service token required. Set ENVVAULT_SERVICE_TOKEN or use --token", file=sys.stderr)
        sys.exit(1)

    try:
        client = EnvVaultClient(server_url=args.server, service_token=args.token)

        def fetch():
            secrets = client.get_secrets(args.project_id, args.env, version_name=args.version_name)
            print(json.dumps(secrets, indent=2))

        def export():
            path = client.export_dotenv(args.project_id, args.env, path=args.output, version_name=args.version_name)
            print(f"Exported {args.env} secrets to {path}")

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
                path = client.export_env_config(
                    args.project_id, args.env, name=args.name,
                    path=args.output, version_name=args.version_name,
                )
                print(f"Distributed env config '{args.name}' to {path}")

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
            # Inject secrets into env
            secrets = client.get_secrets(args.project_id, args.env, version_name=args.version_name)
            env = os.environ.copy()
            env.update(secrets)
            # Execute command
            os.execvpe(cmd[0], cmd, env)

        command_map = {
            "fetch": fetch(),
            "export": export(),
            "env-config": env_config_cmd(),
            "yaml-config": yaml_config_cmd(),
            "run": run_cmd(),
        }
        command_map.get(args.command)
    except EnvVaultError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
