import json
import os
import time
import boto3

appconfig_client = boto3.client('appconfigdata')
ddb_client = boto3.client('dynamodb')
sfn_client = boto3.client('stepfunctions')

def handler(event, context):
    app = os.environ['APPCONFIG_APP']
    env = os.environ['APPCONFIG_ENV']
    conf = os.environ['APPCONFIG_CONF']
    table_name = os.environ['TABLE_NAME']
    state_machine_arn = os.environ['STATE_MACHINE_ARN']

    session_resp = appconfig_client.start_configuration_session(
        ApplicationIdentifier=app,
        EnvironmentIdentifier=env,
        ConfigurationProfileIdentifier=conf
    )
    config_resp = appconfig_client.get_latest_configuration(
        ConfigurationToken=session_resp['InitialConfigurationToken']
    )
    config = json.loads(config_resp['Configuration'].read().decode('utf-8'))

    current_time = int(time.time())
    dispatched = []

    for provider, provider_data in config.get('providers', {}).items():
        secret_name = provider_data['secret_name']
        for endpoint_key, endpoint_cfg in provider_data.get('endpoints', {}).items():
            cadence_sec = endpoint_cfg.get('cadence_minutes', 60) * 60
            pk = "CONFIG#INGESTION"
            sk = f"CHECKPOINT#{provider.upper()}#{endpoint_key.upper()}"

            chk_resp = ddb_client.get_item(
                TableName=table_name,
                Key={'PK': {'S': pk}, 'SK': {'S': sk}}
            )
            last_run = int(chk_resp['Item']['last_run_timestamp']['N']) if 'Item' in chk_resp else 0

            if current_time - last_run >= cadence_sec:
                payload = {
                    "provider": provider,
                    "endpoint": endpoint_key,
                    "secret_name": secret_name,
                    "endpoint_config": endpoint_cfg
                }
                sfn_client.start_execution(
                    stateMachineArn=state_machine_arn,
                    name=f"{provider}-{endpoint_key}-{current_time}",
                    input=json.dumps(payload)
                )
                ddb_client.update_item(
                    TableName=table_name,
                    Key={'PK': {'S': pk}, 'SK': {'S': sk}},
                    UpdateExpression="SET last_run_timestamp = :now",
                    ExpressionAttributeValues={':now': {'N': str(current_time)}}
                )
                dispatched.append(f"{provider}:{endpoint_key}")

    return {"statusCode": 200, "dispatched": dispatched}
