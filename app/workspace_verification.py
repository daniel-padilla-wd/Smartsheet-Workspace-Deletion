"""
Verification-only workflow for marking already deleted workspaces in Smartsheet.

This script intentionally does NOT delete workspaces, folders, sheets, or any data.
It only reads an intake sheet and updates the deletion-status column when a
workspace appears to already be deleted (not resolvable by permalink).
"""

import logging
import sys
from pathlib import Path
from typing import Any, Dict


# Reuse existing app modules that live in ./app with local-style imports.
ROOT_DIR = Path(__file__).resolve().parent
APP_DIR = ROOT_DIR / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from config import config, ConfigurationError  # noqa: E402
from oauth_handler import get_smartsheet_client  # noqa: E402
from repository import SmartsheetRepository, SmartsheetAPIError  # noqa: E402
from service import WorkspaceDeletionService  # noqa: E402
from utils import (  # noqa: E402
    remove_query_string,
    get_pacific_today_date,
    is_date_past_or_today,
    setup_file_logging,
    limit_iterable,
    RowLogEntry,
    log_row_entry,
    get_expected_action,
)


@limit_iterable(500)
def get_rows_for_verification(sheet: Any) -> list[Any]:
    """Return capped rows for safeguard testing runs."""
    return sheet.rows


def verify_deleted_workspaces(
    intake_sheet: Any,
    todays_date: str,
    repository: SmartsheetRepository,
    service: WorkspaceDeletionService,
    all_workspaces: list[Any],
) -> Dict[str, Any]:
    """
    Read an intake sheet and mark rows as "Deleted" when workspace permalink
    cannot be resolved.

    Args:
        intake_sheet: Smartsheet sheet object to process.
        todays_date: Current date in 'YYYY-MM-DD' format.
        repository: Repository instance for Smartsheet API calls.
        service: Service instance containing row parsing and lookup logic.
        all_workspaces: Pre-fetched workspace objects used for permalink resolution.

    Returns:
        Summary dictionary with processing counts and errors.
    """
    summary: Dict[str, Any] = {
        "processed_rows": 0,
        "updated_deleted_status": 0,
        "skipped": 0,
        "errors": [],
    }
    
    #rows = get_rows_for_verification(intake_sheet)
    rows = intake_sheet.rows
    logging.info("Row limit safeguard active: processing up to 20 rows")
    logging.info(f"Processing {len(rows)} rows from sheet {intake_sheet.id}")

    for index, row in enumerate(rows, start=1):
        try:
            extracted_data = service.extract_row_data_with_column_ids(
                row,
                config.COLUMN_TITLES["folder_url"],
                config.COLUMN_TITLES["deletion_date"],
                config.COLUMN_TITLES["em_notification_date"],
                config.COLUMN_TITLES["deletion_status"],
            )
            summary["processed_rows"] += 1

            # Extract row data for logging
            folder_url = extracted_data.get("folder_url")
            em_notification_date = extracted_data.get("em_notification_date")
            deletion_status = extracted_data.get("deletion_status", "")

            deletion_date = extracted_data.get("deletion_date")
            if not deletion_date or not is_date_past_or_today(deletion_date, todays_date):
                expected_action = get_expected_action(deletion_date, em_notification_date, todays_date)
                log_entry = RowLogEntry(
                    row_index=index,
                    row_id=row.id,
                    folder_url=folder_url,
                    deletion_date=deletion_date,
                    em_notification_date=em_notification_date,
                    deletion_status=deletion_status,
                    expected_action=expected_action,
                    automation_action="skipped - deletion date in future or missing",
                )
                log_row_entry(log_entry)
                summary["skipped"] += 1
                continue

            if deletion_status:
                expected_action = get_expected_action(deletion_date, em_notification_date, todays_date)
                log_entry = RowLogEntry(
                    row_index=index,
                    row_id=row.id,
                    folder_url=folder_url,
                    deletion_date=deletion_date,
                    em_notification_date=em_notification_date,
                    deletion_status=deletion_status,
                    expected_action=expected_action,
                    automation_action="skipped - already has deletion status",
                )
                log_row_entry(log_entry)
                summary["skipped"] += 1
                continue

            if not folder_url:
                expected_action = get_expected_action(deletion_date, em_notification_date, todays_date)
                log_entry = RowLogEntry(
                    row_index=index,
                    row_id=row.id,
                    folder_url=folder_url,
                    deletion_date=deletion_date,
                    em_notification_date=em_notification_date,
                    deletion_status=deletion_status,
                    expected_action=expected_action,
                    automation_action="skipped - missing folder URL",
                )
                log_row_entry(log_entry)
                summary["skipped"] += 1
                continue

            clean_permalink = remove_query_string(str(folder_url))
            workspace = service.find_workspace(workspaces=all_workspaces, perma_link=clean_permalink)
            workspace_id = getattr(workspace, "id", None)
            workspace_permalink = getattr(workspace, "permalink", None)

            if workspace_id is not None:
                workspace_metadata = repository.get_workspace(workspace_id)
                if workspace_metadata is not None:
                    expected_action = get_expected_action(deletion_date, em_notification_date, todays_date)
                    log_entry = RowLogEntry(
                        row_index=index,
                        row_id=row.id,
                        workspace_id=workspace_id,
                        workspace_permalink=workspace_permalink,
                        folder_url=folder_url,
                        deletion_date=deletion_date,
                        em_notification_date=em_notification_date,
                        deletion_status=deletion_status,
                        expected_action=expected_action,
                        automation_action=f"skipped - workspace {workspace_id} still exists",
                    )
                    log_row_entry(log_entry)
                    summary["skipped"] += 1
                    continue

            # Workspace appears deleted, update deletion status in the sheet.
            expected_action = get_expected_action(deletion_date, em_notification_date, todays_date)
            update_success = repository.update_cell(
                sheet_id=intake_sheet.id,
                row_id=extracted_data["row_id"],
                column_id=config.COLUMN_TITLES["deletion_status"],
                new_value="Deleted",
            )

            if update_success:
                log_entry = RowLogEntry(
                    row_index=index,
                    row_id=row.id,
                    workspace_id=workspace_id,
                    workspace_permalink=workspace_permalink,
                    folder_url=folder_url,
                    deletion_date=deletion_date,
                    em_notification_date=em_notification_date,
                    deletion_status=deletion_status,
                    expected_action=expected_action,
                    automation_action="updated deletion status to Deleted",
                )
                log_row_entry(log_entry)
                summary["updated_deleted_status"] += 1
            else:
                log_entry = RowLogEntry(
                    row_index=index,
                    row_id=row.id,
                    workspace_id=workspace_id,
                    workspace_permalink=workspace_permalink,
                    folder_url=folder_url,
                    deletion_date=deletion_date,
                    em_notification_date=em_notification_date,
                    deletion_status=deletion_status,
                    expected_action=expected_action,
                    automation_action="failed to update deletion status",
                )
                log_row_entry(log_entry, level="WARNING")
                summary["skipped"] += 1

        except Exception as err:  # Keep processing remaining rows.
            log_entry = RowLogEntry(
                row_index=index,
                row_id=getattr(row, "id", None),
                automation_action=f"error - {str(err)}",
            )
            log_row_entry(log_entry, level="ERROR")
            summary["errors"].append(
                {
                    "row_index": index,
                    "row_id": getattr(row, "id", None),
                    "error": str(err),
                }
            )
            summary["skipped"] += 1

    return summary


