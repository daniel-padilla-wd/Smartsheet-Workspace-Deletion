"""
Verification-only workflow for marking already deleted workspaces in Smartsheet.

This script intentionally does NOT delete workspaces, folders, sheets, or any data.
It only reads an intake sheet and updates the deletion-status column when a
workspace appears to already be deleted (not resolvable by permalink).
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict
from smartsheet.models.sheet import Sheet as SmartsheetSheet
from smartsheet.models.row import Row as SmartsheetRow


# Reuse existing app modules that live in ./app with local-style imports.
ROOT_DIR = Path(__file__).resolve().parent
APP_DIR = ROOT_DIR / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from config import config, ConfigurationError  
from oauth_handler import get_smartsheet_client  
from repository import SmartsheetRepository, SmartsheetAPIError  
from service import (
    WorkspaceDeletionService, 
    validate_complete_cell_values)
from utils import ( 
    remove_query_string,
    get_pacific_today_date,
    is_date_past_or_today,
    setup_file_logging,
    RowLogEntry,
    log_row_entry,
    get_expected_action,
    filter_intake_data,
    get_hyperlink_from_cell,
    validate_complete_cell_values,
    return_validated_rows
)


def verify_project_status(
    intake_sheet: Any,
    todays_date: str,
    repository: SmartsheetRepository,
    service: WorkspaceDeletionService,
    all_workspaces: list[Any],
    all_sheets: list[Any],
) -> list[RowLogEntry]:
    """
    Read an intake sheet and collect a RowLogEntry for each row, noting whether
    the workspace appears to already be deleted.

    Args:
        intake_sheet: Smartsheet sheet object to process.
        todays_date: Current date in 'YYYY-MM-DD' format.
        repository: Repository instance for Smartsheet API calls.
        service: Service instance containing row parsing and lookup logic.
        all_workspaces: Pre-fetched workspace objects used for permalink resolution.

    Returns:
        List of RowLogEntry objects, one per processed row.
    """
    log_entries: list[RowLogEntry] = []
    
    #rows = get_rows_for_verification(intake_sheet)
    #logging.info(f "Row limit safeguard active: processing up to {LIMIT} rows")
    #rows = intake_sheet.rows
    #logging.info(f"Processing {len(rows)} rows from sheet {intake_sheet.id}")

    rows = intake_sheet

    for index, row in enumerate(rows, start=1):
        try:
            extracted_data = service.extract_row_data_with_column_ids(
                row,
                config.COLUMN_TITLES["folder_url"],
                config.COLUMN_TITLES["deletion_date"],
                config.COLUMN_TITLES["em_notification_date"],
                config.COLUMN_TITLES["deletion_status"],
            )

            # Extract row data for logging
            folder_url = extracted_data.get("folder_url")
            em_notification_date = extracted_data.get("em_notification_date")
            deletion_status = extracted_data.get("deletion_status", "")
            deletion_date = extracted_data.get("deletion_date")

            expected_action = get_expected_action(deletion_date, em_notification_date, todays_date)

            # Checks to determine if we should skip this row for verification
            if not deletion_date or not is_date_past_or_today(deletion_date, todays_date):
                log_entry = RowLogEntry(
                    row_index=getattr(row, "row_number"),
                    row_id=row.id,
                    folder_url=folder_url,
                    deletion_date=deletion_date,
                    em_notification_date=em_notification_date,
                    deletion_status=deletion_status,
                    expected_action=expected_action,
                    automation_action="skipped - deletion date in future or missing",
                )
                log_row_entry(log_entry)
                log_entries.append(log_entry)
                continue

            if not folder_url:
                #expected_action = get_expected_action(deletion_date, em_notification_date, todays_date)
                log_entry = RowLogEntry(
                    row_index=getattr(row, "row_number"),
                    row_id=row.id,
                    folder_url=folder_url,
                    deletion_date=deletion_date,
                    em_notification_date=em_notification_date,
                    deletion_status=deletion_status,
                    expected_action=expected_action,
                    automation_action="skipped - missing folder URL",
                )
                log_row_entry(log_entry)
                log_entries.append(log_entry)
                continue

            clean_permalink = remove_query_string(str(folder_url))
            sheet_id_from_folder_url = service.get_sheet_id_from_permalink(clean_permalink, all_sheets)
            if not sheet_id_from_folder_url:
                #expected_action = get_expected_action(deletion_date, em_notification_date, todays_date)
                if "https://app.smartsheet.com/sheets/" not in clean_permalink:
                    logging.warning(f"Row {index}: Folder URL does not appear to be a valid Smartsheet sheet permalink: {folder_url}")
                    log_entry = RowLogEntry(
                        row_index=getattr(row, "row_number"),
                        row_id=row.id,
                        folder_url=folder_url,
                        deletion_date=deletion_date,
                        em_notification_date=em_notification_date,
                        deletion_status=deletion_status,
                        expected_action=expected_action,
                        automation_action="skipped - Unexpeced URL",
                    )
                    log_row_entry(log_entry)
                    log_entries.append(log_entry)
                    continue

                log_entry = RowLogEntry(
                    row_index=getattr(row, "row_number"),
                    row_id=row.id,
                    folder_url=folder_url,
                    deletion_date=deletion_date,
                    em_notification_date=em_notification_date,
                    deletion_status=deletion_status,
                    expected_action=expected_action,
                    automation_action="skipped - could not resolve sheet ID from permalink; likely already deleted workspace",
                )
                log_row_entry(log_entry)
                log_entries.append(log_entry)
                continue
            sheet_id_metadata = repository.get_sheet(sheet_id_from_folder_url) if sheet_id_from_folder_url else None
            workspace = service.find_workspace(workspaces=all_workspaces, id=sheet_id_metadata.workspace.id) if sheet_id_metadata else None
            workspace_id = getattr(workspace, "id", None)
            workspace_permalink = getattr(workspace, "permalink", None)

            if workspace_id is not None:
                workspace_metadata = repository.get_workspace(workspace_id)
                if workspace_metadata is not None:
                    #expected_action = get_expected_action(deletion_date, em_notification_date, todays_date)
                    log_entry = RowLogEntry(
                        row_index=getattr(row, "row_number"),
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
                    log_entries.append(log_entry)

                    '''if deletion_status is not None and deletion_status.lower() == "deleted":
                        logging.warning(f"Row {index}: Workspace {workspace_id} still exists but deletion status is marked as 'Deleted' - potential data inconsistency.")
                        try:
                            update_success = repository.update_cell(
                                sheet_id=intake_sheet.id,
                                row_id=extracted_data["row_id"],
                                column_id=config.COLUMN_TITLES["deletion_status"],
                                new_value="Not Deleted",
                            )
                            if update_success:
                                logging.info(
                                    f"Row {index}: Updated deletion status to 'Not Deleted' for row {row.id}"
                                )
                            else:
                                logging.warning(
                                    f"Row {index}: Failed to update deletion status to 'Not Deleted' for row {row.id}"
                                )
                        except SmartsheetAPIError as update_err:
                            logging.error(
                                f"Row {index}: Error updating deletion status for row {row.id}: {update_err}"
                            )'''
                    continue

            # Workspace appears deleted - no update performed.
            # expected_action = get_expected_action(deletion_date, em_notification_date, todays_date)
            log_entry = RowLogEntry(
                row_index=getattr(row, "row_number"),
                row_id=row.id,
                workspace_id=workspace_id,
                workspace_permalink=workspace_permalink,
                folder_url=folder_url,
                deletion_date=deletion_date,
                em_notification_date=em_notification_date,
                deletion_status=deletion_status,
                expected_action=expected_action,
                automation_action="workspace appears deleted",
            )
            log_row_entry(log_entry)
            log_entries.append(log_entry)
            '''
            try:
                update_success = repository.update_cell(
                    sheet_id=intake_sheet.id,
                    row_id=extracted_data["row_id"],
                    column_id=config.COLUMN_TITLES["deletion_status"],
                    new_value="Deleted",
                )
            except SmartsheetAPIError as update_err:
                logging.error(
                    f"Row {index}: Error updating deletion status for row {row.id}: {update_err}"
                )'''
            

        except Exception as err:  # Keep processing remaining rows.
            log_entry = RowLogEntry(
                row_index=getattr(row, "row_number"),
                row_id=getattr(row, "id", None),
                automation_action=f"error - {str(err)}",
            )
            log_row_entry(log_entry, level="ERROR")
            log_entries.append(log_entry)

    return log_entries


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

    intake_sheet_id = config.S_INTAKE_SHEET_ID if config.DEV_MODE else config.INTAKE_SHEET_ID

    logging.info(
        "Starting workspace verification workflow (no deletion operations enabled)"
    )
    intake_sheet = repository.get_sheet(int(intake_sheet_id))
    all_workspaces = repository.get_all_workspaces()
    all_sheets = repository.list_all_sheets()

    todays_date = get_pacific_today_date()
    if not todays_date:
        error_msg = "Failed to get today's date"
        logging.error(error_msg)
        return {"error": error_msg, "summary": summary_template, "log_file": log_file}
    
    filtered_intake_data = filter_intake_data(intake_sheet, todays_date, has_folder_url=True)

    log_entries = verify_project_status(
        filtered_intake_data,
        todays_date,
        repository,
        service,
        all_workspaces,
        all_sheets
    )

    total_processed = len(log_entries)
    appears_deleted = sum(1 for e in log_entries if e.automation_action == "workspace appears deleted - no update performed")
    skipped = sum(1 for e in log_entries if e.automation_action.startswith("skipped"))
    errors = sum(1 for e in log_entries if e.automation_action.startswith("error"))

    logging.info("=" * 60)
    logging.info("VERIFICATION SUMMARY")
    logging.info("=" * 60)
    logging.info(f"Total rows processed: {total_processed}")
    logging.info(f"Workspace appears deleted: {appears_deleted}")
    logging.info(f"Skipped: {skipped}")
    logging.info(f"Errors: {errors}")
    logging.info("=" * 60)
    logging.info(f"Logs saved to: {log_file}")

    entries_file = str(Path(log_file).with_name(Path(log_file).stem + "_entries.json"))
    if log_entries:
        with open(entries_file, "w") as f:
            for entry in log_entries:
                f.write(json.dumps(entry.to_dict()) + "\n")
    logging.info(f"Log entries exported to: {entries_file}")

    return {
        "processed_rows": total_processed,
        "appears_deleted": appears_deleted,
        "skipped": skipped,
        "errors": errors,
        "log_entries": log_entries,
        "log_file": log_file,
        "entries_file": entries_file,
    }

# You can ignore the tests function - it's just for local testing and debugging, not part of the main workflow.
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

    intake_sheet_id = config.S_INTAKE_SHEET_ID if config.DEV_MODE else config.INTAKE_SHEET_ID
    intake_sheet = repository.get_sheet(int(intake_sheet_id))
    todays_date = get_pacific_today_date()
    if not todays_date:
        error_msg = "Failed to get today's date"
        logging.error(error_msg)
        return {"error": error_msg}

    filtered_intake_data = filter_intake_data(intake_sheet, todays_date, has_folder_url=True)
    logging.info(f"Filtered intake data to {len(filtered_intake_data)} rows with folder URLs and deletion dates in the past or today")

    rows_that_passed_checks = []
    for row in filtered_intake_data:
        hyperlink = get_hyperlink_from_cell(row.cells)
        logging.info(f"Row {getattr(row, 'row_number', 'N/A')}: Extracted hyperlink: {hyperlink}") 
        complete_cell_values = validate_complete_cell_values(row.cells)
        logging.info(f"Row {getattr(row, 'row_number', 'N/A')}: Complete cell values: {complete_cell_values}")
        if validate_complete_cell_values(row.cells):
            rows_that_passed_checks.append(row)

    print(f"Total rows that passed validation checks: {len(rows_that_passed_checks)}")
    print(rows_that_passed_checks)

        
        

    
        





if __name__ == "__main__":
    tests()
