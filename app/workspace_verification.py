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
from repository import SmartsheetRepository  
from service import WorkspaceDeletionService
from utils import ( 
    get_pacific_today_date,
    setup_file_logging,
    RowLogEntry,
    log_row_entry,
    get_expected_action,
    filter_intake_data,
    get_hyperlink_from_cell,
    validate_complete_cell_values
)

def verify_project_status(
    smartsheet_rows_list: list[SmartsheetRow],
    todays_date: str,
    service: WorkspaceDeletionService,
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

    for index, smartsheet_row in enumerate(smartsheet_rows_list, start=1):
        try:
            try:
                extracted_row_data = service.extract_row_data(smartsheet_row)
                row_entry = service.process_row_for_checks(smartsheet_row, extracted_row_data, all_sheets)
                if row_entry.automation_action.startswith("SKIPPED"):
                    log_row_entry(row_entry)
                    log_entries.append(row_entry)
                    continue
            except Exception as err:
                logging.error(f"Row {getattr(smartsheet_row, 'row_number', 'N/A')}: Error extracting row data or performing initial checks: {err}")
                continue

            try:
                workspace_id_resolution = service.process_workspace_id_resolution(smartsheet_row, extracted_row_data, all_sheets)
                if workspace_id_resolution.automation_action.startswith("SKIPPED"):
                    log_row_entry(workspace_id_resolution)
                    log_entries.append(workspace_id_resolution)
                    continue
            except Exception as err:
                logging.error(f"Row {getattr(smartsheet_row, 'row_number', 'N/A')}: Error during workspace ID resolution: {err}")
                continue

            try:
                workspace_id = workspace_id_resolution.workspace_id
                workspace_exists = service.process_workspace_existence(smartsheet_row, workspace_id)
                if workspace_exists.automation_action.startswith("SKIPPED"):
                    log_row_entry(workspace_exists)
                    log_entries.append(workspace_exists)
                    continue
            except Exception as err:
                logging.error(f"Row {getattr(smartsheet_row, 'row_number', 'N/A')}: Error during workspace existence check: {err}")
                continue
            try: 
                expected_action = get_expected_action(extracted_row_data["deletion_date"], extracted_row_data["em_notification_date"], todays_date)
                log_entry = RowLogEntry(
                    row_index=getattr(smartsheet_row, "row_number"),
                    row_id=getattr(smartsheet_row, "id"),
                    workspace_id=workspace_id,
                    workspace_permalink=workspace_exists.workspace_permalink,
                    folder_url=extracted_row_data.get("folder_url"),
                    deletion_date=extracted_row_data.get("deletion_date"),
                    em_notification_date=extracted_row_data.get("em_notification_date"),
                    deletion_status=extracted_row_data.get("deletion_status"),
                    expected_action=expected_action,
                    automation_action=f"CONTINUE",
                )
                log_row_entry(log_entry)
                log_entries.append(log_entry)
            except Exception as err:
                logging.error(f"Row {getattr(smartsheet_row, 'row_number', 'N/A')}: Error determining expected action or logging: {err}")
        except Exception as err:  
            log_entry = RowLogEntry(
                row_index=getattr(smartsheet_row, "row_number"),
                row_id=getattr(smartsheet_row, "id", None),
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
    # all_workspaces = repository.get_all_workspaces()
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
        service,
        all_sheets
    )

    total_processed = len(log_entries)
    appears_deleted = sum(1 for e in log_entries if not e.workspace_id)
    skipped = sum(1 for e in log_entries if e.automation_action.startswith("SKIPPED"))
    errors = sum(1 for e in log_entries if e.automation_action.startswith("error"))
    next_phase = sum(1 for e in log_entries if e.automation_action == "CONTINUE")  

    logging.info("=" * 60)
    logging.info("VERIFICATION SUMMARY")
    logging.info("=" * 60)
    logging.info(f"Total rows processed: {total_processed}")
    logging.info(f"Workspace appears deleted: {appears_deleted}")
    logging.info(f"Workspace still exists: {total_processed - appears_deleted - skipped - errors}")
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

    #all_sheets = repository.list_all_sheets()

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
        #logging.info(f"Row {getattr(row, 'row_number', 'N/A')}: Extracted hyperlink: {hyperlink}") 
        complete_cell_values = validate_complete_cell_values(row.cells)
        #logging.info(f"Row {getattr(row, 'row_number', 'N/A')}: Complete cell values: {complete_cell_values}")
        if validate_complete_cell_values(row.cells):
            rows_that_passed_checks.append(row)
    logging.info(f"{len(rows_that_passed_checks)} rows passed initial checks for folder URL and deletion date")

    #log_entries = verify_project_status(filtered_intake_data,todays_date,service,all_sheets)
    #print(f"Total log entries: {len(log_entries)}")

    workspace_id = 852176508610436
    workspace_childern = repository.get_all_workspace_children(workspace_id)
    print(f"Children of workspace {workspace_id}: {workspace_childern}")
    print(f"Total children: {len(workspace_childern)}")
    print(f"View list: {workspace_childern}")
    print(f"IDs of children: {[getattr(child, 'id', 'N/A') for child in workspace_childern]}")

    folder_id = 4553024141059972
    folder_children = repository.get_all_folder_children(folder_id)
    print(f"Children of folder {folder_id}: {folder_children}")
    print(f"Total children: {len(folder_children)}")
    print(f"View list: {folder_children}")
    print(f"IDs, type of children: {[(getattr(child, 'id', 'N/A'), type(child)) for child in folder_children]}")
        
    all_folder_items = service.get_all_folder_content(folder_id)
    print(f"All folder content for folder {folder_id}: {all_folder_items}")
    print(f"Total folder content items: {len(all_folder_items)}")
if __name__ == "__main__":
    tests()
