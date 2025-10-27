# Deep Dive: Understanding OAuth Implementation with Smartsheet

## Part 1: OAuth Fundamentals

### Why OAuth?

Before diving into the code, let's understand why we need OAuth and why not just use API keys:

1. **Security Benefits**:
   - API keys are permanent and risky if leaked
   - OAuth tokens expire automatically
   - Refresh tokens can be revoked
   - No need to store sensitive credentials

2. **Controlled Access**:
   - Users explicitly grant only needed permissions
   - Permissions can be revoked by users
   - Different tokens for different access levels
   - Clear audit trail of who granted what

3. **Better User Experience**:
   - Users authenticate with their existing accounts
   - No need to create/manage API keys
   - Automatic token refresh without user intervention
   - Works across multiple devices/locations

4. **Industry Standard**:
   - Well-documented security practices
   - Widely supported by tools and libraries
   - Similar pattern works with Google, GitHub, etc.
   - Regular security updates and improvements

### OAuth Tokens Explained

1. **Access Token**:
   - Short-lived (usually hours)
   - Used for API calls
   - Like a temporary ID badge
   - Example:
     ```
     eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
     ```

2. **Refresh Token**:
   - Long-lived (days/months)
   - Used to get new access tokens
   - Like a membership card
   - Must be stored securely
   - Example:
     ```
     1//04dxJ8YkFWKWpGCgYIARAAGAQSNwF-L9...
     ```

3. **Authorization Code**:
   - Very short-lived (minutes)
   - One-time use
   - Exchanged for tokens
   - Example:
     ```
     4/0AZQhGXv-CguD1ZjD6q0fYXoEqG8j_Qu...
     ```

### Practical OAuth Flow

Real-world example of what happens when you click "Login with Google":

1. **Request Authorization**:
   ```
   https://app.smartsheet.com/b/authorize?
     response_type=code
     &client_id=your_app_id
     &scope=READ_SHEETS+WRITE_SHEETS
     &redirect_uri=http://localhost:8080/callback
     &state=random123
   ```

2. **User Consents**:
   - Sees Smartsheet login page
   - Reviews permissions
   - Clicks "Allow"

3. **Get Authorization Code**:
   ```
   http://localhost:8080/callback?
     code=4/abc123...
     &state=random123
   ```

4. **Exchange for Tokens**:
   ```http
   POST https://api.smartsheet.com/2.0/token
   Content-Type: application/x-www-form-urlencoded

   grant_type=authorization_code
   &code=4/abc123...
   &client_id=your_app_id
   &client_secret=your_app_secret
   &redirect_uri=http://localhost:8080/callback
   ```

5. **Response with Tokens**:
   ```json
   {
     "access_token": "eyJ0eXAi...",
     "refresh_token": "1//04dx...",
     "expires_in": 3600,
     "token_type": "Bearer"
   }
   ```

## Part 2: Implementation Deep-Dive

### A. Setting Up Your Development Environment

1. **Prerequisites**:
   ```bash
   # Create a virtual environment
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate

   # Install required packages
   pip install smartsheet-python-sdk requests certifi

   # Set environment variables (macOS/Linux)
   export SM_CLIENT_ID="your_client_id"
   export SM_CLIENT_SECRET="your_client_secret"

   # Or on Windows PowerShell
   $env:SM_CLIENT_ID="your_client_id"
   $env:SM_CLIENT_SECRET="your_client_secret"
   ```

2. **Smartsheet App Setup**:
   - Go to https://app.smartsheet.com/apps/home
   - Click "Create New App"
   - Set Application Name (e.g., "Workspace Manager")
   - Add redirect URL: `http://localhost:8080/callback`
   - Copy Client ID and Secret

### B. OAuth 2.0 Flow Visualization

```
┌──────────────┐         ┌───────────────┐         ┌─────────────┐
│              │         │               │         │             │
│  Our Script  │         │   Browser     │         │  Smartsheet │
│              │         │               │         │             │
└──────┬───────┘         └───────┬───────┘         └──────┬──────┘
       │                         │                         │
       │                         │                         │
       │ 1. Open Browser         │                         │
       │─────────────────────────>                         │
       │                         │                         │
       │                         │ 2. User Logs In         │
       │                         │────────────────────────>│
       │                         │                         │
       │                         │ 3. User Grants Access   │
       │                         │────────────────────────>│
       │                         │                         │
       │                         │ 4. Redirect with Code   │
       │                         │<────────────────────────│
       │                         │                         │
       │ 5. Capture Code         │                         │
       │<────────────────────────│                         │
       │                         │                         │
       │ 6. Exchange Code        │                         │
       │──────────────────────────────────────────────────>│
       │                         │                         │
       │ 7. Get Tokens          │                         │
       │<──────────────────────────────────────────────────│
       │                         │                         │
```

