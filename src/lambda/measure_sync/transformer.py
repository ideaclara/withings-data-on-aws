from decimal import Decimal
from typing import Any, Dict

MEASURE_TYPE_NAMES: Dict[int, str] = {
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
    123: "vo2_max",
}

def decode_withings_val(val: int, unit: int) -> Decimal:
    return Decimal(str(val)) * (Decimal("10") ** Decimal(str(unit)))

def transform_measuregrp(user_id: str, grp: Dict[str, Any]) -> Dict[str, Any]:
    timestamp = grp["date"]
    grp_id = grp["grpid"]
    category = grp.get("category", 1)

    item: Dict[str, Any] = {
        "PK": f"USER#{user_id}",
        "SK": f"WITHINGS#MEAS#{timestamp}#GRP#{grp_id}",
        "entity_type": "MEASUREMENT_GROUP",
        "user_id": str(user_id),
        "grp_id": grp_id,
        "timestamp": timestamp,
        "created_at": grp.get("created"),
        "modified_at": grp.get("modified"),
        "attrib": grp.get("attrib"),
        "category": category,
        "is_objective": (category == 2),
        "device_id": grp.get("deviceid"),
        "model": grp.get("model"),
        "model_id": grp.get("model_id"),
        "metrics": {},
    }

    for m in grp.get("measures", []):
        m_type = m["type"]
        field_name = MEASURE_TYPE_NAMES.get(m_type, f"meastype_{m_type}")
        computed_val = decode_withings_val(m["value"], m["unit"])
        item["metrics"][field_name] = computed_val

        if m_type == 1:
            item["GSI1PK"] = "METRIC#WEIGHT"
            item["GSI1SK"] = f"DATE#{timestamp}"

    return item
