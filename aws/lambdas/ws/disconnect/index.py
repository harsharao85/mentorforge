"""$disconnect Lambda — removes connection record from DynamoDB."""
import os

import boto3

TABLE = os.environ["CONNECTIONS_TABLE"]
_db   = boto3.resource("dynamodb")
_tbl  = _db.Table(TABLE)


def handler(event, context):
    conn_id = event["requestContext"]["connectionId"]
    _tbl.delete_item(Key={"connectionId": conn_id})
    return {"statusCode": 200}
