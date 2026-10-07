import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import boto3

TABLE_NAME = os.environ["TABLE_NAME"]
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

MEASURE_TYPE_NAMES = {
    1: "weight_kg",
    4: "height_m",
    5: "fat_free_mass_kg",
    6: "fat_ratio_pct",
    8: "fat_mass_weight_kg",
    9: "diastolic_blood_pressure_mmhg",
    10: "systolic_blood_pressure_mmhg",
    11: "heart_pulse_bpm",
    12: "temperature_c",
    54: "spo2_pct",
    71: "body_temperature_c",
    73: "skin_temperature_c",
    76: "muscle_mass_kg",
    77: "hydration_kg",
    88: "bone_mass_kg",
    91: "pulse_wave_velocity_ms",
    123: "vo2_max"
}

def decode_val(val: int, unit: int) -> Decimal:
    return Decimal(str(val)) * (Decimal("10") ** Decimal(str(unit)))

def sync_measures(user_id: str, access_token: str, conf: dict) -> int:
    params = {"action": conf.get("action", "getmeas"), "category": conf.get("category", 1)}
    url = f"{conf['url']}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"}, method="POST")
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    
    saved = 0
    with table.batch_writer() as batch:
        for grp in body.get("body", {}).get("measuregrps", []):
            ts = grp["date"]
            item = {
                "PK": f"USER#{user_id}",
                "SK": f"WITHINGS#MEAS#{ts}#GRP#{grp['grpid']}",
                "entity_type": "MEASUREMENT_GROUP",
                "timestamp": ts,
                "category": grp.get("category", 1),
                "metrics": {}
            }
            for m in grp.get("measures", []):
                m_type = m["type"]
                fname = MEASURE_TYPE_NAMES.get(m_type, f"type_{m_type}")
                item["metrics"][fname] = decode_val(m["value"], m["unit"])
                if m_type == 1:
                    item["GSI1PK"] = "METRIC#WEIGHT"
                    item["GSI1SK"] = f"DATE#{ts}"
            batch.put_item(Item=item)
            saved += 1
    return saved

def sync_activity(user_id: str, access_token: str, conf: dict) -> int:
    today = datetime.now(timezone.utc).date()
    start_date = (today - timedelta(days=conf.get("lookback_days", 3))).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")

    params = {
        "action": conf.get("action", "getactivity"),
        "startdateymd": start_date,
        "enddateymd": end_date,
        "data_fields": conf.get("data_fields", "steps,distance,calories")
    }
    url = f"{conf['url']}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"}, method="POST")
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    saved = 0
    with table.batch_writer() as batch:
        for act in body.get("body", {}).get("activities", []):
            d_str = act["date"]
            item = {
                "PK": f"USER#{user_id}",
                "SK": f"WITHINGS#ACTIVITY#{d_str}",
                "entity_type": "DAILY_ACTIVITY",
                "date": d_str,
                "metrics": {k: Decimal(str(v)) for k, v in act.items() if isinstance(v, (int, float)) and v is not None},
                "GSI1PK": "METRIC#ACTIVITY",
                "GSI1SK": f"DATE#{d_str}"
            }
            batch.put_item(Item=item)
            saved += 1
    return saved

def sync_sleep(user_id: str, access_token: str, conf: dict) -> int:
    today = datetime.now(timezone.utc).date()
    start_date = (today - timedelta(days=conf.get("lookback_days", 7))).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")

    params = {
        "action": conf.get("action", "getsummary"),
        "startdateymd": start_date,
        "enddateymd": end_date,
        "data_fields": conf.get("data_fields", "total_timeinbed,total_sleep_time,sleep_score")
    }
    url = f"{conf['url']}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"}, method="POST")
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    saved = 0
    with table.batch_writer() as batch:
        for s in body.get("body", {}).get("series", []):
            ts = s["startdate"]
            item = {
                "PK": f"USER#{user_id}",
                "SK": f"WITHINGS#SLEEP#{ts}#ID#{s['id']}",
                "entity_type": "SLEEP_SUMMARY",
                "date": s["date"],
                "metrics": {k: Decimal(str(v)) for k, v in s.get("data", {}).items() if isinstance(v, (int, float)) and v is not None},
                "GSI1PK": "METRIC#SLEEP",
                "GSI1SK": f"DATE#{ts}"
            }
            batch.put_item(Item=item)
            saved += 1
    return saved

def handler(event, context):
    ep = event["endpoint"]
    token = event["access_token"]
    uid = event["userid"]
    conf = event["endpoint_config"]

    if ep == "measures":
        count = sync_measures(uid, token, conf)
    elif ep == "activity":
        count = sync_activity(uid, token, conf)
    elif ep == "sleep":
        count = sync_sleep(uid, token, conf)
    else:
        raise ValueError(f"Unsupported endpoint: {ep}")

    return {"statusCode": 200, "synced_records": count}