## Part 3: Code Architecture and Implementation

### A. Project Structure

```
smartsheet_workspace/
├── app_oauth.py          # Main OAuth handler
├── smartsheet_token.json # Token storage (git-ignored)
├── requirements.txt      # Dependencies
└── .env                 # Environment variables (git-ignored)
```

### B. Code Organization Strategy

1. **Separation of Concerns**:
   ```python
   # 1. Configuration
   CLIENT_ID, CLIENT_SECRET, etc.

   # 2. Core OAuth Functions
   build_auth_url()
   exchange_code_for_tokens()
   refresh_tokens()

   # 3. Token Management
   save_tokens()
   load_tokens()

   # 4. HTTP Server
   class CallbackHandler()

   # 5. Client Management
   get_smartsheet_client()
   ```

2. **Error Handling Hierarchy**:
   ```python
   try:
       # Level 1: Token Operations
       try:
           tokens = load_tokens()
       except FileNotFoundError:
           # Handle missing token file
       
       # Level 2: Token Refresh
       try:
           new_tokens = refresh_tokens(tokens['refresh'])
       except requests.RequestException:
           # Handle network/API errors
       
       # Level 3: Client Creation
       try:
           client = create_client(new_tokens['access'])
       except Exception:
           # Handle SDK issues
   except Exception as e:
       logging.error(f"Top-level error: {e}")
   ```

### C. Initial Setup and Dependencies

```python
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
```

Each import serves a specific purpose:
- `smartsheet`: The official SDK for API interaction
- `requests`: For manual HTTP calls (token exchange)
- `certifi`: Provides trusted CA certificates for SSL
- `http.server`: Runs local server to catch the OAuth redirect
- `threading`: Handles server shutdown without blocking

### 2. Configuration Management

```python
CLIENT_ID = os.getenv('SM_CLIENT_ID', "your_client_id")
CLIENT_SECRET = os.getenv('SM_CLIENT_SECRET', "your_client_secret")
REDIRECT_URI = "http://localhost:8080/callback"
TOKEN_FILE = "smartsheet_token.json"
```

Why these choices?
- Environment variables: Secure way to inject credentials
- Local callback: Catches OAuth response automatically
- Token file: Persists refresh token for reuse

### 3. The Authorization Flow

#### Step 1: Building the Auth URL
```python
def build_auth_url(scopes, state='state123'):
    """Construct the Smartsheet authorization URL."""
    scope_str = "+".join(scopes) if isinstance(scopes, (list, tuple)) else scopes
    params = (
        f"response_type=code&client_id={CLIENT_ID}"
        f"&scope={scope_str}&redirect_uri={REDIRECT_URI}&state={state}"
    )
    return f"{AUTH_BASE}?{params}"
```

This creates the URL where users grant permission. The parameters are:
- `response_type=code`: We want an authorization code
- `client_id`: Identifies our application
- `scope`: What permissions we need
- `redirect_uri`: Where to send the code
- `state`: Security parameter to prevent CSRF

#### Step 2: Capturing the Authorization Code

```python
class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        nonlocal auth_code
        parsed = urlparse(self.path)
        if parsed.path == urlparse(REDIRECT_URI).path:
            qs = parse_qs(parsed.query)
            if 'code' in qs:
                auth_code = qs['code'][0]
```

Why a local server?
1. Automatic code capture (no copy/paste)
2. Better user experience
3. Fallback to manual if needed

#### Step 3: Token Exchange

```python
def exchange_code_for_tokens(code):
    """Exchange authorization code for access and refresh tokens."""
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'redirect_uri': REDIRECT_URI,
    }
    resp = requests.post(TOKEN_URL, data=data, verify=certifi.where(), timeout=15)
```

Key points:
- Uses `requests` instead of SDK (more control)
- Proper SSL verification with certifi
- Timeout to prevent hanging
- Includes all required OAuth parameters

