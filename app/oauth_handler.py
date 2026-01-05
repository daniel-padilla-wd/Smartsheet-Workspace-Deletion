"""
OAuth 2.0 handler for Smartsheet authentication.

This module handles the complete OAuth flow including:
- Building authorization URLs
- Exchanging authorization codes for tokens
- Refreshing access tokens
- Managing token storage
- Providing authenticated Smartsheet clients
"""

import smartsheet
import os
import json
import logging
import secrets
import webbrowser
import requests
import certifi
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from threading import Thread
from config import config

# AWS imports - optional for local development
try:
    import boto3
    from botocore.exceptions import ClientError
    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False
    logging.debug("boto3 not available - AWS Secrets Manager support disabled")

# AWS Secrets Manager secret names
ACCESS_TOKEN_SECRET = "ausw2p-smgr-smt-access-token-001"
REFRESH_TOKEN_SECRET = "ausw2p-smgr-smt-refresh-token-002"
CLIENT_ID_SECRET = "ausw2p-smgr-smt-client-id-003"
CLIENT_SECRET_SECRET = "ausw2p-smgr-smt-client-secret-004"

# Detect if running in AWS Lambda environment
IS_AWS_LAMBDA = os.getenv('AWS_LAMBDA_FUNCTION_NAME') is not None or os.getenv('AWS_EXECUTION_ENV') is not None


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP request handler for OAuth callback server."""
    
    # Class variables to store state and authorization code
    expected_state = None
    auth_code = None
    
    def do_GET(self):
        """Handle GET request from OAuth redirect."""
        parsed = urlparse(self.path)
        if parsed.path == urlparse(config.REDIRECT_URI).path:
            qs = parse_qs(parsed.query)
            
            # Validate state parameter for CSRF protection
            returned_state = qs.get('state', [None])[0]
            if returned_state != OAuthCallbackHandler.expected_state:
                logging.error(f"State mismatch: expected {OAuthCallbackHandler.expected_state}, got {returned_state}")
                self.send_response(400)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b"<html><body><h2>Invalid state parameter. Authorization failed.</h2></body></html>")
                return
            
            if 'code' in qs:
                # Store the authorization code in class variable
                OAuthCallbackHandler.auth_code = qs['code'][0]
                # Respond to browser
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(
                    b"<html><body><h2>Authorization successful. You can close this window.</h2></body></html>"
                )
                # Shutdown server after response
                def shutdown_server():
                    try:
                        self.server.shutdown()
                    except Exception:
                        pass
                Thread(target=shutdown_server).start()
                return
        # Default response for other paths
        self.send_response(404)
        self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress default HTTP server logging."""
        pass


# ============================================================================
# AWS Secrets Manager Functions
# ============================================================================

def get_secret_string(secret_name):
    """
    Retrieve plain string value from AWS Secrets Manager.
    
    Args:
        secret_name: Name of the secret in AWS Secrets Manager
        
    Returns:
        str or None: Secret value or None if retrieval fails
    """
    if not AWS_AVAILABLE:
        logging.error("boto3 not available - cannot access AWS Secrets Manager")
        return None
    
    client = boto3.client('secretsmanager')
    try:
        resp = client.get_secret_value(SecretId=secret_name)
        
        if 'SecretString' in resp:
            return resp['SecretString']
        else:
            logging.error(f"Secret {secret_name} does not contain SecretString")
            return None
    except ClientError as e:
        logging.error(f"Secrets Manager get_secret_value failed for {secret_name}: {e}")
    except Exception as e:
        logging.error(f"Unexpected error reading secret {secret_name}: {e}")
    return None


def get_oauth_credentials_from_aws():
    """
    Retrieve OAuth client ID and secret from AWS Secrets Manager.
    
    Returns:
        tuple: (client_id, client_secret) or (None, None) if retrieval fails
    """
    client_id_json = get_secret_string(CLIENT_ID_SECRET)
    client_secret_json = get_secret_string(CLIENT_SECRET_SECRET)
    
    if not client_id_json or not client_secret_json:
        missing = []
        if not client_id_json: missing.append(CLIENT_ID_SECRET)
        if not client_secret_json: missing.append(CLIENT_SECRET_SECRET)
        logging.error(f"Failed to retrieve OAuth credentials from secrets: {', '.join(missing)}")
        return None, None
    
    try:
        client_id = json.loads(client_id_json).get("CLIENT_ID")
        client_secret = json.loads(client_secret_json).get("CLIENT_SECRET")
        
        if client_id and client_secret:
            return client_id, client_secret
        else:
            logging.error("OAuth credentials secrets exist but do not contain expected keys")
            return None, None
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse OAuth credentials JSON: {e}")
        return None, None


