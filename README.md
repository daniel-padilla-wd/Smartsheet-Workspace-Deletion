# Smartsheet Workspace Deletion

Automation project for verifying and processing Smartsheet workspace deletion using OAuth authentication and intake-sheet metadata.

## Overview

The current implementation is verification-first:

- Reads intake sheet rows.
- Resolves linked sheet and parent workspace context.
- Determines whether each row should continue to deletion processing.
- Runs deletion operations in `safe_mode=True` from the app entrypoint, so destructive actions are not executed by default.
- Logs results and exports row-level entries for auditing.

Project modules live under `app/`.

## Current Entrypoints

- Primary runtime entrypoint: `app/app.py` (`main()`)

For implementation-level API documentation, see `app/README.md`.

## High-Level Flow

### Application Initialization

1. Validate OAuth configuration.
2. Authenticate with Smartsheet via OAuth token lifecycle.
3. Initialize repository and service layers.
4. Load intake sheet and sheet catalog.
5. Filter rows eligible for evaluation.

### Per-Row Processing Decision Logic
Note: 
- This is an abstracted view of the workflow. Please review the code for a comprehensive understanding. 
- You can copy-paste the block below into Miro > Diagram > Flowchart to generate a visual 


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

### Finalization

6. Export logs and row-level JSON entries.

## Prerequisites

- Python 3.10+
- OAuth app credentials for Smartsheet
- Access to the intake sheet and relevant workspace/sheet resources

## Installation

```bash
pip install -r requirements.txt
```

## GitHub Copilot Agents

This repository includes custom Copilot agent definitions under `.github/agents/`.
These agents are used to route documentation, debugging, Smartsheet API, and design-review requests to the most appropriate specialist.

### Agent System Overview

- `Orchestrator` is the coordinator agent.
- It classifies a request and delegates to exactly one specialist unless the task clearly needs a different path.
- The specialist returns findings or guidance, and the orchestrator assembles the final response.

### Available Agents

#### `Orchestrator`

- File: `.github/agents/orchestrator.agent.md`
- Purpose: Route requests to the correct specialist and assemble the final answer.
- Delegates to: `debug-agent`, `docs-agent`, `smartsheet-docs-lookup-agent`, and `software-design-agent`
- Built-in handoffs:
  - `Plan`: create phased implementation plans
  - `Ask`: answer directly when delegation is unnecessary

#### `debug-agent`

- File: `.github/agents/debug-agent.agent.md`
- Purpose: Diagnose failures, isolate likely root causes, and propose the smallest safe fix.
- Best for:
  - failing tests
  - runtime errors
  - stack traces
  - flaky behavior

#### `docs-agent`

- File: `.github/agents/docs-agent.agent.md`
- Purpose: Turn implementation details into clear documentation.
- Best for:
  - README updates
  - developer guides
  - onboarding documentation
  - API usage notes
  - Python docstrings

#### `smartsheet-docs-lookup-agent`

- File: `.github/agents/smartsheet-docs-lookup-agent.agent.md`
- Purpose: Answer Smartsheet API and Smartsheet Python SDK questions using official docs and local package sources.
- Best for:
  - Smartsheet API methods and scopes
  - SDK usage patterns
  - endpoint behavior and caveats
  - permission and scope requirements

#### `software-design-agent`

- File: `.github/agents/software-design-agent.agent.md`
- Purpose: Review code and architecture against maintainability and Python design principles.
- Best for:
  - refactor reviews
  - SOLID, DRY, KISS, and YAGNI tradeoffs
  - abstraction and coupling concerns
  - Pythonic alternatives to class-heavy designs

### Routing Rules

The orchestrator currently routes requests using these rules:

- Debugging issues, stack traces, failing tests, and reproducible bugs go to `debug-agent`.
- Technical writing, README work, onboarding docs, API usage notes, and docstrings go to `docs-agent`.
- Smartsheet API and SDK questions go to `smartsheet-docs-lookup-agent`.
- Design review and maintainability questions go to `software-design-agent`.
- Planning requests go to built-in Plan mode.
- Everything else is handled directly.

### How To Use Them

In practice, describe the task in Copilot Chat and let the orchestrator route it.

Examples:

- "The app crashes when resolving workspace IDs. Here is the traceback." -> routes to `debug-agent`
- "Update the README to explain the verification-first workflow." -> routes to `docs-agent`
- "What Smartsheet scope is required to delete a workspace?" -> routes to `smartsheet-docs-lookup-agent`
- "Is the current service layer over-abstracted?" -> routes to `software-design-agent`
- "Create a phased implementation plan for adding Slack notifications." -> routes to Plan mode

### Agent File Structure

Each `.agent.md` file combines YAML frontmatter with markdown instructions.
Common fields used in this repository include:

- `name`: displayed agent name
- `description`: short role summary
- `tools`: tool access granted to the agent
- `user-invocable`: whether the agent can be directly selected by a user
- `agents`: sub-agents available for delegation
- `handoffs`: predefined fallback or alternate execution paths

## Configuration

Configuration is managed in `app/config.py` using the `configuration` singleton, which loads values from environment variables and defines mode flags.

### Mode Flags

- `PRODUCTION` (bool, default: `False`)
  - When `True`: uses production Smartsheet sheet/credential resources
  - When `False`: uses sandbox Smartsheet sheet/credential resources
- `LINUX_SERVER` (bool, default: `False`)
  - When `True`: token storage/retrieval uses AWS Secrets Manager
  - When `False`: token storage/retrieval uses local file

### Required Credentials (Production Mode)

When `PRODUCTION=True`:
- `APP_CLIENT_ID` — Smartsheet OAuth client ID
- `APP_SECRET` — Smartsheet OAuth client secret
- `INTAKE_SHEET_ID` — Production intake sheet ID (env var)

### Required Credentials (Sandbox Mode)

When `PRODUCTION=False`:
- `S_APP_CLIENT_ID` — Smartsheet sandbox OAuth client ID
- `S_APP_SECRET` — Smartsheet sandbox OAuth client secret
- Sandbox intake sheet ID is hardcoded in `config.py` as `S_INTAKE_SHEET_ID`

### Optional Configuration

- `REDIRECT_URI` (default: `http://localhost:8080/callback`)
- `TOKEN_FILE` (default: `smartsheet_token.json`)
- `TIMEZONE` (default: `America/Los_Angeles`)
- `FILE_LOGGING_LEVEL` (default: `DEBUG`)
- `CONSOLE_LOGGING_LEVEL` (default: `INFO`)

## Run

From repository root:

```bash
python3 app/app.py
```

## Logging and Output

- Session logs are written under `logs/`.
- Row-level audit entries are exported as line-delimited JSON (`*_entries.json`).

## Safety Notes

- Deleting Smartsheet assets is irreversible.
- Current app flow uses safe mode for delete operations by default.
- Confirm behavior in `app/app.py` before enabling destructive runs.

## AWS Lambda Notes

- OAuth/token support for AWS is implemented in `app/oauth_handler.py`.
- The runtime Lambda handler in `app/app.py` is currently commented out.
- To use Lambda from `app/app.py`, re-enable `lambda_handler` and ensure it returns a serializable summary payload.

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
