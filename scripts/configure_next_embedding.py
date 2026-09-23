"""Configure local Next.js embedding via the public Superset API. Run with --apply.

Uses the existing instance admin only for provisioning. Never prints credentials.
"""
import argparse
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import urllib.request
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8090"
ORIGIN = "http://127.0.0.1:3002"
MAPPING = {"OVERVIEW": 1, "ATTENDANCE": 2, "DEPARTMENTS": 3, "LATENESS": 4}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        print("Will configure 4 embedded dashboards for localhost:3002, a token-only service account, and DashboardGuest read permissions. Use --apply.")
        return
    cfg = dotenv_values(ROOT / ".env.dashboard")
    env_path = ROOT / "attendance-dashboard/.env.local"
    env = dict(dotenv_values(env_path)) if env_path.exists() else {}
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    token = None
    csrf = None

    def request(path, data=None, method=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        if csrf:
            headers["X-CSRFToken"] = csrf
        req = urllib.request.Request(BASE + path, data=json.dumps(data).encode() if data is not None else None, headers=headers, method=method)
        with opener.open(req, timeout=30) as response:
            return json.load(response)

    token = request("/api/v1/security/login", {"username": cfg["SUPERSET_ADMIN_USERNAME"], "password": cfg["SUPERSET_ADMIN_PASSWORD"], "provider": "db", "refresh": False})["access_token"]
    csrf = request("/api/v1/security/csrf_token/")["result"]
    roles = request("/api/v1/security/roles/?q=(page_size:100)")["result"]
    role_by_name = {r["name"]: r["id"] for r in roles}
    pairs = []
    page = 0
    while True:
        batch = request(f"/api/v1/security/permissions-resources/?q=(page_size:100,page:{page})")
        pairs.extend(batch["result"])
        if len(pairs) >= batch["count"]:
            break
        page += 1
    lookup = {(p["permission"]["name"], p["view_menu"]["name"]): p["id"] for p in pairs}
    service_name = "NextDashboardTokenIssuer"
    if service_name not in role_by_name:
        role_by_name[service_name] = request("/api/v1/security/roles/", {"name": service_name})["id"]
    request(f"/api/v1/security/roles/{role_by_name[service_name]}/permissions", {"permission_view_menu_ids": [lookup[(name, "SecurityRestApi")] for name in ("can_grant_guest_token", "can_read")]})
    guest_permissions = [("can_read", name) for name in ("Dashboard", "Chart", "Dataset", "CurrentUserRestApi", "EmbeddedDashboard")]
    guest_permissions += [(name, "Superset") for name in ("can_dashboard", "can_explore_json")]
    guest_permissions += [("can_time_range", "Api")]
    guest_ids = [lookup[p] for p in guest_permissions if p in lookup]
    request(f"/api/v1/security/roles/{role_by_name['DashboardGuest']}/permissions", {"permission_view_menu_ids": guest_ids})
    username = "next_dashboard_embed"
    users = request("/api/v1/security/users/?q=(page_size:100)")["result"]
    existing = next((u for u in users if u["username"] == username), None)
    password = env.get("SUPERSET_SERVICE_PASSWORD")
    if existing and not password:
        raise RuntimeError("Service account exists but local secret is missing; restore .env.local rather than rotating it.")
    if not existing:
        password = secrets.token_urlsafe(36) + "aA1!"
        # Persist the secret before account creation so interrupted runs can recover.
        env.update(SUPERSET_SERVICE_USERNAME=username, SUPERSET_SERVICE_PASSWORD=password)
        save_env(env_path, env)
        request("/api/v1/security/users/", {"username": username, "first_name": "Next", "last_name": "Embedding", "email": "next-dashboard@localhost", "active": True, "password": password, "roles": [role_by_name[service_name]]})
    for key, dashboard_id in MAPPING.items():
        embedded = request(f"/api/v1/dashboard/{dashboard_id}/embedded", {"allowed_domains": [ORIGIN]})["result"]
        env[f"SUPERSET_{key}_ID"] = embedded["uuid"]
        print(f"{key}: embedded dashboard {dashboard_id} configured")
    env.update(APP_ORIGIN=ORIGIN, DASHBOARD_LOCAL_PREVIEW="true", SUPERSET_URL=BASE, SUPERSET_INTERNAL_URL=BASE, SUPERSET_SERVICE_USERNAME=username, SUPERSET_SERVICE_PASSWORD=password)
    save_env(env_path, env)
    print("Local embedding configuration saved to .env.local (mode 600). Production remains disabled.")


def save_env(path, values):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as stream:
        for key, value in values.items():
            if value is not None:
                stream.write(f"{key}={json.dumps(value)}\n")


if __name__ == "__main__":
    main()
