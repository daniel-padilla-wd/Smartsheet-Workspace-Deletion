# Smartsheet Workspace Deletion - API Documentation

## Table of Contents
- [Overview](#overview)
- [Architecture](#architecture)
- [Module Reference](#module-reference)
  - [app.py](#apppy)
  - [config.py](#configpy)
  - [oauth_handler.py](#oauth_handlerpy)
  - [repository.py](#repositorypy)
  - [service.py](#servicepy)
  - [utils.py](#utilspy)
- [Data Flow](#data-flow)
- [Error Handling](#error-handling)

## Overview

This application automates the deletion of Smartsheet workspaces based on scheduled deletion dates stored in an intake sheet. It supports both local execution and AWS Lambda deployment with OAuth 2.0 authentication.

### Key Features
- OAuth 2.0 authentication with Smartsheet API
- Automated workspace deletion based on date criteria
- Support for local and AWS Lambda environments
- Token management (local file or AWS Secrets Manager)
- Comprehensive error handling and logging
- Status tracking via Smartsheet cell updates

## Architecture

The application follows a layered architecture:

```
┌─────────────────────────────────────┐
│         app.py (Entry Point)        │
│   - Lambda Handler                  │
│   - Local Execution                 │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│    service.py (Business Logic)      │
│   - WorkspaceDeletionService        │
│   - Workflow Orchestration          │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  repository.py (Data Access Layer)  │
│   - SmartsheetRepository            │
│   - API Operations                  │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│    oauth_handler.py (Auth Layer)    │
│   - OAuth Flow Management           │
│   - Token Storage/Refresh           │
└─────────────────────────────────────┘

         Supporting Modules:
┌─────────────────────────────────────┐
│   config.py (Configuration)         │
│   utils.py (Utilities)              │
└─────────────────────────────────────┘
```

## Module Reference

### app.py

**Purpose:** Application entry point supporting both local and AWS Lambda execution.

#### Functions

##### `main()`
Main execution function for local environment.

**Returns:**
- `dict`: Summary of workflow execution

**Process:**
1. Validates OAuth and sheet configuration
2. Authenticates via OAuth handler
3. Initializes repository and service layers
4. Processes deletion workflow
5. Returns execution summary

**Example Output:**
```python
{
    "processed_rows": 10,
    "successful_deletions": 3,
    "skipped": 7,
    "errors": []
}
```

##### `lambda_handler(event, context)`
AWS Lambda handler function.

**Parameters:**
- `event`: Lambda event object
- `context`: Lambda context object

**Returns:**
- `dict`: Response with statusCode and JSON body

**Example:**
```python
{
    'statusCode': 200,
    'body': '{"processed_rows": 10, "successful_deletions": 3, ...}'
}
```

---

### config.py

**Purpose:** Centralized configuration management using environment variables.

#### Classes

##### `ConfigurationError`
Exception raised when required configuration is missing or invalid.

##### `Config`
Configuration class providing validated access to application settings.

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `DEV_MODE` | bool | Development mode flag |
| `CLIENT_ID` | str | OAuth client ID |
| `CLIENT_SECRET` | str | OAuth client secret |
| `REDIRECT_URI` | str | OAuth callback URL |
| `TOKEN_FILE` | str | Local token storage file path |
| `AUTH_BASE` | str | Smartsheet authorization URL |
| `TOKEN_URL` | str | Token endpoint URL |
| `OAUTH_SCOPES` | List[str] | Required OAuth scopes |
| `S_INTAKE_SHEET_ID` | str | Sandbox intake sheet ID |
| `INTAKE_SHEET_ID` | str | Production intake sheet ID |
| `TIMEZONE` | str | Timezone for date operations |

**Column ID Mappings:**

```python
COLUMN_TITLES = {
    'folder_url': FOLDER_URL_ID,
    'deletion_date': DELETION_DATE_ID,
    'em_notification_date': EM_NOTIFICATION_ID,
    'deletion_status': DELETION_STATUS_ID,
}
```

**Methods:**

##### `validate_oauth_config()`
Validates OAuth configuration presence.

**Raises:**
- `ConfigurationError`: If required OAuth settings are missing

##### `validate_sheet_config()`
Validates sheet configuration presence.

**Raises:**
- `ConfigurationError`: If required sheet settings are missing

##### `validate_all()`
Validates all required configuration.

##### `get_summary()`
Returns configuration summary with masked sensitive values.

**Returns:**
- `dict`: Configuration summary

---

### oauth_handler.py

**Purpose:** Complete OAuth 2.0 authentication flow management.

#### Classes

##### `OAuthCallbackHandler(BaseHTTPRequestHandler)`
HTTP request handler for OAuth callback server.

**Class Variables:**
- `expected_state`: CSRF protection state parameter
- `auth_code`: Authorization code from OAuth callback

**Methods:**
- `do_GET()`: Handles OAuth redirect callback
- `log_message()`: Suppresses HTTP server logging

#### Functions

##### AWS Secrets Manager Functions

##### `get_secret_string(secret_name)`
Retrieves plain string value from AWS Secrets Manager.

**Parameters:**
- `secret_name` (str): Secret name in AWS Secrets Manager

**Returns:**
- `str | None`: Secret value or None if retrieval fails

##### `get_oauth_credentials_from_aws()`
Retrieves OAuth credentials from AWS Secrets Manager.

**Returns:**
- `tuple`: (client_id, client_secret) or (None, None)

##### `save_tokens_to_aws(access_token, refresh_token)`
Saves tokens to AWS Secrets Manager.

**Parameters:**
- `access_token` (str): Current access token
- `refresh_token` (str): Current refresh token

**Returns:**
- `bool`: Success status

**Required IAM Permissions:**
- `secretsmanager:PutSecretValue`
- `secretsmanager:CreateSecret`

##### `load_tokens_from_aws()`
Loads stored tokens from AWS Secrets Manager.

**Returns:**
- `tuple`: (access_token, refresh_token) or (None, None)

##### OAuth Flow Functions

##### `build_auth_url(scopes, state='state123')`
Constructs Smartsheet authorization URL.

**Parameters:**
- `scopes` (List[str] | str): Permission scopes
- `state` (str): CSRF protection state

**Returns:**
- `str`: Complete authorization URL

**Example:**
```python
url = build_auth_url(['READ_SHEETS', 'DELETE_SHEETS'])
# Returns: https://app.smartsheet.com/b/authorize?response_type=code&client_id=...
```

##### `exchange_code_for_tokens(code)`
Exchanges authorization code for access and refresh tokens.

**Parameters:**
- `code` (str): Authorization code from OAuth callback

**Returns:**
- `dict`: Token response

**Example Response:**
```python
{
    "access_token": "abc123...",
    "refresh_token": "xyz789...",
    "token_type": "bearer",
    "expires_in": 604800
}
```

##### `refresh_tokens(refresh_token)`
Obtains new access token using refresh token.

**Parameters:**
- `refresh_token` (str): Valid refresh token

**Returns:**
- `dict`: Token response with new tokens

##### Token Storage Functions

##### `save_tokens(access_token, refresh_token)`
Saves tokens to appropriate storage (AWS or local file).

**Parameters:**
- `access_token` (str): Current access token
- `refresh_token` (str): Current refresh token

**Returns:**
- `bool`: Success status

**Behavior:**
- **AWS Lambda**: Saves to AWS Secrets Manager
- **Local**: Saves to JSON file specified in config

##### `load_tokens()`
Loads stored tokens from appropriate storage.

**Returns:**
- `tuple`: (access_token, refresh_token) or (None, None)

##### Client Management Functions

##### `create_smartsheet_client(access_token)`
Creates authenticated Smartsheet client.

**Parameters:**
- `access_token` (str): Valid access token

**Returns:**
- `smartsheet.Smartsheet`: Authenticated client instance

##### `validate_client(client)`
Validates that a client has working access token.

**Parameters:**
- `client`: Smartsheet client instance

**Returns:**
- `bool`: True if valid, False only for auth errors (401/403)

**Note:** Non-authentication errors (network issues, etc.) return True to avoid refresh loops.

##### `run_oauth_flow(scopes)`
Runs complete OAuth authorization flow with local callback server.

**Parameters:**
- `scopes` (List[str]): Required permission scopes

**Returns:**
- `str | None`: Authorization code or None

**Process:**
1. Generates CSRF state token
2. Opens browser to authorization URL
3. Starts local HTTP server for callback
4. Waits for authorization code
5. Falls back to manual input if needed

##### `get_smartsheet_client(scopes)`
**Main entry point** for authentication.

**Parameters:**
- `scopes` (List[str]): Required permission scopes

**Returns:**
- `smartsheet.Smartsheet | None`: Authenticated client or None

**Process:**
1. Tries to use existing saved tokens
2. Refreshes token if expired
3. Runs new OAuth flow if no valid tokens exist

**Example:**
```python
from oauth_handler import get_smartsheet_client
from config import config

client = get_smartsheet_client(config.OAUTH_SCOPES)
if client:
    current_user = client.Users.get_current_user()
    print(f"Authenticated as: {current_user.email}")
```

---

### repository.py

**Purpose:** Encapsulates all Smartsheet API interactions.

#### Classes

##### `SmartsheetAPIError`
Exception raised when Smartsheet API operation fails.

##### `SmartsheetRepository`
Repository for Smartsheet API operations.

**Constructor:**
```python
def __init__(self, client):
    """
    Args:
        client: Authenticated Smartsheet client instance
    """
```

**Methods:**

##### `list_all_sheets()`
Retrieves all sheets from Smartsheet.

**Returns:**
- `List[Any]`: List of sheet objects

**Raises:**
- `SmartsheetAPIError`: If API call fails

##### `list_workspaces()`
Retrieves all workspaces from Smartsheet.

**Returns:**
- `List[Any]`: List of workspace objects

**Raises:**
- `SmartsheetAPIError`: If API call fails

##### `delete_workspace(workspace_id)`
Deletes a workspace by ID.

**Parameters:**
- `workspace_id` (int): Workspace ID to delete

**Returns:**
- `bool`: True if successful, False otherwise

**Raises:**
- `SmartsheetAPIError`: If API call fails with unexpected error

**Example:**
```python
success = repository.delete_workspace(1234567890)
if success:
    print("Workspace deleted successfully")
```

##### `get_sheet(sheet_id)`
Retrieves a sheet by ID.

**Parameters:**
- `sheet_id` (int): Sheet ID to retrieve

**Returns:**
- Sheet object with rows and metadata

**Raises:**
- `SmartsheetAPIError`: If API call fails

##### `get_columns(sheet_id)`
Retrieves all columns from a sheet.

**Parameters:**
- `sheet_id` (int): Sheet ID

**Returns:**
- `List[Any]`: List of column objects

**Raises:**
- `SmartsheetAPIError`: If API call fails

##### `update_cell(sheet_id, row_id, column_id, new_value)`
Updates a specific cell in a sheet.

**Parameters:**
- `sheet_id` (int): Sheet ID
- `row_id` (int): Row ID
- `column_id` (int): Column ID
- `new_value` (str): New cell value

**Returns:**
- `bool`: True if successful, False otherwise

**Raises:**
- `SmartsheetAPIError`: If API call fails

**Example:**
```python
repository.update_cell(
    sheet_id=123456,
    row_id=789012,
    column_id=345678,
    new_value="Deleted"
)
```

##### `get_current_user()`
Gets information about current authenticated user.

**Returns:**
- User object

**Raises:**
- `SmartsheetAPIError`: If API call fails

---

### service.py

**Purpose:** Business logic for workspace deletion workflow.

#### Classes

##### `WorkspaceDeletionError`
Exception raised when deletion process encounters an error.

##### `WorkspaceDeletionService`
Service for managing workspace deletion workflow.

**Constructor:**
```python
def __init__(self, repository: SmartsheetRepository):
    """
    Args:
        repository: SmartsheetRepository instance for data access
    """
```

**Methods:**

##### `find_workspace_by_permalink(permalink)`
Finds workspace ID by matching permalink pattern.

**Parameters:**
- `permalink` (str): Permalink URL to search for

**Returns:**
- `int | None`: Workspace ID if found, None otherwise

**Example:**
```python
workspace_id = service.find_workspace_by_permalink(
    "https://app.smartsheet.com/workspaces/abc123"
)
```

##### `find_sheet_by_permalink(permalink)`
Finds sheet ID by matching permalink pattern.

**Parameters:**
- `permalink` (str): Permalink URL to search for

**Returns:**
- `int | None`: Sheet ID if found, None otherwise

##### `get_parent_workspace_id_from_sheet(permalink)`
Gets parent workspace ID for a given sheet permalink.

**Parameters:**
- `permalink` (str): Sheet permalink URL

**Returns:**
- `int | None`: Parent workspace ID or None

**Process:**
1. Cleans permalink (removes query parameters)
2. Finds sheet by permalink
3. Retrieves sheet data
4. Extracts parent workspace ID

**Example:**
```python
workspace_id = service.get_parent_workspace_id_from_sheet(
    "https://app.smartsheet.com/sheets/xyz789?param=value"
)
```

##### `extract_row_data_with_column_ids(row, folder_url_col_id, deletion_date_col_id, em_notification_col_id, status_col_id)`
Extracts relevant data from a row using specific column IDs.

**Parameters:**
- `row` (Any): Row object from Smartsheet
- `folder_url_col_id` (int): Column ID for folder URL
- `deletion_date_col_id` (int): Column ID for deletion date
- `em_notification_col_id` (int): Column ID for EM notification date
- `status_col_id` (int): Column ID for deletion status

**Returns:**
- `Dict[str, Any]`: Extracted row data

**Example Output:**
```python
{
    "row_id": 123456,
    "folder_url": "https://app.smartsheet.com/sheets/...",
    "deletion_date": "2026-01-15",
    "em_notification_date": "2026-01-10",
    "deletion_status": "Pending"
}
```

##### `process_deletion_workflow(sheet_url)`
**Main orchestration method** for workspace deletion workflow.

**Parameters:**
- `sheet_url` (str): URL of intake sheet

**Returns:**
- `Dict[str, Any]`: Processing summary

**Process:**
1. Finds sheet by URL
2. Gets column IDs from config
3. Processes each row:
   - Extracts row data
   - Checks deletion criteria
   - Gets workspace ID from folder URL
   - Deletes workspace
   - Updates status cell
4. Returns summary

**Example Output:**
```python
{
    "processed_rows": 15,
    "successful_deletions": 5,
    "skipped": 10,
    "errors": [
        {
            "row_index": 3,
            "row_id": 789012,
            "error": "Failed to get workspace ID"
        }
    ]
}
```

**Example Usage:**
```python
service = WorkspaceDeletionService(repository)
summary = service.process_deletion_workflow(
    "https://app.smartsheet.com/sheets/intake123"
)
print(f"Deleted {summary['successful_deletions']} workspaces")
```

##### `extract_row_data(row, column_ids)`
Extracts relevant data from a sheet row.

**Parameters:**
- `row` (Any): Row object from Smartsheet
- `column_ids` (Dict[str, int]): Mapping of logical names to column IDs

**Returns:**
- `Dict[str, Any]`: Extracted row data

##### `process_intake_row(sheet_id, row, column_ids)`
Processes a single row to determine if workspace should be deleted.

**Parameters:**
- `sheet_id` (int): Sheet ID being processed
- `row` (Any): Row object to process
- `column_ids` (Dict[str, int]): Mapping of logical names to column IDs

**Returns:**
- `bool`: True if processed successfully, False otherwise

**Process:**
1. Extracts row data
2. Checks deletion criteria
3. Finds workspace by permalink
4. Deletes workspace
5. Updates row status

---

### utils.py

**Purpose:** Pure utility functions for date handling and string operations.

#### Functions

##### `get_pacific_today_date()`
Returns today's date in configured timezone.

**Returns:**
- `str | None`: Formatted date string (YYYY-MM-DD) or None if error

**Example:**
```python
date = get_pacific_today_date()
# Returns: "2026-01-05"
```

**Note:** Uses `config.TIMEZONE` (defaults to 'America/Los_Angeles')

##### `is_date_past_or_today(date_string, todays_date)`
Compares a date string to today's date.

**Parameters:**
- `date_string` (str): Date to compare (YYYY-MM-DD)
- `todays_date` (str): Today's date (YYYY-MM-DD)

**Returns:**
- `bool`: True if date_string is on or before today

**Example:**
```python
is_past = is_date_past_or_today("2026-01-01", "2026-01-05")
# Returns: True
```

##### `should_workspace_be_deleted(em_notification_date, deletion_date, todays_date)`
Determines if workspace should be deleted based on dates.

**Business Logic:**
- Workspace should be deleted if:
  - Today is on or after deletion date AND
  - Today is NOT the EM notification date

**Parameters:**
- `em_notification_date` (str): EM notification date (YYYY-MM-DD)
- `deletion_date` (str): Deletion date (YYYY-MM-DD)
- `todays_date` (str): Today's date (YYYY-MM-DD)

**Returns:**
- `bool`: True if workspace should be deleted

**Example:**
```python
should_delete = should_workspace_be_deleted(
    em_notification_date="2026-01-03",
    deletion_date="2026-01-05",
    todays_date="2026-01-05"
)
# Returns: True (today is deletion date and not EM notification date)
```

##### `is_pattern_substring(string_a, string_b, pattern)`
Checks if a pattern substring from string_a is present in string_b.

**Parameters:**
- `string_a` (str): String containing pattern (e.g., 'path/to/sheets/dev*')
- `string_b` (str): String to search within
- `pattern` (str): Pattern to match (e.g., 'sheets')

**Returns:**
- `bool`: True if pattern found and matches

**Example:**
```python
matches = is_pattern_substring(
    "https://app.smartsheet.com/sheets/abc123*",
    "https://app.smartsheet.com/sheets/abc123def",
    "sheets"
)
# Returns: True
```

##### `is_workspaces_substring(string_a, string_b)`
Checks if 'workspaces/*' substring from string_a is in string_b.

**Parameters:**
- `string_a` (str): String containing pattern (e.g., 'path/to/workspaces/dev*')
- `string_b` (str): String to search within

**Returns:**
- `bool`: True if workspaces pattern matches

**Example:**
```python
matches = is_workspaces_substring(
    "https://app.smartsheet.com/workspaces/project1*",
    "https://app.smartsheet.com/workspaces/project1/folder"
)
# Returns: True
```

##### `get_key_from_value(dictionary, value_to_find)`
Searches dictionary for value and returns first matching key.

**Parameters:**
- `dictionary` (dict): Dictionary to search
- `value_to_find`: Value to look for

**Returns:**
- `str | None`: Key corresponding to value, or None if not found

**Example:**
```python
key = get_key_from_value(
    {"name": "John", "age": 30},
    30
)
# Returns: "age"
```

##### `remove_query_string(string)`
Removes query string portion from URL.

**Parameters:**
- `string` (str): String to clean (URL with query parameters)

**Returns:**
- `str`: Cleaned string without query parameters

**Example:**
```python
clean_url = remove_query_string(
    "https://example.com/path?param=value&other=123"
)
# Returns: "https://example.com/path"
```

## Data Flow

### Complete Workflow

```
1. Application Start (app.py)
   ↓
2. Validate Configuration (config.py)
   ↓
3. Authenticate (oauth_handler.py)
   - Load existing tokens
   - Refresh if expired
   - Run OAuth flow if needed
   ↓
4. Initialize Services
   - Create SmartsheetRepository
   - Create WorkspaceDeletionService
   ↓
5. Process Deletion Workflow (service.py)
   - Find intake sheet
   - Get sheet data
   - For each row:
     a. Extract row data
     b. Check deletion criteria (utils.py)
     c. Get workspace ID from folder URL
     d. Delete workspace (repository.py)
     e. Update status cell (repository.py)
   ↓
6. Return Summary
```

### Deletion Criteria Decision Tree

```
Row Data
  ↓
Has deletion_date AND em_notification_date?
  ├─ No → Skip row
  └─ Yes
      ↓
  Is today >= deletion_date?
      ├─ No → Skip row
      └─ Yes
          ↓
      Is today == em_notification_date?
          ├─ Yes → Skip row (EM notification day)
          └─ No → DELETE WORKSPACE
```

## Error Handling

### Exception Hierarchy

```
Exception
├─ ConfigurationError (config.py)
│   └─ Missing or invalid configuration
├─ SmartsheetAPIError (repository.py)
│   └─ API operation failures
└─ WorkspaceDeletionError (service.py)
    └─ Deletion process errors
```

### Error Handling Strategies

#### 1. Configuration Errors
- **When:** Missing environment variables
- **Action:** Fail fast, log error, return error response
- **Recovery:** None - requires configuration fix

#### 2. Authentication Errors
- **When:** OAuth failures, token expiration
- **Action:** Attempt token refresh, run new OAuth flow if needed
- **Recovery:** Automatic via token refresh or re-authentication

#### 3. API Errors
- **When:** Smartsheet API calls fail
- **Action:** Log error, raise SmartsheetAPIError
- **Recovery:** Depends on error type (401/403 triggers re-auth)

#### 4. Row Processing Errors
- **When:** Individual row processing fails
- **Action:** Log error, add to errors list, continue processing
- **Recovery:** Continue with next row

### Logging Levels

| Level | Usage |
|-------|-------|
| ERROR | Critical failures, API errors, missing config |
| WARNING | Non-critical issues, fallback behaviors |
| INFO | Workflow progress, successful operations |
| DEBUG | Detailed flow information, skipped rows |

### Example Error Response

```python
{
    "error": "Configuration error: Missing required OAuth configuration",
    "summary": {
        "processed_rows": 0,
        "successful_deletions": 0,
        "skipped": 0,
        "errors": []
    }
}
```

## Environment Variables

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `S_APP_CLIENT_ID` | Smartsheet OAuth client ID (dev) | `abc123...` |
| `S_APP_SECRET` | Smartsheet OAuth client secret (dev) | `xyz789...` |
| `APP_CLIENT_ID` | Smartsheet OAuth client ID (prod) | `abc123...` |
| `APP_SECRET` | Smartsheet OAuth client secret (prod) | `xyz789...` |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIRECT_URI` | OAuth callback URL | `http://localhost:8080/callback` |
| `TOKEN_FILE` | Local token storage file | `smartsheet_token.json` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `TIMEZONE` | Timezone for dates | `America/Los_Angeles` |

## AWS Lambda Deployment

### Environment Detection

The application automatically detects AWS Lambda environment via:
```python
IS_AWS_LAMBDA = (
    os.getenv('AWS_LAMBDA_FUNCTION_NAME') is not None or 
    os.getenv('AWS_EXECUTION_ENV') is not None
)
```

### Token Storage in Lambda

- **Development/Testing:** Use local file storage
- **Production:** Use AWS Secrets Manager

### Required AWS Secrets

| Secret Name | Content |
|-------------|---------|
| `ausw2p-smgr-smt-access-token-001` | Access token (plain string) |
| `ausw2p-smgr-smt-refresh-token-002` | Refresh token (plain string) |
| `ausw2p-smgr-smt-client-id-003` | JSON: `{"CLIENT_ID": "..."}` |
| `ausw2p-smgr-smt-client-secret-004` | JSON: `{"CLIENT_SECRET": "..."}` |

### Required IAM Permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:PutSecretValue",
        "secretsmanager:CreateSecret"
      ],
      "Resource": [
        "arn:aws:secretsmanager:*:*:secret:ausw2p-smgr-smt-*"
      ]
    }
  ]
}
```
