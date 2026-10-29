from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.domain import WORKFLOW_STATE_KEYS, default_profile


def supabase_request(
    method: str,
    supabase_url: str,
    supabase_service_key: str,
    path: str,
    payload: dict | None = None,
) -> object:
    request = Request(
        f"{supabase_url}/rest/v1/{path}",
        method=method,
        headers={
            "apikey": supabase_service_key,
            "Authorization": f"Bearer {supabase_service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation,resolution=merge-duplicates",
        },
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
    )
    with urlopen(request, timeout=10) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else None


def load_workspace(
    user_key: str,
    auth_configured: bool,
    supabase_url: str,
    supabase_service_key: str,
    database_path: Path,
) -> tuple[dict, dict]:
    if not auth_configured:
        return default_profile(), {step: False for step in WORKFLOW_STATE_KEYS}
    if supabase_url and supabase_service_key:
        query = urlencode({"user_key": f"eq.{user_key}", "select": "profile,workflow"})
        rows = supabase_request("GET", supabase_url, supabase_service_key, f"workspaces?{query}")
        if not rows:
            return default_profile(), {step: False for step in WORKFLOW_STATE_KEYS}
        profile_data = rows[0]["profile"]
        workflow_data = rows[0]["workflow"]
        return (
            json.loads(profile_data) if isinstance(profile_data, str) else profile_data,
            json.loads(workflow_data) if isinstance(workflow_data, str) else workflow_data,
        )
    with closing(sqlite3.connect(database_path)) as connection:
        with connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS workspaces (user_key TEXT PRIMARY KEY, profile TEXT NOT NULL, workflow TEXT NOT NULL)"
            )
            row = connection.execute(
                "SELECT profile, workflow FROM workspaces WHERE user_key = ?",
                (user_key,),
            ).fetchone()
    if not row:
        return default_profile(), {step: False for step in WORKFLOW_STATE_KEYS}
    return json.loads(row[0]), json.loads(row[1])


def save_workspace(
    user_key: str,
    profile: dict,
    workflow: dict,
    auth_configured: bool,
    supabase_url: str,
    supabase_service_key: str,
    database_path: Path,
) -> None:
    if not auth_configured:
        return
    payload = {
        "user_key": user_key,
        "profile": profile,
        "workflow": workflow,
    }
    if supabase_url and supabase_service_key:
        supabase_request("POST", supabase_url, supabase_service_key, "workspaces", payload)
        return
    with closing(sqlite3.connect(database_path)) as connection:
        with connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS workspaces (user_key TEXT PRIMARY KEY, profile TEXT NOT NULL, workflow TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO workspaces (user_key, profile, workflow) VALUES (?, ?, ?) "
                "ON CONFLICT(user_key) DO UPDATE SET profile = excluded.profile, workflow = excluded.workflow",
                (user_key, json.dumps(payload["profile"]), json.dumps(payload["workflow"])),
            )