### 4. Token Management

```python
def refresh_tokens(refresh_token):
    """Use a refresh token to obtain a new access token."""
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
    }
    resp = requests.post(TOKEN_URL, data=data, verify=certifi.where(), timeout=15)
```

Why refresh tokens?
1. Access tokens expire quickly (security)
2. Refresh tokens let us get new access tokens
3. Users don't need to re-authorize

### 5. Safe Token Storage

```python
def save_tokens(access_token, refresh_token):
    """Saves the access and refresh tokens to a file."""
    token_data = {
        "accessToken": access_token,
        "refreshToken": refresh_token
    }
    with open(TOKEN_FILE, 'w') as f:
        json.dump(token_data, f)
```

Development vs Production:
- Development: Local JSON file (simple)
- Production: Use AWS Secrets Manager or similar
- Never commit tokens to git

### 6. Client Creation Strategy

The `get_smartsheet_client` function uses a multi-step strategy:

1. Try to use saved tokens:
```python
if os.path.exists(TOKEN_FILE):
    with open(TOKEN_FILE, 'r') as f:
        token_data = json.load(f)
```

2. Try to refresh if possible:
```python
if refresh:
    new = refresh_tokens(refresh)
    access = new.get('access_token')
```

3. Fall back to new authorization if needed:
```python
auth_url = build_auth_url(scopes)
webbrowser.open(auth_url)
```

4. Safe client creation with multiple attempts:
```python
try:
    smart = smartsheet.Smartsheet(access)
except Exception:
    try:
        smart = smartsheet.Smartsheet(access_token=access)
    except Exception:
        smart = smartsheet.Smartsheet()
        setattr(smart, 'access_token', access)
```

## Part 4: Troubleshooting & Real-World Scenarios

### A. Common Issues and Solutions

1. **SSL Certificate Problems**:
   ```
   Problem: ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED]
   ```

   Diagnosis Steps:
   ```python
   import ssl
   print(ssl.get_default_verify_paths())
   ```

   Solutions:
   ```python
   # Solution 1: Use certifi (preferred)
   import certifi
   requests.post(url, verify=certifi.where())

   # Solution 2: Update certificates
   # On macOS:
   # /Applications/Python 3.x/Install Certificates.command

   # Solution 3: Debug with verbose SSL
   import requests.packages.urllib3
   requests.packages.urllib3.add_stderr_logger()
   ```

2. **Token Refresh Failures**:
   ```
   Problem: {"error": "invalid_grant"}
   ```

   Debug Steps:
   ```python
   # 1. Check token format
   import jwt
   try:
       jwt.decode(token, options={"verify_signature": False})
   except jwt.InvalidTokenError as e:
       print(f"Invalid token format: {e}")

   # 2. Check expiration
   def is_token_expired(token_data):
       if 'expiresAt' not in token_data:
           return True
       return time.time() > token_data['expiresAt']

   # 3. Validate refresh attempt
   def debug_refresh(refresh_token):
       response = requests.post(
           TOKEN_URL,
           data={'refresh_token': refresh_token, ...},
           verify=certifi.where()
       )
       print(f"Status: {response.status_code}")
       print(f"Response: {response.text}")
   ```

3. **SDK Version Conflicts**:
   ```
   Problem: AttributeError: 'Smartsheet' object has no attribute 'set_access_token'
   ```

   Version Check:
   ```python
   import smartsheet
   print(f"SDK Version: {smartsheet.__version__}")
   ```

   Compatibility Layer:
   ```python
   def set_token_safely(client, token):
       methods = [
           # Method 1: Constructor
           lambda: smartsheet.Smartsheet(token),
           
           # Method 2: Keyword arg
           lambda: smartsheet.Smartsheet(access_token=token),
           
           # Method 3: Attribute
           lambda: setattr(client, 'access_token', token),
           
           # Method 4: Legacy method
           lambda: client.set_access_token(token)
       ]
       
       for method in methods:
           try:
               result = method()
               return result if result else client
           except Exception as e:
               logging.debug(f"Method failed: {e}")
       
       raise ValueError("All token setting methods failed")
   ```

### B. Real-World Scenarios

Problem:
```
ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED]
```

Solution in our code:
```python
requests.post(TOKEN_URL, verify=certifi.where(), timeout=15)
```

