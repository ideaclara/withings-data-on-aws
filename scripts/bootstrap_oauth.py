# scripts/bootstrap_oauth.py
import http.server
import json
import os
import secrets
import sys
import time
import urllib.parse
import urllib.request
import webbrowser
import boto3

CREDENTIALS_FILE = "withingsCredentials.json"
SECRET_NAME = "prod/withings/credentials"
# Target London region explicitly
AWS_REGION = os.environ.get("AWS_REGION", "eu-west-2")
AWS_PROFILE = os.environ.get("AWS_PROFILE", None)

PORT = 5173
SCOPES = "user.info,user.metrics,user.activity"
AUTH_URL = "https://account.withings.com/oauth2_user/authorize2"
TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"

auth_code = None
state_token = secrets.token_urlsafe(16)

class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        url_components = urllib.parse.urlparse(self.path)
        if url_components.path == "/oauth/callback":
            params = urllib.parse.parse_qs(url_components.query)
            if "error" in params:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f"OAuth Error: {params.get('error')}".encode("utf-8"))
                return

            returned_state = params.get("state", [None])[0]
            if returned_state != state_token:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch error.")
                return

            auth_code = params.get("code", [None])[0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Authentication successful!</h1><p>You can close this tab and return to the terminal.</p>")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        return

def exchange_code(code: str, client_id: str, client_secret: str, redirect_uri: str) -> dict:
    payload = {
        "action": "requesttoken",
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri
    }
    encoded_data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(TOKEN_URL, data=encoded_data, method="POST")
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        if body.get("status") != 0:
            raise RuntimeError(f"Token exchange failed: {body}")
        return body["body"]

def get_boto3_secrets_client():
    """Initializes boto3 client with SSO credentials resolution."""
    session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    return session.client("secretsmanager")

def main():
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"Error: {CREDENTIALS_FILE} not found.")
        sys.exit(1)

    with open(CREDENTIALS_FILE, "r") as f:
        creds = json.load(f)

    client_id = creds["client_id"]
    client_secret = creds["client_secret"]
    redirect_uri = creds.get("redirect_uri", f"http://localhost:{PORT}/oauth/callback")

    # If access_token and refresh_token already exist from your prior run, use them
    if "access_token" in creds and "refresh_token" in creds:
        print("Using existing tokens from withingsCredentials.json...")
        persisted_secret = creds
    else:
        auth_params = {
            "response_type": "code",
            "client_id": client_id,
            "scope": SCOPES,
            "redirect_uri": redirect_uri,
            "state": state_token
        }
        full_auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(auth_params)}"

        server = http.server.HTTPServer(("127.0.0.1", PORT), OAuthCallbackHandler)
        print("Opening browser for Withings authorization...")
        webbrowser.open(full_auth_url)

        print("Listening on http://localhost:5173/oauth/callback...")
        while not auth_code:
            server.handle_request()

        print("Authorization code received. Exchanging for tokens...")
        token_body = exchange_code(auth_code, client_id, client_secret, redirect_uri)

        now = int(time.time())
        persisted_secret = {
            "client_id": client_id,
            "client_secret": client_secret,
            "userid": str(token_body["userid"]),
            "access_token": token_body["access_token"],
            "refresh_token": token_body["refresh_token"],
            "expires_at": now + int(token_body["expires_in"]),
            "scope": token_body.get("scope", SCOPES)
        }

        with open(CREDENTIALS_FILE, "w") as f:
            json.dump(persisted_secret, f, indent=2)

    # Persist into AWS Secrets Manager in London (eu-west-2)
    print(f"Persisting secret to Secrets Manager ({SECRET_NAME}) in {AWS_REGION}...")
    sm_client = get_boto3_secrets_client()
    try:
        sm_client.put_secret_value(
            SecretId=SECRET_NAME,
            SecretString=json.dumps(persisted_secret)
        )
        print(f"Updated existing secret {SECRET_NAME} in {AWS_REGION}.")
    except sm_client.exceptions.ResourceNotFoundException:
        sm_client.create_secret(
            Name=SECRET_NAME,
            Description="Withings OAuth 2.0 Credentials",
            SecretString=json.dumps(persisted_secret)
        )
        print(f"Created new secret {SECRET_NAME} in {AWS_REGION}.")

    print("Tokens successfully synchronized to AWS.")

if __name__ == "__main__":
    main()