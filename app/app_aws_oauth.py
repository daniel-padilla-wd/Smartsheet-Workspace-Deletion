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
OAUTH_SECRET_NAME = os.getenv('SMARTSHEET_OAUTH_SECRET_NAME', 'smartsheet/oauth')
TOKEN_SECRET_NAME = os.getenv('SMARTSHEET_TOKEN_SECRET_NAME', 'smartsheet/tokens')

# Smartsheet OAuth endpoint for token refresh
TOKEN_URL = "https://api.smartsheet.com/2.0/token"


def get_secret(secret_name):
    """Retrieve dict from AWS Secrets Manager. Returns dict or None."""
    client = boto3.client('secretsmanager')
    try:
        resp = client.get_secret_value(SecretId=secret_name)
        if 'SecretString' in resp and resp['SecretString']:
            parsed_data = json.loads(resp['SecretString'])
            if isinstance(parsed_data, dict):
                return parsed_data
            else:
                logging.error(f"Secret {secret_name} contains invalid data type: expected dict, got {type(parsed_data)}")
                return None
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse secret {secret_name} as JSON: {e}")
    except ClientError as e:
        # Not found or access denied
        logging.debug(f"Secrets Manager get_secret_value failed for {secret_name}: {e}")
    except Exception as e:
        logging.debug(f"Unexpected error reading secret {secret_name}: {e}")
    return None


def get_oauth_credentials():
    """Retrieve OAuth client ID and secret from AWS Secrets Manager."""
    oauth_data = get_secret(OAUTH_SECRET_NAME)
    if oauth_data and isinstance(oauth_data, dict):
        client_id = oauth_data.get('client_id') or oauth_data.get('CLIENT_ID')
        client_secret = oauth_data.get('client_secret') or oauth_data.get('CLIENT_SECRET')
        
        if client_id and client_secret:
            return client_id, client_secret
        else:
            missing = []
            if not client_id: missing.append('client_id')
            if not client_secret: missing.append('client_secret')
            logging.error(f"OAuth secret missing required fields: {', '.join(missing)}")
    else:
        logging.error(f"Failed to retrieve OAuth credentials from secret: {OAUTH_SECRET_NAME}")
    
    return None, None


def save_token_secret(token_data: dict):
    """Persist token dict to AWS Secrets Manager.

    token_data should be JSON-serializable containing at least accessToken/refreshToken.
    """
    client = boto3.client('secretsmanager')
    try:
        # Try to update (put a new secret value). If secret doesn't exist, create it.
        client.put_secret_value(SecretId=TOKEN_SECRET_NAME, SecretString=json.dumps(token_data))
    except ClientError as e:
        # If the secret doesn't exist, create it
        if e.response.get('Error', {}).get('Code') in ('ResourceNotFoundException',):
            try:
                client.create_secret(Name=TOKEN_SECRET_NAME, SecretString=json.dumps(token_data))
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
    client_id, client_secret = get_oauth_credentials()
    if not client_id or not client_secret:
        raise ValueError("OAuth credentials not available")
    
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': client_id,
        'client_secret': client_secret,
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


def get_smartsheet_client(scopes=None):
    """
    Initializes the Smartsheet client, handling OAuth 2.0 authentication.
    Attempts to use existing access token, or refreshes using refresh token if needed.
    
    Args:
        scopes: OAuth scopes (unused in current implementation, kept for compatibility)
    
    Returns:
        smartsheet.Smartsheet: Authenticated Smartsheet client or None if authentication fails
    """
    # Get tokens from Secrets Manager
    token_data = get_secret(TOKEN_SECRET_NAME)
    access = None
    refresh = None

    if token_data and isinstance(token_data, dict):
        access = token_data.get('accessToken')
        refresh = token_data.get('refreshToken')
    elif token_data is not None:
        logging.error(f"Expected token_data to be a dictionary, got {type(token_data)}: {token_data}")
        return None

    # If we have an access token, create a client
    if access:
        smart = smartsheet.Smartsheet()
        smart.access_token = access
        return smart

    # If no access but have a refresh token, attempt to refresh
    if refresh:
        logging.info("Attempting to refresh token using saved refresh token...")
        try:
            new_tokens = refresh_tokens(refresh)
            access = new_tokens.get('access_token') or new_tokens.get('accessToken')
            refresh = new_tokens.get('refresh_token') or new_tokens.get('refreshToken')
            
            if access:
                # Persist refreshed tokens
                try:
                    save_token_secret({
                        "accessToken": access,
                        "refreshToken": refresh
                    })
                    logging.info("Token refresh successful.")
                except Exception as e:
                    logging.warning(f"Failed to persist refreshed tokens: {e}")

                # Create client with refreshed access token
                smart = smartsheet.Smartsheet()
                smart.access_token = access
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
    - SMARTSHEET_OAUTH_SECRET_NAME: Name of secret storing OAuth credentials (default: 'smartsheet/oauth')
    - SMARTSHEET_TOKEN_SECRET_NAME: Name of secret storing OAuth tokens (default: 'smartsheet/tokens')
    - INTAKE_SHEET_ID: Smartsheet ID for the sheet containing deletion requests
    - COLUMN_TITLES: Comma-separated column names for parsing the sheet
    
    Required secrets in AWS Secrets Manager:
    1. OAuth secret (default name: 'smartsheet/oauth'):
    {
        "client_id": "your-oauth-client-id",
        "client_secret": "your-oauth-client-secret"
    }
    
    2. Token secret (default name: 'smartsheet/tokens'):
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
    
    # Verify authentication by getting current user
    try:
        current = client.Users.get_current_user()
        # Print a brief summary (handle different SDK return shapes)
        user_email = None
        if hasattr(current, 'email'):
            user_email = current.email
        elif isinstance(current, dict):
            user_email = current.get('email') or current.get('result')
        else:
            # fallback to string representation
            user_email = str(current)
        logging.info(f"Authenticated as: {user_email}")
    except Exception as e:
        logging.warning(f"Warning: verification call failed: {e}")
    
    # Run the workspace deletion logic
    try:
        # Get sheet ID from environment variable
        sheet_id = os.getenv('INTAKE_SHEET_ID')
        if not sheet_id:
            error_msg = "INTAKE_SHEET_ID environment variable not set"
            logging.error(error_msg)
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': error_msg,
                    'detail': 'Set INTAKE_SHEET_ID environment variable with the Smartsheet ID'
                })
            }
        
        from main import process_workspace_deletions
        result = process_workspace_deletions(client, sheet_id)
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
