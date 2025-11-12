import smartsheet
import os
import json
import logging
import webbrowser
import requests
import certifi
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from threading import Thread
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# --- Configuration ---
# Replace these with the values from Step A (Client ID & Client Secret)
# Prefer environment variables for safety (e.g. export SM_CLIENT_ID=...)
CLIENT_ID = os.getenv('CLIENT_ID', None)
CLIENT_SECRET = os.getenv('CLIENT_SECRET', None)
REDIRECT_URI = "http://localhost:8080/callback"  # Must match app registration
TOKEN_FILE = "smartsheet_token.json"  # File to store the Refresh Token

directory_path = Path("Smartsheet Workspace Deletion/secrets")

# Smartsheet OAuth endpoints
AUTH_BASE = "https://app.smartsheet.com/b/authorize"
TOKEN_URL = "https://api.smartsheet.com/2.0/token"


def build_auth_url(scopes, state='state123'):
    """Construct the Smartsheet authorization URL."""
    scope_str = "+".join(scopes) if isinstance(scopes, (list, tuple)) else scopes
    params = (
        f"response_type=code&client_id={CLIENT_ID}"
        f"&scope={scope_str}&redirect_uri={REDIRECT_URI}&state={state}"
    )
    return f"{AUTH_BASE}?{params}"


def exchange_code_for_tokens(code):
    """Exchange authorization code for access and refresh tokens via Smartsheet token endpoint."""
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'redirect_uri': REDIRECT_URI,
    }
    resp = requests.post(TOKEN_URL, data=data, verify=certifi.where(), timeout=15)
    resp.raise_for_status()
    return resp.json()


def refresh_tokens(refresh_token):
    """Use a refresh token to obtain a new access token."""
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
    }
    resp = requests.post(TOKEN_URL, data=data, verify=certifi.where(), timeout=15)
    resp.raise_for_status()
    return resp.json()


def save_tokens(access_token, refresh_token):
    """Saves the access and refresh tokens to a file."""
    token_data = {
        "accessToken": access_token,
        "refreshToken": refresh_token
    }
    with open(TOKEN_FILE, 'w') as f:
        json.dump(token_data, f)


