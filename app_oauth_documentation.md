# Smartsheet OAuth Helper Documentation

## Overview

`app_oauth.py` is a Python script that handles OAuth 2.0 authentication with Smartsheet's API. It provides automated token management including:
- Initial OAuth authorization (opens browser, captures code via local callback)
- Token exchange (code → access + refresh tokens)
- Token persistence (saves to local JSON file)
- Automatic token refresh
- Safe Smartsheet SDK client initialization

## Configuration

### Environment Variables
```bash
SM_CLIENT_ID      # Your Smartsheet app's client ID
SM_CLIENT_SECRET  # Your Smartsheet app's client secret
```

### Constants
```python
REDIRECT_URI = "http://localhost:8080/callback"  # Must match app registration
TOKEN_FILE = "smartsheet_token.json"  # Local token storage
AUTH_BASE = "https://app.smartsheet.com/b/authorize"
TOKEN_URL = "https://api.smartsheet.com/2.0/token"
```

## Key Functions

### `build_auth_url(scopes, state='state123')`
Constructs the Smartsheet authorization URL.
- **Args:**
  - `scopes`: List/tuple of scope strings or single scope string
  - `state`: OAuth state parameter (default: 'state123')
- **Returns:** Complete authorization URL string

### `exchange_code_for_tokens(code)`
Exchanges authorization code for access/refresh tokens.
- **Args:**
  - `code`: Authorization code from OAuth redirect
- **Returns:** Dict with access_token and refresh_token
- **Note:** Uses certifi for SSL verification, 15s timeout

### `refresh_tokens(refresh_token)`
Gets new access token using refresh token.
- **Args:**
  - `refresh_token`: Valid refresh token
- **Returns:** Dict with new access_token and refresh_token
- **Note:** Uses certifi for SSL verification, 15s timeout

### `save_tokens(access_token, refresh_token)`
Persists tokens to local JSON file.
- **Args:**
  - `access_token`: Current access token
  - `refresh_token`: Current refresh token
- **Saves to:** TOKEN_FILE (smartsheet_token.json)

### `get_smartsheet_client(scopes)`
Main orchestration function - handles full OAuth flow and returns SDK client.
- **Args:**
  - `scopes`: Required API permission scopes
- **Returns:** Authenticated smartsheet.Smartsheet client or None
- **Flow:**
  1. Checks for saved tokens in TOKEN_FILE
  2. If refresh token exists, attempts refresh
  3. If refresh fails or no tokens, starts new auth:
     - Opens browser to auth URL
     - Runs local HTTP server for callback
     - Falls back to manual code entry if needed
     - Exchanges code for tokens
     - Saves new tokens
  4. Creates and configures SDK client
     - Tries multiple constructor signatures
     - Falls back to direct attribute setting
     - Handles SDK version differences

## Usage Example

```python
# Initialize logging (optional but recommended)
logging.basicConfig(level=logging.INFO)

# Define required scopes
scopes = ['READ_USERS', 'READ_SHEETS', 'WRITE_SHEETS']

# Get authenticated client
client = get_smartsheet_client(scopes)
if client:
    # Use the client
    user = client.Users.get_current_user()
    print(f"Authenticated as: {user.email}")
```

## Security Notes

1. **Token Storage:**
   - Tokens are stored in plain text (smartsheet_token.json)
   - For production, use a secure secret store (e.g., AWS Secrets Manager)

2. **SSL Verification:**
   - Uses certifi's CA bundle for HTTPS requests
   - Never disable SSL verification in production

3. **Credential Security:**
   - Prefer environment variables for CLIENT_ID/SECRET
   - Don't commit credentials to source control

## Error Handling

The script includes comprehensive error handling for:
- SSL certificate issues (uses certifi)
- Network timeouts (15s timeout on requests)
- SDK version differences (multiple client creation methods)
- Browser launch failures (manual code entry fallback)
- Token refresh failures (falls back to new auth)
- Server binding issues (falls back to manual flow)

## Dependencies

Required packages (see requirements.txt):
```
smartsheet-python-sdk
requests
certifi
```

## Common Issues & Solutions

1. **SSL Verification Errors:**
   - Error: `certificate verify failed`
   - Solution: Script uses certifi; ensure Python has access to system CA certs

2. **SDK Compatibility:**
   - Issue: Different SDK versions handle client creation differently
   - Solution: Script tries multiple methods to set access token

3. **Browser/Server Issues:**
   - Problem: Can't open browser or bind to port
   - Solution: Falls back to manual authorization flow

## AWS Lambda Adaptation

To use in AWS Lambda:
1. Run locally once to get initial refresh token
2. Store refresh token in AWS Secrets Manager
3. Modify script to:
   - Remove browser/server components
   - Read refresh token from Secrets Manager
   - Use token refresh flow only

## Reference Links

- [Smartsheet API Documentation](https://smartsheet.redoc.ly/)
- [Smartsheet OAuth 2.0 Flow](https://smartsheet.redoc.ly/docs/api/oauth2-authorization/)
- [Python SDK Documentation](https://github.com/smartsheet-platform/smartsheet-python-sdk)