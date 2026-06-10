#!/usr/bin/env python3
"""
MentorForge WebSocket test client — TASK-004 acceptance smoke test.

Usage
-----
1. Deploy the stack and note the WssUrl output.
2. Set the demo user password (see README.md post-deploy steps).
3. Run:

    python scripts/ws_test_client.py \
        --wss-url  wss://<api-id>.execute-api.us-east-1.amazonaws.com/demo \
        --pool-id  us-east-1_XXXXXXXX \
        --client-id XXXXXXXXXXXXXXXXXXXXXXXXXX \
        --username  demo@northstar-consulting.demo \
        --password  '<your-demo-password>'

   Or, if you already have a JWT:

    python scripts/ws_test_client.py \
        --wss-url wss://... \
        --token   <id-token>

What it does
------------
- Authenticates via USER_PASSWORD_AUTH (Cognito) to get an ID token.
- Connects to the WebSocket API with ?token=<jwt>.
- Sends a "sendMessage" turn (EX Story 1 opener: Priya Nair, day 1).
- Prints every inbound signal as it arrives.
- When awaiting_confirmation fires, sends a "confirm" action.
- Closes after the final "end_of_turn" or after 60 seconds.

Requirements: pip install websockets boto3
"""

import argparse
import asyncio
import json
import sys
import time

try:
    import boto3
    import websockets
except ImportError:
    print("Missing deps — run: pip install websockets boto3", file=sys.stderr)
    sys.exit(1)


def get_jwt(pool_id: str, client_id: str, username: str, password: str) -> str:
    """Authenticate via USER_PASSWORD_AUTH and return the ID token."""
    cognito = boto3.client("cognito-idp", region_name=pool_id.split("_")[0])
    resp = cognito.initiate_auth(
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": username, "PASSWORD": password},
        ClientId=client_id,
    )
    if resp.get("ChallengeName") == "NEW_PASSWORD_REQUIRED":
        print(
            "ERROR: user is in FORCE_CHANGE_PASSWORD state.\n"
            "Run:  aws cognito-idp admin-set-user-password "
            "--user-pool-id <pool> --username <user> --password '<your-demo-password>' --permanent",
            file=sys.stderr,
        )
        sys.exit(1)
    return resp["AuthenticationResult"]["IdToken"]


async def run(wss_url: str, token: str) -> None:
    url = f"{wss_url}?token={token}"
    print(f"[client] connecting → {wss_url}")

    async with websockets.connect(url) as ws:
        print("[client] connected\n")

        # Send the opening turn — EX Story 1 opener (Priya Nair, day 1 at Northstar)
        turn = {
            "action": "sendMessage",
            "payload": {
                "message": (
                    "Hi! I'm Priya Nair, starting today at Northstar Consulting on the Atlas-Health engagement. "
                    "Can you help me figure out who I should meet first and what I should read to get up to speed?"
                )
            },
        }
        await ws.send(json.dumps(turn))
        print(f"[client → server] {json.dumps(turn, indent=2)}\n")

        deadline = time.time() + 180  # 3 min — agent turn can take >29s (API GW frame timeout)
        pending_action_id: str | None = None

        async for raw in ws:
            signal = json.loads(raw)
            sig_type = signal.get("type", "unknown")
            print(f"[server → client] {sig_type}")
            print(json.dumps(signal, indent=2))
            print()

            if sig_type == "awaiting_confirmation":
                pending_action_id = signal.get("payload", {}).get("action_id")
                confirm_msg = {
                    "action": "confirm",
                    "payload": {"action_id": pending_action_id},
                }
                await ws.send(json.dumps(confirm_msg))
                print(f"[client → server] confirm action_id={pending_action_id}\n")

            elif sig_type in ("done", "error"):
                print(f"[client] session ended ({sig_type}) — closing")
                break

            if time.time() > deadline:
                print("[client] 60-second timeout — closing")
                break

    print("[client] disconnected")


def main() -> None:
    p = argparse.ArgumentParser(description="MentorForge WS smoke test")
    p.add_argument("--wss-url",   required=True,  help="wss:// URL from WssUrl stack output")
    p.add_argument("--token",     default=None,   help="pre-fetched ID token (skip auth)")
    p.add_argument("--pool-id",   default=None,   help="Cognito user pool ID (e.g. us-east-1_XXX)")
    p.add_argument("--client-id", default=None,   help="Cognito app client ID")
    p.add_argument("--username",  default=None,   help="demo user email")
    p.add_argument("--password",  default=None,   help="demo user password")
    args = p.parse_args()

    if args.token:
        token = args.token
    else:
        missing = [f for f in ("pool_id", "client_id", "username", "password") if not getattr(args, f)]
        if missing:
            p.error(f"provide --token OR all of --pool-id / --client-id / --username / --password (missing: {missing})")
        print("[client] authenticating with Cognito USER_PASSWORD_AUTH …")
        token = get_jwt(args.pool_id, args.client_id, args.username, args.password)
        print("[client] got ID token\n")

    asyncio.run(run(args.wss_url, token))


if __name__ == "__main__":
    main()
