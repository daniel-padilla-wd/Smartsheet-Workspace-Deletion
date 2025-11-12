# Smartsheet Workspace Deletion - Lambda Deployment Guide

## Required Environment Variables

Configure these environment variables in your Lambda function:

```
# OAuth App Credentials
SM_CLIENT_ID=your_client_id         # Your Smartsheet OAuth app client ID
SM_CLIENT_SECRET=your_client_secret # Your Smartsheet OAuth app client secret

# AWS Configuration
SMARTSHEET_TOKEN_SECRET_NAME=smartsheet/tokens  # Name of the Secrets Manager secret storing tokens
```

## AWS Secrets Manager Setup

1. Create a secret in AWS Secrets Manager with this structure:
```json
{
    "accessToken": "your_access_token",
    "refreshToken": "your_refresh_token"
}
```

## Required IAM Permissions

Your Lambda function's execution role needs these permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue",
                "secretsmanager:PutSecretValue"
            ],
            "Resource": "arn:aws:secretsmanager:*:*:secret:smartsheet/tokens*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:*"
        }
    ]
}
```

## Lambda Function Configuration

1. Runtime: Python 3.8 or later
2. Handler: `app_aws_oauth.lambda_handler`
3. Memory: 128 MB (minimum)
4. Timeout: 30 seconds (adjust based on your sheet size)

## Package and Deploy

1. Create a deployment package:
```bash
# Create and activate a virtual environment (optional but recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create deployment package
mkdir package
pip install -r requirements.txt -t package/
cp app_aws_oauth.py main.py package/
cd package && zip -r ../lambda.zip . && cd ..
```

2. Upload the `lambda.zip` to AWS Lambda

## Monitoring and Error Handling

The Lambda function emits structured error logs for token-related issues:

- Watch for `SMARTSHEET_AUTH_ERROR` in CloudWatch Logs
- Error types:
  - `token_revoked`: Refresh token is invalid/revoked
  - `token_expired`: Access token expired
  - `network_error`: Connection issues
  - `unknown`: Other errors

Example CloudWatch Metric Filter:
```
filter pattern: { $.error_type = token_revoked }
metric name: TokenRevokedErrors
```

## Troubleshooting

1. **Secret Access Issues**
   - Verify the secret exists in Secrets Manager
   - Check IAM role permissions
   - Verify secret name matches `SMARTSHEET_TOKEN_SECRET_NAME`

2. **Token Issues**
   - Check CloudWatch Logs for `SMARTSHEET_AUTH_ERROR`
   - Verify tokens in secret are valid
   - If tokens are revoked, you'll need to:
     1. Run local OAuth flow to get new tokens
     2. Update the secret with new tokens

3. **Common HTTP Errors**
   - 400: Invalid token or revoked access
   - 401: Unauthorized (check scopes)
   - 403: Insufficient permissions
   - 429: Rate limit exceeded

## Security Considerations

1. Use AWS KMS to encrypt the Secrets Manager secret
2. Rotate the OAuth client secret periodically
3. Monitor CloudWatch logs for auth errors
4. Consider implementing alerts for token revocation