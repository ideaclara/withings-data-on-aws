#!/usr/bin/env bash
set -euo pipefail

SECRET_NAME="prod/withings/credentials"
AWS_REGION="${AWS_REGION:-eu-west-1}"
CRED_FILE="../withingsCredentials"

if [ ! -f "$CRED_FILE" ]; then
    echo "Error: Credentials file '$CRED_FILE' not found!"
    exit 1
fi

echo "Creating/Updating AWS Secrets Manager secret: $SECRET_NAME..."

if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" --region "$AWS_REGION" >/dev/null 2>&1; then
    aws secretsmanager put-secret-value \
        --secret-id "$SECRET_NAME" \
        --secret-string "file://$CRED_FILE" \
        --region "$AWS_REGION"
    echo "Secret successfully updated."
else
    aws secretsmanager create-secret \
        --name "$SECRET_NAME" \
        --description "Withings OAuth 2.0 Credentials" \
        --secret-string "file://$CRED_FILE" \
        --region "$AWS_REGION"
    echo "Secret successfully created."
fi
