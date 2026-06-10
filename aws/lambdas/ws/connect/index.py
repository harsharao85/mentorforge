"""$connect Lambda — registers connectionId → learnerId in DynamoDB."""
import os
import time
from datetime import datetime, timezone

import boto3

TABLE = os.environ["CONNECTIONS_TABLE"]
_db   = boto3.resource("dynamodb")
_tbl  = _db.Table(TABLE)

TTL_SECONDS = 4 * 60 * 60  # 4-hour idle TTL — stale connections auto-expire


def handler(event, context):
    conn_id    = event["requestContext"]["connectionId"]
    learner_id = (event["requestContext"].get("authorizer") or {}).get("learnerId", "unknown")
    now        = datetime.now(timezone.utc).isoformat()

    _tbl.put_item(Item={
        "connectionId":     conn_id,
        "learnerId":        learner_id,
        "connected_at":     now,
        "turn_count":       0,
        "turn_window_start": now,
        "ttl":              int(time.time()) + TTL_SECONDS,
    })

    return {"statusCode": 200}
