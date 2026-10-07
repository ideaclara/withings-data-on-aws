import json
import os
import time
import urllib.parse
import urllib.request
import boto3

SECRET_NAME = os.environ["SECRET_NAME"]
TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"
sm_client = boto3.client("secretsmanager")

def handler(event, context):
    secret_record = sm_client.get_secret_value(SecretId=SECRET_NAME)
    creds = json.loads(secret_record["SecretString"])

    now = int(time.time())
    expires_at = creds.get("expires_at", 0)

    # Refresh proactively if expiring within 10 minutes (Withings access tokens expire in 10800s)
    if now + 600 >= expires_at:
        payload = {
            "action": "requesttoken",
            "grant_type": "refresh_token",
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "refresh_token": creds["refresh_token"],
        }
        encoded = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(TOKEN_URL, data=encoded, method="POST")
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if body.get("status") != 0:
                raise RuntimeError(f"Refresh failed: {body}")
            tokens = body["body"]

        creds["access_token"] = tokens["access_token"]
        creds["refresh_token"] = tokens["refresh_token"]
        creds["expires_at"] = now + int(tokens["expires_in"])
        creds["userid"] = str(tokens["userid"])

        sm_client.put_secret_value(
            SecretId=SECRET_NAME,
            SecretString=json.dumps(creds),
        )

    return {
        "status": "VALID",
        "access_token": creds["access_token"],
        "userid": creds["userid"],
    }
