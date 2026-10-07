import json
import os
import time
import urllib.parse
import urllib.request
import boto3

secrets_client = boto3.client('secretsmanager')

def handler(event, context):
    secret_name = event.get('secret_name') or os.environ.get('SECRET_NAME')
    secret_resp = secrets_client.get_secret_value(SecretId=secret_name)
    credentials = json.loads(secret_resp['SecretString'])

    current_time = int(time.time())
    expires_at = int(credentials.get('expires_at', 0))

    # Refresh if within 5 minutes of expiration
    if current_time >= (expires_at - 300):
        url = "https://wbsapi.withings.net/v2/oauth2"
        data = urllib.parse.urlencode({
            'action': 'requesttoken',
            'grant_type': 'refresh_token',
            'client_id': credentials['client_id'],
            'client_secret': credentials['client_secret'],
            'refresh_token': credentials['refresh_token']
        }).encode('utf-8')

        req = urllib.request.Request(url, data=data, method='POST')
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read().decode('utf-8'))

        if body.get('status') != 0:
            raise RuntimeError(f"Withings token refresh error: {body}")

        token_data = body['body']
        credentials['access_token'] = token_data['access_token']
        credentials['refresh_token'] = token_data['refresh_token']
        credentials['expires_at'] = current_time + int(token_data.get('expires_in', 10800))
        if 'userid' in token_data:
            credentials['userid'] = str(token_data['userid'])

        secrets_client.put_secret_value(
            SecretId=secret_name,
            SecretString=json.dumps(credentials)
        )

    return {
        'access_token': credentials['access_token'],
        'userid': str(credentials.get('userid', ''))
    }