Why? MacOS Python might not find system certificates. Certifi provides a trusted bundle.

### 2. SDK Version Differences

Problem: Different versions accept tokens differently

Solution: Try multiple methods:
```python
# Try 1: Positional arg
smart = smartsheet.Smartsheet(access)

# Try 2: Keyword arg
smart = smartsheet.Smartsheet(access_token=access)

# Try 3: Set attribute
smart = smartsheet.Smartsheet()
setattr(smart, 'access_token', access)
```

### 3. Local Server Binding

Problem: Port 8080 might be in use

Solution: Fallback to manual entry:
```python
if not auth_code:
    auth_code = input("\nPaste the 'code' parameter: ")
```

## Production Considerations

## Part 5: Production Deployment

### A. AWS Lambda Integration

1. **Lambda-Compatible Version**:
   ```python
   import boto3
   import json
   import smartsheet
   import requests
   import certifi
   from botocore.exceptions import ClientError

   def get_secret():
       """Get tokens from AWS Secrets Manager."""
       session = boto3.session.Session()
       client = session.client('secretsmanager')
       try:
           response = client.get_secret_value(
               SecretId='smartsheet/tokens'
           )
           return json.loads(response['SecretString'])
       except ClientError as e:
           logging.error(f"Failed to get secret: {e}")
           raise

   def update_secret(token_data):
       """Update tokens in AWS Secrets Manager."""
       client = boto3.client('secretsmanager')
       try:
           client.update_secret_value(
               SecretId='smartsheet/tokens',
               SecretString=json.dumps(token_data)
           )
       except ClientError as e:
           logging.error(f"Failed to update secret: {e}")
           raise

   def lambda_handler(event, context):
       """AWS Lambda entry point."""
       try:
           # Get tokens from Secrets Manager
           token_data = get_secret()
           
           # Try to refresh if needed
           if is_token_expired(token_data):
               new_tokens = refresh_tokens(
                   token_data['refreshToken']
               )
               token_data.update(new_tokens)
               update_secret(token_data)
           
           # Create Smartsheet client
           client = smartsheet.Smartsheet(
               token_data['accessToken']
           )
           
           # Your workspace deletion logic here
           # ...
           
           return {
               'statusCode': 200,
               'body': json.dumps('Success')
           }
       except Exception as e:
           logging.error(f"Lambda execution failed: {e}")
           return {
               'statusCode': 500,
               'body': json.dumps(str(e))
           }
   ```

2. **IAM Role Configuration**:
   ```json
   {
       "Version": "2012-10-17",
       "Statement": [
           {
               "Effect": "Allow",
               "Action": [
                   "secretsmanager:GetSecretValue",
                   "secretsmanager:UpdateSecret"
               ],
               "Resource": [
                   "arn:aws:secretsmanager:region:account:secret:smartsheet/*"
               ]
           }
       ]
   }
   ```

3. **Environment Variables**:
   ```bash
   # Lambda environment variables
   SM_CLIENT_ID=your_client_id
   SM_CLIENT_SECRET=your_client_secret
   LOG_LEVEL=INFO
   ```

4. **Initial Token Setup**:
   ```python
   def initialize_lambda_tokens():
       """Run this locally to set up initial tokens."""
       # Get tokens using local OAuth flow
       client = get_smartsheet_client(scopes)
       tokens = {
           'accessToken': client.access_token,
           'refreshToken': get_refresh_token(),
           'expiresAt': time.time() + 3600
       }
       
       # Create secret in AWS
       client = boto3.client('secretsmanager')
       client.create_secret(
           Name='smartsheet/tokens',
           SecretString=json.dumps(tokens)
       )
   ```

### B. Security Best Practices

Add:
```python
import boto3

def get_secret():
    session = boto3.session.Session()
    client = session.client('secretsmanager')
    return client.get_secret_value(
        SecretId='smartsheet/tokens'
    )
```

### B. Security Best Practices

1. **Token Storage**:
   ```python
   # BAD: Plain file storage
   with open('tokens.json', 'w') as f:
       json.dump(token_data, f)  # Don't do this!

   # GOOD: Encrypted storage
   from cryptography.fernet import Fernet
   
   def save_tokens_securely(token_data):
       key = Fernet.generate_key()
       f = Fernet(key)
       encrypted = f.encrypt(json.dumps(token_data).encode())
       # Store key in environment or secrets manager
       os.environ['ENCRYPTION_KEY'] = key.decode()
       # Store encrypted data
       with open('tokens.encrypted', 'wb') as f:
           f.write(encrypted)
   ```