def main() -> Dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    # Set up file logging for this session
    log_file = setup_file_logging("workspace_verification")

    summary_template: Dict[str, Any] = {
        "processed_rows": 0,
        "updated_deleted_status": 0,
        "skipped": 0,
        "errors": [],
    }

    try:
        config.validate_oauth_config()
    except ConfigurationError as err:
        error_msg = f"Configuration error: {err}"
        logging.error(error_msg)
        return {"error": error_msg, "summary": summary_template, "log_file": log_file}

    client = get_smartsheet_client(config.OAUTH_SCOPES)
    if not client:
        error_msg = "Authentication failed"
        logging.error(error_msg)
        return {"error": error_msg, "summary": summary_template, "log_file": log_file}

    repository = SmartsheetRepository(client)
    service = WorkspaceDeletionService(repository)

    # Match app.py behavior for choosing target sheet.
    sheet_id = config.S_INTAKE_SHEET_ID if config.DEV_MODE else config.INTAKE_SHEET_ID

    logging.info(
        "Starting workspace verification workflow (no deletion operations enabled)"
    )
    logging.info(f"Using sheet ID: {sheet_id}")
    intake_sheet = repository.get_sheet(int(sheet_id))
    all_workspaces = repository.get_all_workspaces()

    todays_date = get_pacific_today_date()
    if not todays_date:
        error_msg = "Failed to get today's date"
        logging.error(error_msg)
        return {"error": error_msg, "summary": summary_template, "log_file": log_file}

    summary = verify_deleted_workspaces(
        intake_sheet,
        todays_date,
        repository,
        service,
        all_workspaces,
    )

    if "error" in summary:
        logging.error(summary["error"])
        summary["log_file"] = log_file
        return summary

    logging.info("=" * 60)
    logging.info("VERIFICATION SUMMARY")
    logging.info("=" * 60)
    logging.info(f"Total rows processed: {summary['processed_rows']}")
    logging.info(f"Rows marked Deleted: {summary['updated_deleted_status']}")
    logging.info(f"Skipped: {summary['skipped']}")
    logging.info(f"Errors: {len(summary['errors'])}")
    logging.info("=" * 60)
    logging.info(f"Logs saved to: {log_file}")

    summary["log_file"] = log_file
    return summary


def tests():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        config.validate_oauth_config()
    except ConfigurationError as err:
        error_msg = f"Configuration error: {err}"
        logging.error(error_msg)
        return {"error": error_msg}

    client = get_smartsheet_client(config.OAUTH_SCOPES)
    if not client:
        error_msg = "Authentication failed"
        logging.error(error_msg)
        return {"error": error_msg}

    repository = SmartsheetRepository(client)
    service = WorkspaceDeletionService(repository)

    all_sheets = repository.list_all_sheets()
    logging.info(f"Total sheets accessible: {len(all_sheets)}")

    #row_sheet_id = service.find_sheet_by_permalink("https://app.smartsheet.com/sheets/9r3fhQg4wgvjXxVMXpv3fmr2GfVxW924vpwJx7P1")
    #row_sheet_data = repository.get_sheet(row_sheet_id)
    #parent_workspace = getattr(row_sheet_data, "workspace")
    #parent_workspace_id = getattr(parent_workspace, "id")
    
    #logging.info(f"Test workspace lookup result: {parent_workspace_id}")
    #get_wrokspace_result = repository.get_workspace(parent_workspace_id)
    #logging.info(f"Test get workspace result: {get_wrokspace_result}")





if __name__ == "__main__":
    tests()
