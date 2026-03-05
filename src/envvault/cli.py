"""
EnvVault CLI — Simple command-line interface for managing secrets.

Usage:
    envvault fetch --project-id <id> --env <env>
    envvault export --project-id <id> --env <env> --output .env
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

        if args.command == "fetch":
            secrets = client.get_secrets(args.project_id, args.env, version_name=args.version_name)
            print(json.dumps(secrets, indent=2))

        elif args.command == "export":
            path = client.export_dotenv(args.project_id, args.env, path=args.output, version_name=args.version_name)
            print(f"Exported {args.env} secrets to {path}")

        elif args.command == "run":
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

    except EnvVaultError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