2. **Input Validation**:
   ```python
   def validate_token_response(response):
       """Validate token response format."""
       required = {'access_token', 'refresh_token', 'expires_in'}
       if not all(k in response for k in required):
           raise ValueError("Invalid token response format")
       
       if not isinstance(response['expires_in'], int):
           raise ValueError("Invalid expiry format")
       
       if len(response['access_token']) < 20:
           raise ValueError("Suspiciously short token")
   ```

3. **Rate Limiting**:
   ```python
   from functools import wraps
   import time

   def rate_limit(max_per_minute):
       calls = []
       
       def decorator(func):
           @wraps(func)
           def wrapper(*args, **kwargs):
               now = time.time()
               # Remove old calls
               while calls and calls[0] < now - 60:
                   calls.pop(0)
               # Check rate limit
               if len(calls) >= max_per_minute:
                   raise Exception("Rate limit exceeded")
               # Make call
               calls.append(now)
               return func(*args, **kwargs)
           return wrapper
       return decorator

   @rate_limit(max_per_minute=300)
   def exchange_code_for_tokens(code):
       # ... existing code ...
   ```

4. **Logging Best Practices**:
   ```python
   import logging.config

   logging_config = {
       'version': 1,
       'disable_existing_loggers': False,
       'formatters': {
           'standard': {
               'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
           },
       },
       'handlers': {
           'default': {
               'level': 'INFO',
               'formatter': 'standard',
               'class': 'logging.StreamHandler',
           },
           'file': {
               'level': 'INFO',
               'formatter': 'standard',
               'class': 'logging.FileHandler',
               'filename': 'oauth.log',
               'mode': 'a',
           },
       },
       'loggers': {
           '': {  # root logger
               'handlers': ['default', 'file'],
               'level': 'INFO',
               'propagate': True
           },
           'sensitive': {  # for sensitive operations
               'handlers': ['file'],
               'level': 'INFO',
               'propagate': False
           },
       }
   }

   logging.config.dictConfig(logging_config)
   logger = logging.getLogger(__name__)
   sensitive_logger = logging.getLogger('sensitive')
   ```

### C. Monitoring and Alerting

Production (AWS):
```python
client = boto3.client('secretsmanager')
client.put_secret_value(
    SecretId='smartsheet/tokens',
    SecretString=json.dumps(token_data)
)
```

## Part 6: Monitoring and Maintenance

### A. Health Checks and Monitoring

1. **Token Health Check**:
   ```python
   def check_token_health(token_data):
       """
       Check token health and return status.
       Returns: (bool, str) - (is_healthy, description)
       """
       checks = []
       
       # 1. Check token presence
       checks.append(
           ('has_tokens', bool(token_data.get('accessToken')))
       )
       
       # 2. Check expiration
       if 'expiresAt' in token_data:
           time_left = token_data['expiresAt'] - time.time()
           checks.append(
               ('not_expired', time_left > 0)
           )
           checks.append(
               ('expiry_warning', time_left > 600)  # 10 min buffer
           )
       
       # 3. Verify token format
       try:
           jwt.decode(
               token_data['accessToken'],
               options={"verify_signature": False}
           )
           checks.append(('valid_format', True))
       except:
           checks.append(('valid_format', False))
       
       # 4. Test API call
       try:
           client = smartsheet.Smartsheet(token_data['accessToken'])
           client.Users.get_current_user()
           checks.append(('api_working', True))
       except:
           checks.append(('api_working', False))
       
       # Summarize health
       is_healthy = all(result for _, result in checks)
       details = ', '.join(
           f"{name}={'✓' if result else '✗'}"
           for name, result in checks
       )
       
       return is_healthy, details
   ```

