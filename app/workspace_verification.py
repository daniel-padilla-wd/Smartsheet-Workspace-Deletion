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
from utils import remove_query_string, get_pacific_today_date, is_date_past_or_today  # noqa: E402


def verify_deleted_workspaces(sheet_id: int) -> Dict[str, Any]:
    """
    Read an intake sheet and mark rows as "Deleted" when workspace permalink
    cannot be resolved.

    Args:
        sheet_id: Smartsheet ID of the intake sheet to process.

    Returns:
        Summary dictionary with processing counts and errors.
    """
    summary: Dict[str, Any] = {
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
        return {"error": error_msg, "summary": summary}

    client = get_smartsheet_client(config.OAUTH_SCOPES)
    if not client:
        error_msg = "Authentication failed"
        logging.error(error_msg)
        return {"error": error_msg, "summary": summary}

    repository = SmartsheetRepository(client)
    service = WorkspaceDeletionService(repository)

    try:
        sheet = repository.get_sheet(sheet_id)
    except SmartsheetAPIError as err:
        error_msg = f"Failed to get sheet {sheet_id}: {err}"
        logging.error(error_msg)
        return {"error": error_msg, "summary": summary}

    todays_date = get_pacific_today_date()
    if not todays_date:
        error_msg = "Failed to get today's date"
        logging.error(error_msg)
        return {"error": error_msg, "summary": summary}

    rows = sheet.rows
    logging.info(f"Processing {len(rows)} rows from sheet {sheet_id}")

    for index, row in enumerate(rows):
        try:
            extracted_data = service.extract_row_data_with_column_ids(
                row,
                config.COLUMN_TITLES["folder_url"],
                config.COLUMN_TITLES["deletion_date"],
                config.COLUMN_TITLES["em_notification_date"],
                config.COLUMN_TITLES["deletion_status"],
            )
            summary["processed_rows"] += 1

            deletion_date = extracted_data.get("deletion_date")
            if not deletion_date or not is_date_past_or_today(deletion_date, todays_date):
                logging.info(f"Row {row.id}: deletion date '{deletion_date}' is in the future or missing, skipping")
                summary["skipped"] += 1
                continue

            delete_status = extracted_data.get("deletion_status", "")
            if delete_status:
                logging.info(f"Row {row.id}: already has deletion status, skipping")
                summary["skipped"] += 1
                continue

            folder_url = extracted_data.get("folder_url")
            if not folder_url:
                logging.info(f"Row {row.id}: missing folder URL, skipping")
                summary["skipped"] += 1
                continue

            clean_permalink = remove_query_string(str(folder_url))
            workspace_id = service.find_workspace_by_permalink(clean_permalink)

            if workspace_id is not None:
                workspace_metadata = repository.get_workspace(workspace_id)
                if workspace_metadata is not None:
                    logging.info(
                        f"Row {row.id}: workspace {workspace_id} still exists, no update"
                    )
                    summary["skipped"] += 1
                    continue

            # If we cannot resolve the workspace by permalink, or metadata lookup fails,
            # treat it as already deleted and mark the row.
            update_success = repository.update_cell(
                sheet_id=sheet_id,
                row_id=extracted_data["row_id"],
                column_id=config.COLUMN_TITLES["deletion_status"],
                new_value="Deleted",
            )

            if update_success:
                logging.info(f"Row {row.id}: updated deletion status to 'Deleted'")
                summary["updated_deleted_status"] += 1
            else:
                logging.warning(f"Row {row.id}: failed to update deletion status")
                summary["skipped"] += 1

        except Exception as err:  # Keep processing remaining rows.
            logging.error(f"Row {getattr(row, 'id', 'unknown')}: {err}")
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

    # Match app.py behavior for choosing target sheet.
    sheet_id = config.S_INTAKE_SHEET_ID if config.DEV_MODE else config.INTAKE_SHEET_ID

    logging.info(
        "Starting workspace verification workflow (no deletion operations enabled)"
    )
    logging.info(f"Using sheet ID: {sheet_id}")
    summary = verify_deleted_workspaces(int(sheet_id))

    if "error" in summary:
        logging.error(summary["error"])
        return summary

    logging.info("=" * 60)
    logging.info("VERIFICATION SUMMARY")
    logging.info("=" * 60)
    logging.info(f"Total rows processed: {summary['processed_rows']}")
    logging.info(f"Rows marked Deleted: {summary['updated_deleted_status']}")
    logging.info(f"Skipped: {summary['skipped']}")
    logging.info(f"Errors: {len(summary['errors'])}")
    logging.info("=" * 60)

    return summary


if __name__ == "__main__":
    main()
