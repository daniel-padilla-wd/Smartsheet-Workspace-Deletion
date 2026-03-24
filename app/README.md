# Smartsheet Workspace Deletion - API Documentation

## Table of Contents
- [Overview](#overview)
- [Current Execution Mode](#current-execution-mode)
- [Architecture](#architecture)
- [Module Reference](#module-reference)
  - [app.py](#apppy)
  - [workspace_verification.py](#workspace_verificationpy)
  - [config.py](#configpy)
  - [oauth_handler.py](#oauth_handlerpy)
  - [repository.py](#repositorypy)
  - [service.py](#servicepy)
  - [utils.py](#utilspy)
- [Data Flow](#data-flow)
- [Error Handling](#error-handling)
- [Environment Variables](#environment-variables)
- [AWS Lambda Notes](#aws-lambda-notes)

## Overview

This project automates Smartsheet workspace cleanup based on intake-sheet dates and links.

The current application entrypoint in `app.py` uses a verification-first workflow and imports helper functions from `workspace_verification.py`.

## Current Execution Mode

As implemented today:

- `app.py::main()` runs a verification workflow.
- It evaluates intake rows, resolves workspace IDs, and determines expected actions.
- It calls `delete_verified_workspaces(..., safe_mode=True)`, which means destructive API delete actions are not executed.
- It writes session logs and line-delimited JSON entry exports under `logs/`.

Important behavior notes in the current implementation:

- `main()` does not return a summary dictionary.
- Validation/authentication failures are logged, but `main()` does not currently fail fast at those checkpoints.
- The Lambda handler block in `app.py` is currently commented out.

## Architecture

The application currently follows this flow:

```
┌──────────────────────────────────────────────┐
│              app.py (Entry Point)           │
│   - main()                                  │
│   - Imports verification helpers             │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│      workspace_verification.py (Helpers)     │
│   - verify_project_status()                  │
│   - delete_verified_workspaces()             │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│       service.py (Business Logic)            │
│   - WorkspaceDeletionService                 │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│    repository.py (Smartsheet API Access)     │
│   - SmartsheetRepository                     │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│        oauth_handler.py (Auth Layer)         │
│   - OAuth + token lifecycle                  │
└──────────────────────────────────────────────┘
```

Supporting modules:

- `config.py`: Environment-backed settings and validation
- `utils.py`: Date helpers, filtering, row-log utilities

## Module Reference

### app.py

Purpose: Runtime entrypoint for the current verification-first workflow.

#### `main()`

Current process:

1. Configures logging and file logging output.
2. Calls `config.validate_oauth_config()`.
3. Authenticates with `get_smartsheet_client(config.OAUTH_SCOPES)`.
4. Builds `SmartsheetRepository` and `WorkspaceDeletionService`.
5. Loads intake sheet and all sheets.
6. Filters intake rows using `filter_intake_data(..., has_folder_url=True)`.
7. Verifies rows using `verify_project_status(...)`.
8. Invokes `delete_verified_workspaces(..., safe_mode=True)`.
9. Logs summary and exports row entries JSON.

Current return behavior:

- Returns `None` (no explicit return statement).

#### `lambda_handler(event, context)`

Status:

- Present only as commented code in the current file.
- Not active unless re-enabled.

---

### workspace_verification.py

Purpose: Contains reusable verification and deletion-orchestration helper functions used by `app.py`.

#### `verify_project_status(smartsheet_rows_list, todays_date, service, all_sheets)`

- Extracts and validates row data.
- Resolves workspace IDs from sheet/permalink data.
- Checks workspace existence.
- Produces `RowLogEntry` objects with automation actions such as `CONTINUE` and `SKIPPED - ...`.

#### `delete_verified_workspaces(log_entries, repository, service, safe_mode=True)`

- Processes rows marked for continuation and expected deletion.
- Traverses workspace content and performs delete calls through service/repository.
- When `safe_mode=True`, delete calls are dry-run style (no destructive action).
- Updates deletion status via `process_deletion_status_update`.

#### `main()`

- Standalone verification entrypoint that returns a summary dict.
- Not the runtime entrypoint currently used by `app.py`.

---

### config.py

Purpose: Centralized configuration and validation from environment variables.

Key class:

- `Config`

Key validation methods:

- `validate_oauth_config()`
- `validate_sheet_config()`
- `validate_all()`

Notes:

- `CLIENT_ID` and `CLIENT_SECRET` are class attributes loaded at import time.
- `DEV_MODE` toggles between sandbox and production IDs.

---

### oauth_handler.py

Purpose: OAuth 2.0 flow, token persistence, refresh, and client creation.

Primary entrypoint:

- `get_smartsheet_client(scopes)`

Behavior summary:

1. Load existing tokens (local/AWS).
2. Validate token.
3. Refresh token when needed.
4. Run full OAuth flow if needed.

---

### repository.py

Purpose: Encapsulates Smartsheet SDK/API operations.

Primary class:

- `SmartsheetRepository`

Representative methods:

- `get_sheet(sheet_id)`
- `list_all_sheets()`
- `get_workspace(workspace_id)`
- `get_all_workspace_children(workspace_id)`
- `delete_workspace(workspace_id, safe_mode=True)`
- `update_cell(...)`

---

### service.py

Purpose: Business logic for workspace resolution, validation, and deletion orchestration.

Primary class:

- `WorkspaceDeletionService`

Key methods used by current workflow:

- `extract_row_data(row)`
- `process_row_for_checks(smartsheet_row, extracted_row_data, all_sheets)`
- `process_workspace_id_resolution(smartsheet_row, extracted_row_data, all_sheets)`
- `process_workspace_existence(smartsheet_row, workspace_id)`
- `get_all_workspace_content(workspace_id)`
- `delete_all_workspace_content(all_workspace_content, safe_mode=True)`
- `process_deletion_status_update(entry, safe_mode=True)`

---

### utils.py

Purpose: Utility and helper functions for date handling, filtering, and structured row logging.

Commonly used in current flow:

- `get_pacific_today_date()`
- `setup_file_logging(log_name_prefix)`
- `filter_intake_data(sheet, todays_date, has_folder_url=True)`
- `get_expected_action(deletion_date, em_notification_date, todays_date)`
- `RowLogEntry`
- `log_row_entry(...)`

## Data Flow

### Current Runtime Flow (`app.py::main`)

```
1. Start app.py main
2. Configure logging + file logger
3. Validate OAuth config
4. Authenticate client
5. Create repository/service
6. Load intake sheet + list all sheets
7. Resolve Pacific date
8. Filter intake rows
9. verify_project_status(...)
10. delete_verified_workspaces(..., safe_mode=True)
11. Write summary logs
12. Export row entries JSON (logs/*_entries.json)
```

### Decision Logic (Per Row)

```mermaid
flowchart LR
    %% Nodes
    Start([Start])
    IntakeSheet[/Intake Sheet/]
    GetNextRow(Get Next Row)
    CheckDate{Is Date <= <br>Today?}
    ExtractSheetID(Extract Sheet ID from Link)
    GetWorkspaceID(Get Parent Workspace ID)
    VerifyWorkspace{Verify Workspace <br>Existence}
    DeleteWorkspace(Delete <br>Workspace)
    EndNode([END])

    %% Connections
    Start --> IntakeSheet
    IntakeSheet --> GetNextRow
    
    GetNextRow -- "Yes, there is a next row" --> CheckDate
    GetNextRow -- "No, all rows processed" --> EndNode
    
    CheckDate -- "No" --> GetNextRow
    CheckDate -- "Yes" --> ExtractSheetID
    
    ExtractSheetID --> GetWorkspaceID
    GetWorkspaceID --> VerifyWorkspace
    
    VerifyWorkspace -- "Doesn't Exist" --> GetNextRow
    VerifyWorkspace -- "Exists" --> DeleteWorkspace

    %% Styling
    classDef greenFill fill:#a8e6b3,stroke:#2e7d32,stroke-width:2px,color:#000
    classDef yellowFill fill:#fff9c4,stroke:#fbc02d,stroke-width:2px,color:#000
    classDef blueFill fill:#d0e1fd,stroke:#1565c0,stroke-width:2px,color:#000

    class Start,EndNode greenFill
    class IntakeSheet,GetNextRow,ExtractSheetID,GetWorkspaceID,DeleteWorkspace yellowFill
    class CheckDate,VerifyWorkspace blueFill
```

## Error Handling

### Exception Types

- `ConfigurationError` in `config.py`
- `SmartsheetAPIError` in `repository.py`
- `WorkspaceDeletionError` in `service.py`

### Current Strategy

- Row-level processing errors are logged and processing continues for other rows.
- Configuration/authentication/date failures are logged in `app.py`.
- `workspace_verification.py::main()` returns structured error payloads.
- `app.py::main()` currently logs errors but does not return a structured error payload.

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `APP_CLIENT_ID` | Smartsheet OAuth client ID (prod mode) |
| `APP_SECRET` | Smartsheet OAuth client secret (prod mode) |
| `S_APP_CLIENT_ID` | Smartsheet OAuth client ID (dev mode) |
| `S_APP_SECRET` | Smartsheet OAuth client secret (dev mode) |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIRECT_URI` | OAuth callback URL | `http://localhost:8080/callback` |
| `TOKEN_FILE` | Local token file | `smartsheet_token.json` |
| `FILE_LOGGING_LEVEL` | File log level | `DEBUG` |
| `CONSOLE_LOGGING_LEVEL` | Console log level | `INFO` |
| `TIMEZONE` | Date timezone | `America/Los_Angeles` |
| `INTAKE_SHEET_ID` | Production intake sheet ID | `0` if unset |

## AWS Lambda Notes

- OAuth/token support for AWS is implemented in `oauth_handler.py`.
- The runtime Lambda handler in `app.py` is currently commented out.
- To use Lambda from `app.py`, re-enable `lambda_handler` and ensure it returns a serializable summary payload.

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