2. **AWS CloudWatch Metrics**:
   ```python
   def report_metrics(token_data):
       """Send metrics to CloudWatch."""
       client = boto3.client('cloudwatch')
       
       # Token expiry metric
       if 'expiresAt' in token_data:
           time_left = token_data['expiresAt'] - time.time()
           client.put_metric_data(
               Namespace='Smartsheet/OAuth',
               MetricData=[{
                   'MetricName': 'TokenExpirySeconds',
                   'Value': time_left,
                   'Unit': 'Seconds'
               }]
           )
       
       # API call success rate
       try:
           smartsheet.Smartsheet(token_data['accessToken'])
           value = 1
       except:
           value = 0
       
       client.put_metric_data(
           Namespace='Smartsheet/OAuth',
           MetricData=[{
               'MetricName': 'APISuccess',
               'Value': value,
               'Unit': 'Count'
           }]
       )
   ```

3. **Alert Configuration**:
   ```python
   def configure_alerts():
       """Set up CloudWatch alarms."""
       client = boto3.client('cloudwatch')
       
       # Token expiry alarm
       client.put_metric_alarm(
           AlarmName='TokenNearExpiry',
           MetricName='TokenExpirySeconds',
           Namespace='Smartsheet/OAuth',
           Period=300,
           EvaluationPeriods=1,
           Threshold=900,  # 15 minutes
           ComparisonOperator='LessThanThreshold',
           AlarmActions=['arn:aws:sns:...']
       )
       
       # API failure alarm
       client.put_metric_alarm(
           AlarmName='APIFailure',
           MetricName='APISuccess',
           Namespace='Smartsheet/OAuth',
           Period=300,
           EvaluationPeriods=2,
           Threshold=1,
           ComparisonOperator='LessThanThreshold',
           AlarmActions=['arn:aws:sns:...']
       )
   ```

### B. Maintenance Tasks
```python
try:
    current = client.Users.get_current_user()
    print(f"Authenticated as: {current.email}")
except Exception as e:
    print(f"Verification failed: {e}")
```

### Logging for Debugging
```python
logging.info("Attempting to refresh token...")
logging.warning("Refresh failed. Starting new auth...")
logging.error("Failed to exchange code for tokens")
```

### B. Maintenance Tasks

1. **Regular Token Rotation**:
   ```python
   def rotate_refresh_token():
       """
       Proactively rotate refresh token.
       Best practice: rotate every 30-90 days.
       """
       token_data = get_secret()
       
       # Force a new token exchange
       new_tokens = refresh_tokens(
           token_data['refreshToken']
       )
       
       # Update storage
       token_data.update(new_tokens)
       update_secret(token_data)
       
       # Log rotation
       logging.info(
           f"Rotated refresh token. Valid until: "
           f"{time.ctime(token_data['expiresAt'])}"
       )
   ```

2. **Automated Testing**:
   ```python
   import pytest
   import responses  # for mocking HTTP requests

   @pytest.fixture
   def mock_token_response():
       """Mock token endpoint responses."""
       with responses.RequestsMock() as rsps:
           rsps.add(
               responses.POST,
               'https://api.smartsheet.com/2.0/token',
               json={
                   'access_token': 'test_access',
                   'refresh_token': 'test_refresh',
                   'expires_in': 3600
               }
           )
           yield rsps

   def test_token_refresh(mock_token_response):
       """Test token refresh flow."""
       result = refresh_tokens('old_refresh_token')
       assert 'access_token' in result
       assert 'refresh_token' in result
       assert result['expires_in'] == 3600
   ```

3. **Health Check Lambda**:
   ```python
   def health_check_handler(event, context):
       """
       Separate Lambda to monitor token health.
       Run every 5 minutes via CloudWatch Events.
       """
       try:
           # Get current tokens
           token_data = get_secret()
           
           # Check health
           is_healthy, details = check_token_health(token_data)
           
           # Report metrics
           report_metrics(token_data)
           
           # Handle unhealthy state
           if not is_healthy:
               # Attempt refresh
               try:
                   new_tokens = refresh_tokens(
                       token_data['refreshToken']
                   )
                   token_data.update(new_tokens)
                   update_secret(token_data)
                   
                   # Recheck health
                   is_healthy, details = check_token_health(
                       token_data
                   )
               except Exception as e:
                   details += f" (Refresh failed: {e})"
           
           return {
               'statusCode': 200 if is_healthy else 500,
               'body': {
                   'healthy': is_healthy,
                   'details': details,
                   'timestamp': time.time()
               }
           }
       
       except Exception as e:
           logging.error(f"Health check failed: {e}")
           return {
               'statusCode': 500,
               'body': {'error': str(e)}
           }
   ```

