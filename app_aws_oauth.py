import smartsheet
import os
import json
import logging
import requests
import certifi
import boto3
import datetime
from botocore.exceptions import ClientError

# --- Configuration ---
# Required environment variables for Lambda
CLIENT_ID = os.getenv('SM_CLIENT_ID')
CLIENT_SECRET = os.getenv('SM_CLIENT_SECRET')
SECRET_NAME = os.getenv('SMARTSHEET_TOKEN_SECRET_NAME', 'smartsheet/tokens')

# Smartsheet OAuth endpoint for token refresh
TOKEN_URL = "https://api.smartsheet.com/2.0/token"


def get_secret():
    """Retrieve token dict from AWS Secrets Manager. Returns dict or None."""
    client = boto3.client('secretsmanager')
    try:
        resp = client.get_secret_value(SecretId=SECRET_NAME)
        if 'SecretString' in resp and resp['SecretString']:
            return json.loads(resp['SecretString'])
    except ClientError as e:
        # Not found or access denied
        logging.debug(f"Secrets Manager get_secret_value failed: {e}")
    except Exception as e:
        logging.debug(f"Unexpected error reading secret: {e}")
    return None


def save_secret(token_data: dict):
    """Persist token dict to AWS Secrets Manager.

    token_data should be JSON-serializable containing at least accessToken/refreshToken.
    """
    client = boto3.client('secretsmanager')
    try:
        # Try to update (put a new secret value). If secret doesn't exist, create it.
        client.put_secret_value(SecretId=SECRET_NAME, SecretString=json.dumps(token_data))
    except ClientError as e:
        # If the secret doesn't exist, create it
        if e.response.get('Error', {}).get('Code') in ('ResourceNotFoundException',):
            try:
                client.create_secret(Name=SECRET_NAME, SecretString=json.dumps(token_data))
            except Exception as ce:
                logging.error(f"Failed to create secret: {ce}")
                raise
        else:
            logging.error(f"Failed to put secret value: {e}")
            raise



def emit_refresh_failure(error_type, message, original_error=None):
    """
    Emit a structured error message suitable for CloudWatch alerts.
    
    error_type: One of 'token_expired', 'token_revoked', 'network_error', 'unknown'
    message: Human readable error description
    original_error: Optional original exception
    """
    error_data = {
        'error_type': error_type,
        'message': message,
        'timestamp': datetime.datetime.utcnow().isoformat(),
        'original_error': str(original_error) if original_error else None
    }
    # Log in a format that's easy to parse in CloudWatch
    logging.error(f"SMARTSHEET_AUTH_ERROR: {json.dumps(error_data)}")
    return error_data

def refresh_tokens(refresh_token):
    """Use a refresh token to obtain a new access token."""
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
    }
    try:
        resp = requests.post(TOKEN_URL, data=data, verify=certifi.where(), timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        if e.response is not None:
            if e.response.status_code == 400:
                # Try to parse error details
                try:
                    error_data = e.response.json()
                    error = error_data.get('error', '')
                    if error == 'invalid_grant':
                        emit_refresh_failure('token_revoked', 
                            'Refresh token is invalid or revoked. Re-authorization required.', e)
                    else:
                        emit_refresh_failure('token_expired',
                            f'Token refresh failed with OAuth error: {error}', e)
                except Exception:
                    emit_refresh_failure('unknown',
                        'Token refresh failed with unreadable error response', e)
            else:
                emit_refresh_failure('network_error',
                    f'Token refresh failed with HTTP {e.response.status_code}', e)
        else:
            emit_refresh_failure('network_error',
                'Token refresh failed with no response', e)
        raise
    except requests.exceptions.Timeout:
        emit_refresh_failure('network_error', 'Token refresh timed out', None)
        raise
    except Exception as e:
        emit_refresh_failure('unknown', 'Unexpected error during token refresh', e)
        raise


# No need for a separate save_tokens function - we can use save_secret directly


def get_smartsheet_client(scopes):
    """
    Initializes the Smartsheet client, handling OAuth 2.0 authentication.
    If a saved refresh token exists, it refreshes the access token.
    Otherwise, it initiates the manual OAuth flow to get the initial tokens.
    """

    # We'll only create the SDK client after we have a valid access token
    smart = None
    # Get tokens from Secrets Manager
    token_data = get_secret()
    access = None
    refresh = None

    if token_data:
        access = token_data.get('accessToken')
        refresh = token_data.get('refreshToken')

        # If we have an access token, create a client
        if access:
            # The Smartsheet SDK has evolved and different versions accept different patterns
            # Try the most common pattern first
            smart = smartsheet.Smartsheet()
            smart.access_token = access
            return smart

        # If no access but have a refresh token, attempt to refresh
        if refresh:
            logging.info("Attempting to refresh token using saved refresh token...")
            try:
                new = refresh_tokens(refresh)
                access = new.get('access_token') or new.get('accessToken')
                refresh = new.get('refresh_token') or new.get('refreshToken')
                if access:
                    # Persist refreshed tokens
                    try:
                        save_secret({
                            "accessToken": access,
                            "refreshToken": refresh
                        })
                    except Exception as e:
                        logging.warning(f"Failed to persist refreshed tokens: {e}")

                    # Create client with refreshed access token
                    smart = smartsheet.Smartsheet()
                    smart.access_token = access
                    logging.info("Token refresh successful.")
                    return smart
            except Exception as e:
                logging.warning(f"Refresh failed: {e}")

    # If we reach here, no valid tokens exist
    logging.error("No valid tokens available in Secrets Manager. Ensure the secret exists and contains valid tokens.")
    return None


# Required scopes for workspace deletion
REQUIRED_SCOPES = [
    'READ_USERS', 'READ_SHEETS', 'WRITE_SHEETS',
    'DELETE_SHEETS', 'MANAGE_WORKSPACES'
]

def lambda_handler(event, context):
    """
    AWS Lambda handler that runs the Smartsheet workspace deletion workflow.
    
    Required environment variables:
    - SM_CLIENT_ID: Smartsheet OAuth client ID
    - SM_CLIENT_SECRET: Smartsheet OAuth client secret
    - SMARTSHEET_TOKEN_SECRET_NAME: Name of secret storing OAuth tokens
    
    The secret should contain:
    {
        "accessToken": "...",
        "refreshToken": "..."
    }
    """
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    # Get authenticated Smartsheet client
    client = get_smartsheet_client(REQUIRED_SCOPES)
    if not client:
        error_msg = "Failed to initialize Smartsheet client. Check if secret exists and contains valid tokens."
        logging.error(error_msg)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': error_msg,
                'detail': 'Ensure the secret exists in Secrets Manager and contains valid tokens.'
            })
        }
    
    # Run the workspace deletion logic
    try:
        from main import process_workspace_deletions
        result = process_workspace_deletions(client)
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Workspace deletion completed successfully',
                'result': result
            })
        }
    except Exception as e:
        error_msg = f"Workspace deletion failed: {str(e)}"
        logging.error(error_msg)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': error_msg
            })
        }


# Local testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    # Simulate a Lambda invocation locally
    result = lambda_handler({}, None)
    print(f"\nLambda response: {json.dumps(result, indent=2)}")
