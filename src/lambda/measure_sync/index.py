import json
import os
import urllib.parse
import urllib.request
import boto3
from transformer import transform_measuregrp

TABLE_NAME = os.environ["TABLE_NAME"]
MEASURE_URL = "https://wbsapi.withings.net/measure"
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

def handler(event, context):
    access_token = event["access_token"]
    user_id = event["userid"]
    last_update = event.get("lastupdate", 0)

    params = {
        "action": "getmeas",
        "category": 1,
    }
    if last_update and int(last_update) > 0:
        params["lastupdate"] = int(last_update)

    full_url = f"{MEASURE_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        full_url,
        headers={"Authorization": f"Bearer {access_token}"},
        method="POST",
    )

    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        if body.get("status") != 0:
            raise RuntimeError(f"Withings getmeas returned non-zero status: {body}")

    measure_groups = body.get("body", {}).get("measuregrps", [])
    records_saved = 0

    with table.batch_writer() as batch:
        for grp in measure_groups:
            item = transform_measuregrp(user_id, grp)
            batch.put_item(Item=item)
            records_saved += 1

    return {
        "statusCode": 200,
        "measuregrps_synced": records_saved,
        "updatetime": body.get("body", {}).get("updatetime"),
    }
