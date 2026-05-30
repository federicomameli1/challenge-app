#!/usr/bin/env python3
"""Seed the local Verdict Health page from the mgmt ArgoCD cluster.

Reads ArgoCD Application resources via kubectl (uses the current kubeconfig)
and POSTs each one to the local Verdict webhook endpoint.

Usage:
    python3 scripts/seed_health_local.py [--context mgmt] [--verdict http://localhost:8001]
"""
import argparse
import json
import subprocess
import sys
import urllib.request


def fetch_apps(context: str) -> list:
    cmd = ["kubectl", "--context", context, "-n", "argocd", "get", "applications", "-o", "json"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"kubectl failed: {result.stderr.strip()}")
    return json.loads(result.stdout).get("items", [])


def post_app(verdict_url: str, app: dict) -> None:
    meta = app.get("metadata") or {}
    spec = app.get("spec") or {}
    status = app.get("status") or {}
    payload = json.dumps({
        "app": meta.get("name", ""),
        "cluster": (spec.get("destination") or {}).get("name", ""),
        "namespace": (spec.get("destination") or {}).get("namespace", ""),
        "sync_status": (status.get("sync") or {}).get("status", "Unknown"),
        "health_status": (status.get("health") or {}).get("status", "Unknown"),
        "operation_phase": (status.get("operationState") or {}).get("phase", ""),
        "revision": (status.get("sync") or {}).get("revision", ""),
    }).encode()
    req = urllib.request.Request(
        f"{verdict_url}/webhooks/argocd",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", default="mgmt", help="kubectl context (default: mgmt)")
    parser.add_argument("--verdict", default="http://localhost:8001", help="Verdict backend URL")
    args = parser.parse_args()

    apps = fetch_apps(args.context)
    if not apps:
        print("No ArgoCD applications found.")
        return

    for app in apps:
        name = (app.get("metadata") or {}).get("name", "?")
        try:
            post_app(args.verdict, app)
            print(f"OK  {name}")
        except Exception as exc:
            print(f"ERR {name}: {exc}")


if __name__ == "__main__":
    main()
