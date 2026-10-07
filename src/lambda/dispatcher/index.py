import json
import os
import time
import boto3

APP_NAME = os.environ["APPCONFIG_APP"]
ENV_NAME = os.environ["APPCONFIG_ENV"]
CONF_NAME = os.environ["APPCONFIG_CONF"]
TABLE_NAME = os.environ["TABLE_NAME"]
STATE_MACHINE_ARN = os.environ["STATE_MACHINE_ARN"]

appconfig_data = boto3.client("appconfigdata")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)
sfn_client = boto3.client("stepfunctions")

def get_appconfig() -> dict:
    """Retrieves active configuration document via AppConfigData session."""
    session = appconfig_data.start_configuration_session(
        ApplicationIdentifier=APP_NAME,
        EnvironmentIdentifier=ENV_NAME,
        ConfigurationProfileIdentifier=CONF_NAME,
        RequiredMinimumPollIntervalInSeconds=60,
    )
    token = session["InitialConfigurationToken"]
    response = appconfig_data.get_latest_configuration(
        ConfigurationToken=token
    )
    raw_payload = response["Configuration"].read().decode("utf-8")
    return json.loads(raw_payload)

def handler(event, context):
    config = get_appconfig()
    now = int(time.time())
    dispatched = []

    for provider, pdata in config.get("providers", {}).items():
        endpoints = pdata.get("endpoints", {})
        secret_name = pdata.get("secret_name")
        refresh_url = pdata.get("token_refresh_url")

        for ep_name, ep_conf in endpoints.items():
            if not ep_conf.get("enabled", False):
                continue

            cadence_seconds = ep_conf.get("cadence_minutes", 60) * 60
            sk_key = f"STATE#{provider}#{ep_name}"

            # Query high-water mark control item in DynamoDB
            res = table.get_item(
                Key={"PK": "CONFIG#INGESTION", "SK": sk_key}
            )
            last_run = res.get("Item", {}).get("last_executed_at", 0)

            # Evaluate cadence interval
            if (now - last_run) >= cadence_seconds:
                payload = {
                    "provider": provider,
                    "endpoint": ep_name,
                    "secret_name": secret_name,
                    "refresh_url": refresh_url,
                    "endpoint_config": ep_conf,
                    "dispatched_at": now
                }

                exec_name = f"{provider}-{ep_name}-{now}"
                sfn_client.start_execution(
                    stateMachineArn=STATE_MACHINE_ARN,
                    name=exec_name,
                    input=json.dumps(payload)
                )

                # Atomically update high-water mark
                table.put_item(
                    Item={
                        "PK": "CONFIG#INGESTION",
                        "SK": sk_key,
                        "last_executed_at": now,
                        "status": "DISPATCHED"
                    }
                )
                dispatched.append(f"{provider}:{ep_name}")

    return {
        "statusCode": 200,
        "dispatched": dispatched
    }