def get_smartsheet_client(scopes):
    """
    Initializes the Smartsheet client, handling OAuth 2.0 authentication.
    If a saved refresh token exists, it refreshes the access token.
    Otherwise, it initiates the manual OAuth flow to get the initial tokens.
    """

    # We'll only create the SDK client after we have a valid access token
    smart = None

    # 1. Check for stored tokens
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, 'r') as f:
                token_data = json.load(f)
                access = token_data.get('accessToken')
                refresh = token_data.get('refreshToken')
                if access:
                    # Instantiate client with the existing access token (prefer constructor)
                    try:
                        smart = smartsheet.Smartsheet(access)
                    except Exception:
                        try:
                            smart = smartsheet.Smartsheet(access_token=access)
                        except Exception:
                            # Fallback: create empty client and set attribute directly
                            smart = smartsheet.Smartsheet()
                            try:
                                setattr(smart, 'access_token', access)
                            except Exception:
                                # If we cannot set attribute, ignore; we'll recreate later when needed
                                pass

                if refresh:
                    # Attempt to refresh tokens using HTTP API
                    logging.info("Attempting to refresh token using saved refresh token...")
                    try:
                        new = refresh_tokens(refresh)
                        access = new.get('access_token') or new.get('accessToken')
                        refresh = new.get('refresh_token') or new.get('refreshToken')
                        if access:
                            # Recreate client with the new access token, or set attribute
                            try:
                                smart = smartsheet.Smartsheet(access)
                            except Exception:
                                try:
                                    smart = smartsheet.Smartsheet(access_token=access)
                                except Exception:
                                    if smart is None:
                                        smart = smartsheet.Smartsheet()
                            try:
                                setattr(smart, 'access_token', access)
                            except Exception:
                                pass
                        save_tokens(access, refresh)
                        logging.info("Token refresh successful.")
                        return smart
                    except Exception as e:
                        logging.warning(f"Refresh failed: {e}. Will start new auth flow.")
        except Exception as e:
            logging.warning(f"Failed to use stored token: {e}. Initiating manual flow.")

    # 2. Authorization Flow (automatic local callback with manual fallback)
    logging.info("Starting new OAuth 2.0 authorization flow.")

    auth_url = build_auth_url(scopes, state='1234')

    print("\n--- AUTHORIZATION REQUIRED ---")
    print("Opening browser to the authorization URL. If it doesn't open, copy/paste the URL below into your browser:")
    print(auth_url)

    # Try to open the browser automatically
    try:
        webbrowser.open(auth_url)
    except Exception:
        logging.warning("Failed to open web browser automatically. Please open the URL above manually.")

    # Start a tiny HTTP server to capture the redirect with the authorization code
    auth_code = None

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal auth_code
            parsed = urlparse(self.path)
            if parsed.path == urlparse(REDIRECT_URI).path:
                qs = parse_qs(parsed.query)
                if 'code' in qs:
                    auth_code = qs['code'][0]
                    # Respond to browser
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(b"<html><body><h2>Authorization successful. You can close this window.</h2></body></html>")
                    # Shutdown server after sending response
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

    # Try to bind to the host/port in REDIRECT_URI
    parsed_redirect = urlparse(REDIRECT_URI)
    server_address = (parsed_redirect.hostname or 'localhost', parsed_redirect.port or 8080)

    try:
        httpd = HTTPServer(server_address, CallbackHandler)
        logging.info(f"Listening for OAuth callback on http://{server_address[0]}:{server_address[1]}{parsed_redirect.path}")
        # This will handle a single request then return
        httpd.handle_request()
    except OSError as e:
        logging.warning(f"Could not start local HTTP server on {server_address}: {e}. Falling back to manual copy/paste.")
        httpd = None

    # If automatic callback failed or did not yield a code, ask for manual input
    if not auth_code:
        auth_code = input("\nIf your browser did not redirect here, paste the 'code' parameter from the redirect URL (or press Enter to cancel): ").strip()
        if not auth_code:
            logging.error("No authorization code provided. Aborting.")
            return None

    # Exchange the code for the tokens via HTTP
    try:
        token_info = exchange_code_for_tokens(auth_code)
        access = token_info.get('access_token') or token_info.get('accessToken')
        refresh = token_info.get('refresh_token') or token_info.get('refreshToken')

        # Save the tokens
        save_tokens(access, refresh)
        logging.info("Initial token exchange successful. Tokens saved.")

        # Ensure SDK client exists and set token
        if not access:
            logging.error("Token response did not include access token.")
            return None

        if smart is None:
            try:
                smart = smartsheet.Smartsheet(access)
            except Exception:
                try:
                    smart = smartsheet.Smartsheet(access_token=access)
                except Exception:
                    # fallback to empty client
                    smart = smartsheet.Smartsheet()

        try:
            setattr(smart, 'access_token', access)
        except Exception as se:
            logging.error(f"Failed to set access token on client: {se}")
            return None

        return smart
    except Exception as e:
        logging.error(f"Failed to exchange code for tokens: {e}")
        return None
    
def workspace_deletion_process(client, sheet_id):
    # Run the workspace deletion logic
    try:
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



# --- Example Usage ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    # Define the permissions (scopes) required by your application.
    required_scopes = [
        'READ_USERS', 'READ_SHEETS', 'WRITE_SHEETS',
        'DELETE_SHEETS', 'ADMIN_WORKSPACES', "SHARE_SHEETS", "SHARE_SIGHTS"
    ]

    # Get the authenticated Smartsheet client
    client = get_smartsheet_client(required_scopes)

    if client:
        logging.info("\nSuccessfully authenticated with OAuth 2.0!")
        # Quick verification: get the current user to confirm token works
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
    else:
        logging.error("\nAuthentication failed. Check logs for details.")

    # You can now use 'client' for your automation tasks (e.g., deleting workspaces)
    # Testing workspace deletion process (uncomment to run)
    print("\n--- Running Workspace Deletion Process ---")
    workspace_deletion_process(client, os.getenv('PROD_TEST_SHEET'))