import json
import os
import time
import urllib.parse
import urllib.request
from decimal import Decimal
import boto3

dynamodb = boto3.resource('dynamodb')

MEAS_TYPE_MAP = {
    1: "weight_kg",
    4: "height_m",
    5: "fat_free_mass_kg",
    6: "fat_ratio_pct",
    8: "fat_mass_weight_kg",
    9: "diastolic_blood_pressure_mmhg",
    10: "systolic_blood_pressure_mmhg",
    11: "heart_pulse_bpm",
    76: "muscle_mass_kg",
    77: "hydration_kg",
    88: "bone_mass_kg",
    91: "pulse_wave_velocity_ms"
}

def handler(event, context):
    table = dynamodb.Table(os.environ['TABLE_NAME'])
    endpoint = event['endpoint']
    endpoint_config = event['endpoint_config']
    access_token = event['access_token']
    userid = event['userid']

    base_url = f"https://wbsapi.withings.net{endpoint_config['path']}"
    headers = {'Authorization': f"Bearer {access_token}"}
    persisted_count = 0

    if endpoint == 'measures':
        params = {
            'action': endpoint_config['action'],
            'category': endpoint_config.get('category', 1),
            'startdate': int(time.time()) - (86400 * 7)
        }
        data = urllib.parse.urlencode(params).encode('utf-8')
        req = urllib.request.Request(base_url, data=data, headers=headers, method='POST')
        with urllib.request.urlopen(req) as resp:
            res = json.loads(resp.read().decode('utf-8'))

        for grp in res.get('body', {}).get('measuregrps', []):
            grpid = grp['grpid']
            timestamp = grp['date']
            pk = f"USER#{userid}"
            sk = f"WITHINGS#MEAS#{timestamp}#{grpid}"
            
            metrics = {}
            for m in grp.get('measures', []):
                metric_name = MEAS_TYPE_MAP.get(m['type'], f"type_{m['type']}")
                raw_val = m['value']
                unit = m['unit']
                actual_val = Decimal(str(raw_val)) * (Decimal('10') ** Decimal(str(unit)))
                metrics[metric_name] = actual_val

            table.put_item(Item={
                'PK': pk,
                'SK': sk,
                'entity_type': 'MEASUREMENT_GROUP',
                'grpid': grpid,
                'timestamp': timestamp,
                'metrics': metrics
            })
            persisted_count += 1

    elif endpoint == 'activity':
        today = time.strftime('%Y-%m-%d')
        params = {
            'action': endpoint_config['action'],
            'startdateymd': today,
            'enddateymd': today,
            'data_fields': endpoint_config.get('data_fields', 'steps,calories')
        }
        data = urllib.parse.urlencode(params).encode('utf-8')
        req = urllib.request.Request(base_url, data=data, headers=headers, method='POST')
        with urllib.request.urlopen(req) as resp:
            res = json.loads(resp.read().decode('utf-8'))

        for act in res.get('body', {}).get('activities', []):
            date_str = act['date']
            table.put_item(Item={
                'PK': f"USER#{userid}",
                'SK': f"WITHINGS#ACTIVITY#{date_str}",
                'entity_type': 'DAILY_ACTIVITY',
                'date': date_str,
                'metrics': {k: Decimal(str(v)) for k, v in act.items() if isinstance(v, (int, float))}
            })
            persisted_count += 1

    elif endpoint == 'sleep':
        today = time.strftime('%Y-%m-%d')
        params = {
            'action': endpoint_config['action'],
            'startdateymd': today,
            'enddateymd': today,
            'data_fields': endpoint_config.get('data_fields', 'total_sleep_time,sleep_score')
        }
        data = urllib.parse.urlencode(params).encode('utf-8')
        req = urllib.request.Request(base_url, data=data, headers=headers, method='POST')
        with urllib.request.urlopen(req) as resp:
            res = json.loads(resp.read().decode('utf-8'))

        for s in res.get('body', {}).get('series', []):
            date_str = s['date']
            table.put_item(Item={
                'PK': f"USER#{userid}",
                'SK': f"WITHINGS#SLEEP#{date_str}",
                'entity_type': 'SLEEP_SUMMARY',
                'date': date_str,
                'metrics': {k: Decimal(str(v)) for k, v in s.get('data', {}).items() if isinstance(v, (int, float))}
            })
            persisted_count += 1

    return {"endpoint": endpoint, "persisted_items": persisted_count}