## Part 7: Future Improvements

1. **Enhanced Security**:
   ```python
   # 1. Token Encryption at Rest
   def encrypt_token_data(token_data, kms_key_id):
       client = boto3.client('kms')
       encrypted = client.encrypt(
           KeyId=kms_key_id,
           Plaintext=json.dumps(token_data)
       )
       return encrypted['CiphertextBlob']

   # 2. Token Validation
   def validate_token(token):
       if not token.strip():
           raise ValueError("Empty token")
       
       try:
           decoded = jwt.decode(
               token,
               options={"verify_signature": False}
           )
           
           # Check claims
           if 'exp' in decoded:
               if decoded['exp'] < time.time():
                   raise ValueError("Token expired")
           
           # Check permissions
           if 'scope' in decoded:
               required = {'READ_SHEETS', 'WRITE_SHEETS'}
               scopes = set(decoded['scope'].split())
               if not required.issubset(scopes):
                   raise ValueError("Missing required scopes")
       
       except jwt.InvalidTokenError as e:
           raise ValueError(f"Invalid token format: {e}")
   ```

2. **Improved Error Recovery**:
   ```python
   class TokenError(Exception):
       """Custom exception for token-related errors."""
       pass

   class RefreshError(TokenError):
       """Failed to refresh token."""
       pass

   def safe_refresh(refresh_token, max_retries=3):
       """Refresh with retry and exponential backoff."""
       for attempt in range(max_retries):
           try:
               return refresh_tokens(refresh_token)
           except requests.RequestException as e:
               if attempt == max_retries - 1:
                   raise RefreshError(f"Max retries exceeded: {e}")
               time.sleep(2 ** attempt)  # Exponential backoff
   ```

3. **Advanced Monitoring**:
   ```python
   def track_token_metrics():
       """Track detailed token usage metrics."""
       metrics = []
       
       def track(func):
           @wraps(func)
           def wrapper(*args, **kwargs):
               start = time.time()
               try:
                   result = func(*args, **kwargs)
                   success = True
               except Exception as e:
                   success = False
                   raise
               finally:
                   duration = time.time() - start
                   metrics.append({
                       'function': func.__name__,
                       'duration': duration,
                       'success': success,
                       'timestamp': time.time()
                   })
               return result
           return wrapper
       
       return track
   ```

## Resources and Further Reading

1. **OAuth Documentation**:
   - [OAuth 2.0 RFC](https://tools.ietf.org/html/rfc6749)
   - [OAuth Security Best Practices](https://tools.ietf.org/html/draft-ietf-oauth-security-topics)
   - [Token Best Practices](https://tools.ietf.org/html/draft-ietf-oauth-security-topics#section-3)

2. **AWS Integration**:
   - [AWS Secrets Manager Guide](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html)
   - [Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
   - [CloudWatch Monitoring](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/WhatIsCloudWatch.html)

3. **Python Security**:
   - [Python Security Best Practices](https://snyk.io/blog/python-security-best-practices/)
   - [Cryptography in Python](https://cryptography.io/en/latest/)
   - [Token Storage Security](https://owasp.org/www-community/Secure_Coding_Practices-Quick_Reference_Guide)

4. **Smartsheet API**:
   - [API Documentation](https://smartsheet.redoc.ly/)
   - [OAuth Flow Guide](https://smartsheet.redoc.ly/docs/api/oauth2-authorization/)
   - [Python SDK Reference](https://github.com/smartsheet-platform/smartsheet-python-sdk)
   - [Rate Limiting](https://smartsheet.redoc.ly/docs/api/rate-limiting/)

2. Add token revocation:
```python
def revoke_token(token):
    requests.post(REVOKE_URL, data={
        'token': token,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    })
```

3. Add rate limiting:
```python
from ratelimit import limits, sleep_and_retry

@sleep_and_retry
@limits(calls=300, period=60)
def exchange_code_for_tokens(code):
    # ... existing code ...
```

## Resources

1. [OAuth 2.0 RFC](https://tools.ietf.org/html/rfc6749)
2. [Smartsheet API Auth Guide](https://smartsheet.redoc.ly/docs/api/oauth2-authorization/)
3. [Python Requests Security](https://requests.readthedocs.io/en/latest/user/advanced/#ssl-cert-verification)
4. [AWS Secrets Manager Guide](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html)