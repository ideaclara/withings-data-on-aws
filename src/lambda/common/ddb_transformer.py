# src/lambda/common/ddb_transformer.py
from decimal import Decimal
from typing import Any, Dict, List

# Metric types mapping per Withings specification
MEASURE_TYPE_MAP: Dict[int, str] = {
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
    130: "afib_result",
    155: "vascular_age",
    226: "bmr",
    227: "metabolic_age"
}

def decode_withings_value(value: int, unit: int) -> Decimal:
    """Calculates actual_value = value * 10^unit into DynamoDB Decimal."""
    return Decimal(str(value)) * (Decimal("10") ** Decimal(str(unit)))

def flatten_measure_group(user_id: str, grp: Dict[str, Any]) -> Dict[str, Any]:
    """Flattens a Withings measuregrp_object into an idempotent DynamoDB record."""
    epoch_timestamp = grp["date"]
    grp_id = grp["grpid"]
    category = grp.get("category", 1)

    item: Dict[str, Any] = {
        "PK": f"USER#{user_id}",
        "SK": f"MEAS#{epoch_timestamp}#GRP#{grp_id}",
        "user_id": str(user_id),
        "grp_id": grp_id,
        "timestamp": epoch_timestamp,
        "created_at": grp.get("created"),
        "modified_at": grp.get("modified"),
        "attrib": grp.get("attrib"),
        "category": category,
        "is_objective": (category == 2),
        "device_id": grp.get("deviceid"),
        "model": grp.get("model"),
        "model_id": grp.get("model_id"),
        "metrics": {}
    }

    for measure in grp.get("measures", []):
        m_type = measure["type"]
        field_name = MEASURE_TYPE_MAP.get(m_type, f"meas_type_{m_type}")
        real_val = decode_withings_value(measure["value"], measure["unit"])
        
        item["metrics"][field_name] = real_val

        # Primary GSI key for fast querying of primary telemetry (e.g., Weight)
        if m_type == 1:
            item["GSI1PK"] = "TYPE#WEIGHT"
            item["GSI1SK"] = f"DATE#{epoch_timestamp}"

    return item