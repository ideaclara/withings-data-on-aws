# src/lambda/auth_refresher/handler.py
import json
import os
import time
import urllib.parse
import urllib.request
import boto3

secrets_client = boto3.client("secretsmanager")
SECRET_ARN = os.environ["WITHINGS_SECRET_ARN"]
TOKEN_ENDPOINT = "https://wbsapi.withings.net/v2/oauth2"

def get_credentials() -> dict:
    resp = secrets_client.get_secret_value(SecretId=SECRET_ARN)
    return json.loads(resp["SecretString"])

def refresh_tokens(creds: dict) -> dict:
    payload = {
        "action": "requesttoken",
        "grant_type": "refresh_token",
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"]
    }
    
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(TOKEN_ENDPOINT, data=data, method="POST")
    
    with urllib.request.urlopen(req) as response:
        res_body = json.loads(response.read().decode("utf-8"))
        
    if res_body.get("status") != 0:
        raise RuntimeError(f"Token refresh failed: {res_body}")
        
    body = res_body["body"]
    now = int(time.time())
    
    creds["access_token"] = body["access_token"]
    creds["refresh_token"] = body["refresh_token"]
    creds["expires_at"] = now + int(body["expires_in"])
    creds["userid"] = str(body["userid"])
    
    secrets_client.put_secret_value(
        SecretId=SECRET_ARN,
        SecretString=json.dumps(creds)
    )
    return creds

def handler(event, context):
    creds = get_credentials()
    now = int(time.time())
    
    # Refresh proactively if within a 5-minute safety threshold
    if now + 300 >= creds.get("expires_at", 0):
        creds = refresh_tokens(creds)
        
    return {
        "statusCode": 200,
        "access_token": creds["access_token"],
        "userid": creds["userid"]
    }