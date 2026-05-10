#!/usr/bin/env python3
"""
Trigger a Deep Research execution against the local backend.

Reads entity_ids.json (created by create_fresh.py) and triggers
the top-level process with the specified research topic.

Usage:
    python trigger_execution.py
    python trigger_execution.py --topic "Quantum computing in 2026"
"""

import json, os, sys, time
from datetime import datetime, timedelta, timezone

try:
    import requests
except ImportError:
    print("Error: 'requests' library is required. Install with: pip install requests")
    sys.exit(1)

try:
    from jose import jwt
except ImportError:
    print("Error: 'python-jose' library is required. Install with: pip install python-jose[cryptography]")
    sys.exit(1)

BASE_URL = "http://localhost:8000/api/v1"
SECRET_KEY = "dev_secret_key_change_in_production"

token_data = {
    "sub": "admin@hirebuddha.com",
    "company_id": "699098ce-a31c-42ef-b13b-2780c7decb9d",
    "exp": datetime.now(timezone.utc) + timedelta(hours=24),
}
TOKEN = jwt.encode(token_data, SECRET_KEY, algorithm="HS256")

HEADERS = {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"}

DEFAULT_TOPIC = (
    "Impact of generative AI on the creative industries: "
    "economics, employment, and intellectual property"
)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Trigger Deep Research execution")
    parser.add_argument("--topic", default=DEFAULT_TOPIC, help="Research topic")
    parser.add_argument("--entity-ids", default=None, help="Path to entity_ids.json")
    args = parser.parse_args()

    # Load entity IDs
    ids_path = args.entity_ids or os.path.join(os.path.dirname(__file__), "entity_ids.json")
    if not os.path.exists(ids_path):
        print(f"❌ Error: entity_ids.json not found at {ids_path}")
        print("   Run create_fresh.py first.")
        sys.exit(1)

    with open(ids_path) as f:
        entity_ids = json.load(f)

    process_id = entity_ids.get("deep_research_process")
    if not process_id:
        print("❌ Error: 'deep_research_process' not found in entity_ids.json")
        sys.exit(1)

    # Trigger execution
    url = f"{BASE_URL}/ai/execute"
    payload = {
        "entity_id": process_id,
        "input_data": {"input": args.topic}
    }

    print(f"🔬 Deep Research — Triggering Execution")
    print(f"   Topic: {args.topic}")
    print(f"   Process ID: {process_id}")
    print(f"   API: {url}")
    print()

    resp = requests.post(url, headers=HEADERS, json=payload)
    if resp.status_code not in (200, 201):
        print(f"❌ Failed: {resp.status_code} — {resp.text[:500]}")
        sys.exit(1)

    data = resp.json()
    print(f"✅ Execution created!")
    print(f"   Execution ID: {data['id']}")
    print(f"   Status: {data['status']}")
    print(f"\n   Monitor at: {BASE_URL}/ai/executions/{data['id']}")

    # Save execution ID
    exec_path = os.path.join(os.path.dirname(__file__), "last_execution.json")
    with open(exec_path, "w") as f:
        json.dump({"execution_id": data["id"], "topic": args.topic, "process_id": process_id}, f, indent=2)
    print(f"\n   Execution info saved to: {exec_path}")


if __name__ == "__main__":
    main()
