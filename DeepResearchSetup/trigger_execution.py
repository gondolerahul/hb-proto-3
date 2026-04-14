#!/usr/bin/env python3
"""
Trigger a Deep Research execution.

Reads entity_ids.json (created by create_entities.py) and triggers
the top-level process with the specified research topic.

Usage:
    python trigger_execution.py --token "$AUTH_TOKEN"
    python trigger_execution.py --token "$AUTH_TOKEN" --topic "Quantum computing in 2026"
"""

import argparse
import json
import os
import sys

try:
    import requests
except ImportError:
    print("Error: 'requests' library is required. Install with: pip install requests")
    sys.exit(1)


DEFAULT_BASE_URL = os.environ.get(
    "API_BASE_URL", "https://gateway.hirebuddha.com/api/v1"
)
DEFAULT_TOPIC = (
    "Impact of generative AI on the creative industries: "
    "economics, employment, and intellectual property"
)


def main():
    parser = argparse.ArgumentParser(description="Trigger Deep Research execution")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL")
    parser.add_argument("--token", default=os.environ.get("AUTH_TOKEN", ""), help="JWT auth token")
    parser.add_argument("--topic", default=DEFAULT_TOPIC, help="Research topic")
    parser.add_argument("--entity-ids", default=None, help="Path to entity_ids.json")
    args = parser.parse_args()

    if not args.token:
        print("❌ Error: Auth token is required. Set AUTH_TOKEN or pass --token")
        sys.exit(1)

    # Load entity IDs
    ids_path = args.entity_ids or os.path.join(os.path.dirname(__file__), "entity_ids.json")
    if not os.path.exists(ids_path):
        print(f"❌ Error: entity_ids.json not found at {ids_path}")
        print("   Run create_entities.py first.")
        sys.exit(1)

    with open(ids_path) as f:
        entity_ids = json.load(f)

    process_id = entity_ids.get("deep_research_process")
    if not process_id:
        print("❌ Error: 'deep_research_process' not found in entity_ids.json")
        sys.exit(1)

    # Trigger execution
    url = f"{args.base_url.rstrip('/')}/ai/execute"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {args.token}",
    }
    payload = {
        "entity_id": process_id,
        "input_data": {"input": args.topic}
    }

    print(f"🔬 Deep Research — Triggering Execution")
    print(f"   Topic: {args.topic}")
    print(f"   Process ID: {process_id}")
    print(f"   API: {url}")
    print()

    resp = requests.post(url, headers=headers, json=payload)
    if resp.status_code not in (200, 201):
        print(f"❌ Failed: {resp.status_code} — {resp.text[:500]}")
        sys.exit(1)

    data = resp.json()
    print(f"✅ Execution created!")
    print(f"   Execution ID: {data['id']}")
    print(f"   Status: {data['status']}")
    print(f"\n   Monitor at: {args.base_url}/ai/executions/{data['id']}")
    print(f"\n   Stream: {args.base_url}/ai/executions/{data['id']}/stream")

    # Save execution ID
    exec_path = os.path.join(os.path.dirname(__file__), "last_execution.json")
    with open(exec_path, "w") as f:
        json.dump({"execution_id": data["id"], "topic": args.topic, "process_id": process_id}, f, indent=2)
    print(f"\n   Execution info saved to: {exec_path}")


if __name__ == "__main__":
    main()
