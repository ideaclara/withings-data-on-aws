import json
import os
import time
import urllib.parse
import urllib.request
from decimal import Decimal
import boto3

dynamodb = boto3.resource('dynamodb')

# Official Withings meastype IDs per OpenAPI Specification
TYPE_FIELD_MAP = {
    1: "weight_kg",
    4: "height_m",
    5: "fat_free_mass_kg",
    6: "fat_ratio_pct",
    8: "fat_mass_weight_kg",
    9: "diastolic_blood_pressure_mmhg",
    10: "systolic_blood_pressure_mmhg",
    11: "heart_pulse_bpm",
    12: "temperature_celsius",
    54: "spo2_pct",
    71: "body_temperature_celsius",
    73: "skin_temperature_celsius",
    76: "muscle_mass_kg",
    77: "hydration_kg",
    88: "bone_mass_kg",
    123: "vo2_max_ml_min_kg",
    130: "afib_result",
    155: "vascular_age_yrs",
    168: "extracellular_water_kg",
    169: "intracellular_water_kg",
    170: "visceral_fat_index",
    226: "bmr_kcal",
    227: "metabolic_age_years"
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
            'startdate': int(time.time()) - (86400 * 30)
        }
        data = urllib.parse.urlencode(params).encode('utf-8')
        req = urllib.request.Request(base_url, data=data, headers=headers, method='POST')
        with urllib.request.urlopen(req) as resp:
            res = json.loads(resp.read().decode('utf-8'))

        # Aggregate separate measuregrps by common timestamp
        sessions_by_timestamp = {}

        for grp in res.get('body', {}).get('measuregrps', []):
            timestamp = int(grp['date'])
            grpid = str(grp['grpid'])

            if timestamp not in sessions_by_timestamp:
                sessions_by_timestamp[timestamp] = {
                    'PK': f"USER#{userid}",
                    'SK': f"WITHINGS#MEAS#{timestamp}",
                    'entity_type': 'MEASUREMENT_SESSION',
                    'timestamp': timestamp,
                    'measure_group_ids': set(),
                    'device_model': grp.get('model', 'unknown')
                }

            session = sessions_by_timestamp[timestamp]
            session['measure_group_ids'].add(grpid)

            # Check if this group includes Vascular Age (Type 155)
            types_in_group = [m['type'] for m in grp.get('measures', [])]
            has_vascular_age = (155 in types_in_group)

            for m in grp.get('measures', []):
                m_type = m['type']
                raw_val = m['value']
                unit = m['unit']
                actual_val = Decimal(str(raw_val)) * (Decimal('10') ** Decimal(str(unit)))

                if m_type == 91:  # Pulse Wave Velocity
                    if has_vascular_age:
                        session['pulse_wave_velocity_normalized_ms'] = actual_val
                    else:
                        session['pulse_wave_velocity_raw_ms'] = actual_val
                elif m_type in TYPE_FIELD_MAP:
                    field_name = TYPE_FIELD_MAP[m_type]
                    session[field_name] = actual_val
                else:
                    session[f"type_{m_type}"] = actual_val

        # Persist consolidated flat records
        for timestamp, item in sessions_by_timestamp.items():
            item['measure_group_ids'] = list(item['measure_group_ids'])
            table.put_item(Item=item)
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
            item = {
                'PK': f"USER#{userid}",
                'SK': f"WITHINGS#ACTIVITY#{date_str}",
                'entity_type': 'DAILY_ACTIVITY',
                'date': date_str
            }
            for k, v in act.items():
                if isinstance(v, (int, float)):
                    item[k] = Decimal(str(v))
            table.put_item(Item=item)
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
            item = {
                'PK': f"USER#{userid}",
                'SK': f"WITHINGS#SLEEP#{date_str}",
                'entity_type': 'SLEEP_SUMMARY',
                'date': date_str
            }
            for k, v in s.get('data', {}).items():
                if isinstance(v, (int, float)):
                    item[k] = Decimal(str(v))
            table.put_item(Item=item)
            persisted_count += 1

    return {"endpoint": endpoint, "persisted_items": persisted_count}