def save_tokens_to_aws(access_token, refresh_token):
    """
    Save access and refresh tokens to AWS Secrets Manager.
    
    Note: This requires appropriate IAM permissions for secretsmanager:PutSecretValue
    and secretsmanager:CreateSecret.
    
    Args:
        access_token: Current access token
        refresh_token: Current refresh token
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not AWS_AVAILABLE:
        logging.error("boto3 not available - cannot save to AWS Secrets Manager")
        return False
    
    client = boto3.client('secretsmanager')
    
    # Save access token
    try:
        client.put_secret_value(SecretId=ACCESS_TOKEN_SECRET, SecretString=access_token)
        logging.info(f"Saved access token to {ACCESS_TOKEN_SECRET}")
    except ClientError as e:
        if e.response.get('Error', {}).get('Code') in ('ResourceNotFoundException',):
            try:
                client.create_secret(Name=ACCESS_TOKEN_SECRET, SecretString=access_token)
                logging.info(f"Created new secret {ACCESS_TOKEN_SECRET}")
            except Exception as ce:
                logging.error(f"Failed to create access token secret: {ce}")
                return False
        else:
            logging.error(f"Failed to save access token: {e}")
            return False
    
    # Save refresh token
    try:
        client.put_secret_value(SecretId=REFRESH_TOKEN_SECRET, SecretString=refresh_token)
        logging.info(f"Saved refresh token to {REFRESH_TOKEN_SECRET}")
    except ClientError as e:
        if e.response.get('Error', {}).get('Code') in ('ResourceNotFoundException',):
            try:
                client.create_secret(Name=REFRESH_TOKEN_SECRET, SecretString=refresh_token)
                logging.info(f"Created new secret {REFRESH_TOKEN_SECRET}")
            except Exception as ce:
                logging.error(f"Failed to create refresh token secret: {ce}")
                return False
        else:
            logging.error(f"Failed to save refresh token: {e}")
            return False
    
    return True


def load_tokens_from_aws():
    """
    Load stored tokens from AWS Secrets Manager.
    
    Returns:
        tuple: (access_token, refresh_token) or (None, None) if not found
    """
    access_json = get_secret_string(ACCESS_TOKEN_SECRET)
    refresh_json = get_secret_string(REFRESH_TOKEN_SECRET)
    
    access = json.loads(access_json).get("accessToken") if access_json else None
    refresh = json.loads(refresh_json).get("refreshToken") if refresh_json else None
    
    return access, refresh


# ============================================================================
# Local File Storage Functions
# ============================================================================


def build_auth_url(scopes, state='state123'):
    """
    Construct the Smartsheet authorization URL.
    
    Args:
        scopes: List of permission scopes or space-separated string
        state: Optional state parameter for CSRF protection
        
    Returns:
        str: Complete authorization URL
    """
    # Get client ID from appropriate source
    if IS_AWS_LAMBDA and AWS_AVAILABLE:
        client_id, _ = get_oauth_credentials_from_aws()
        if not client_id:
            logging.error("Failed to get client_id from AWS Secrets Manager")
            return None
    else:
        client_id = config.CLIENT_ID
    
    scope_str = "+".join(scopes) if isinstance(scopes, (list, tuple)) else scopes
    params = (
        f"response_type=code&client_id={client_id}"
        f"&scope={scope_str}&redirect_uri={config.REDIRECT_URI}&state={state}"
    )
    return f"{config.AUTH_BASE}?{params}"


def exchange_code_for_tokens(code):
    """
    Exchange authorization code for access and refresh tokens.
    
    Args:
        code: Authorization code from OAuth callback
        
    Returns:
        dict: Token response containing access_token and refresh_token
    """
    # Get OAuth credentials from appropriate source
    if IS_AWS_LAMBDA and AWS_AVAILABLE:
        client_id, client_secret = get_oauth_credentials_from_aws()
        if not client_id or not client_secret:
            raise ValueError("Failed to get OAuth credentials from AWS Secrets Manager")
    else:
        client_id = config.CLIENT_ID
        client_secret = config.CLIENT_SECRET
    
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': config.REDIRECT_URI,
    }
    resp = requests.post(config.TOKEN_URL, data=data, verify=certifi.where(), timeout=15)
    resp.raise_for_status()
    return resp.json()


def refresh_tokens(refresh_token):
    """
    Use a refresh token to obtain a new access token.
    
    Args:
        refresh_token: Valid refresh token
        
    Returns:
        dict: Token response containing new access_token and refresh_token
    """
    # Get OAuth credentials from appropriate source
    if IS_AWS_LAMBDA and AWS_AVAILABLE:
        client_id, client_secret = get_oauth_credentials_from_aws()
        if not client_id or not client_secret:
            raise ValueError("Failed to get OAuth credentials from AWS Secrets Manager")
    else:
        client_id = config.CLIENT_ID
        client_secret = config.CLIENT_SECRET
    
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': client_id,
        'client_secret': client_secret,
    }
    resp = requests.post(config.TOKEN_URL, data=data, verify=certifi.where(), timeout=15)
    resp.raise_for_status()
    return resp.json()


def save_tokens(access_token, refresh_token):
    """
    Save access and refresh tokens to appropriate storage.
    Uses AWS Secrets Manager in Lambda, local file otherwise.
    
    Args:
        access_token: Current access token
        refresh_token: Current refresh token
        
    Returns:
        bool: True if successful, False otherwise
    """
    if IS_AWS_LAMBDA and AWS_AVAILABLE:
        # Note: This will fail if Lambda doesn't have write permissions
        # User will need to manually update tokens locally and redeploy
        logging.info("Running in AWS Lambda - attempting to save to Secrets Manager")
        success = save_tokens_to_aws(access_token, refresh_token)
        if not success:
            logging.warning("Failed to save tokens to AWS Secrets Manager - check IAM permissions")
        return success
    else:
        # Local file storage
        token_data = {
            "accessToken": access_token,
            "refreshToken": refresh_token
        }
        try:
            with open(config.TOKEN_FILE, 'w') as f:
                json.dump(token_data, f)
            logging.info(f"Saved tokens to local file: {config.TOKEN_FILE}")
            return True
        except Exception as e:
            logging.error(f"Failed to save tokens to file: {e}")
            return False


def load_tokens():
    """
    Load stored tokens from appropriate storage.
    Uses AWS Secrets Manager in Lambda, local file otherwise.
    
    Returns:
        tuple: (access_token, refresh_token) or (None, None) if not found
    """
    if IS_AWS_LAMBDA and AWS_AVAILABLE:
        logging.info("Running in AWS Lambda - loading tokens from Secrets Manager")
        return load_tokens_from_aws()
    else:
        # Local file storage
        if not os.path.exists(config.TOKEN_FILE):
            return None, None
        
        try:
            with open(config.TOKEN_FILE, 'r') as f:
                token_data = json.load(f)
                access = token_data.get('accessToken')
                refresh = token_data.get('refreshToken')
                logging.info(f"Loaded tokens from local file: {config.TOKEN_FILE}")
                return access, refresh
        except Exception as e:
            logging.warning(f"Failed to load tokens from file: {e}")
            return None, None


def create_smartsheet_client(access_token):
    """
    Create a Smartsheet client with the given access token.
    
    Args:
        access_token: Valid access token
        
    Returns:
        smartsheet.Smartsheet: Authenticated client instance
    """
    try:
        return smartsheet.Smartsheet(access_token)
    except Exception:
        try:
            return smartsheet.Smartsheet(access_token=access_token)
        except Exception:
            # Fallback: create empty client and set attribute directly
            smart = smartsheet.Smartsheet()
            try:
                setattr(smart, 'access_token', access_token)
            except Exception:
                pass
            return smart


def validate_client(client):
    """
    Validate that a Smartsheet client has a working access token.
    
    Only treats authentication errors (401/403) as invalid tokens.
    Other errors (network issues, etc.) are logged but the client is still considered valid
    to avoid unnecessary token refresh loops.
    
    Args:
        client: Smartsheet client instance
        
    Returns:
        bool: True if client is valid or error is non-auth related, False only for auth errors
    """
    try:
        response = client.Users.get_current_user()
        
        # Check if response contains embedded error (SDK doesn't always raise exceptions)
        if hasattr(response, 'to_dict'):
            response_dict = response.to_dict()
            if "result" in response_dict and isinstance(response_dict["result"], dict):
                result = response_dict["result"]
                if "errorCode" in result or "statusCode" in result:
                    status_code = result.get("statusCode", result.get("errorCode"))
                    if status_code in (401, 403):
                        logging.info(f"Access token expired or unauthorized (status code: {status_code})")
                        return False
                    else:
                        logging.warning(f"API validation check failed with non-auth error: {status_code}. Proceeding with token anyway.")
                        return True
        
        return True
    except Exception as e:
        # Check if it's a Smartsheet API error with auth status code
        if hasattr(e, 'error') and hasattr(e.error, 'status_code'):
            if e.error.status_code in (401, 403):
                logging.info(f"Access token expired or unauthorized (HTTP {e.error.status_code})")
                return False
            else:
                # Other API errors - don't treat as token expiration
                logging.warning(f"API validation check failed with non-auth error: {e}. Proceeding with token anyway.")
                return True
        else:
            # Network or other errors - don't treat as token expiration to avoid refresh loops
            logging.warning(f"Token validation check failed with error: {e}. Proceeding with token anyway.")
            return True


def run_oauth_flow(scopes):
    """
    Run the complete OAuth authorization flow with local callback server.
    
    Args:
        scopes: List of required permission scopes
        
    Returns:
        str: Authorization code or None if flow failed
    """
    # Generate random state for CSRF protection
    state = secrets.token_urlsafe(32)
    
    # Reset class variables before starting
    OAuthCallbackHandler.auth_code = None
    OAuthCallbackHandler.expected_state = state
    
    auth_url = build_auth_url(scopes, state=state)
    
    print("\n--- AUTHORIZATION REQUIRED ---")
    print("Opening browser to the authorization URL. If it doesn't open, copy/paste the URL below:")
    print(auth_url)
    
    # Try to open browser automatically
    try:
        webbrowser.open(auth_url)
    except Exception:
        logging.warning("Failed to open browser automatically. Please open the URL manually.")
    
    # Bind to callback URI
    parsed_redirect = urlparse(config.REDIRECT_URI)
    server_address = (parsed_redirect.hostname or 'localhost', parsed_redirect.port or 8080)
    
    try:
        httpd = HTTPServer(server_address, OAuthCallbackHandler)
        logging.info(f"Listening for OAuth callback on {config.REDIRECT_URI}")
        httpd.handle_request()
    except OSError as e:
        logging.warning(f"Could not start local server: {e}. Falling back to manual input.")
    
    # Manual fallback if needed
    if not OAuthCallbackHandler.auth_code:
        auth_code = input("\nPaste the 'code' parameter from redirect URL (or Enter to cancel): ").strip()
        if not auth_code:
            logging.error("No authorization code provided.")
            return None
        return auth_code
    
    return OAuthCallbackHandler.auth_code



def get_smartsheet_client(scopes):
    """
    Get an authenticated Smartsheet client, handling full OAuth flow.
    
    This is the main entry point for authentication. It will:
    1. Try to use existing saved tokens
    2. Refresh token if expired
    3. Run new OAuth flow if no valid tokens exist
    
    Args:
        scopes: List of required permission scopes
        
    Returns:
        smartsheet.Smartsheet: Authenticated client or None if auth failed
    """
    # Try to use existing tokens
    access, refresh = load_tokens()
    
    if access:
        logging.info("Found saved access token, validating...")
        client = create_smartsheet_client(access)
        
        if validate_client(client):
            logging.info("Saved access token is valid.")
            return client
        
        # Token expired, try refresh
        if refresh:
            logging.info("Access token expired, refreshing...")
            try:
                new_tokens = refresh_tokens(refresh)
                access = new_tokens.get('access_token') or new_tokens.get('accessToken')
                refresh = new_tokens.get('refresh_token') or new_tokens.get('refreshToken')
                
                if access:
                    save_tokens(access, refresh)
                    logging.info("Token refresh successful.")
                    return create_smartsheet_client(access)
            except Exception as e:
                logging.warning(f"Token refresh failed: {e}. Starting new auth flow.")
    
    # Need new authorization
    logging.info("Starting new OAuth 2.0 authorization flow...")
    auth_code = run_oauth_flow(scopes)
    
    if not auth_code:
        return None
    
    # Exchange code for tokens
    try:
        token_info = exchange_code_for_tokens(auth_code)
        access = token_info.get('access_token') or token_info.get('accessToken')
        refresh = token_info.get('refresh_token') or token_info.get('refreshToken')
        
        if not access:
            logging.error("Token response did not include access token.")
            return None
        
        save_tokens(access, refresh)
        logging.info("Initial token exchange successful. Tokens saved.")
        
        return create_smartsheet_client(access)
    except Exception as e:
        logging.error(f"Failed to exchange code for tokens: {e}")
        return None
