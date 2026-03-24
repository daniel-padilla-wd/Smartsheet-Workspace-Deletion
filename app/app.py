"""
Application entry point for Smartsheet workspace deletion with OAuth authentication.

This module works in both local and AWS Lambda environments:
- Local: Run with `python3 app_local_oauth.py`
- Lambda: Configure handler as `app_local_oauth.lambda_handler`
"""

import json
import logging
from config import config, ConfigurationError
from oauth_handler import get_smartsheet_client
from repository import SmartsheetRepository
from service import WorkspaceDeletionService
from pathlib import Path
from workspace_verification import (
    verify_project_status,
    delete_verified_workspaces,
)
from utils import ( 
    get_pacific_today_date,
    setup_file_logging,
    filter_intake_data
)

def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    # Validate OAuth configuration before proceeding
    try:
        config.validate_oauth_config()
        config.validate_sheet_config()
    except ConfigurationError as e:
        logging.error(f"Configuration error: {e}")
        return {"error": f"Configuration error: {e}"}
    
    # Get authenticated client via OAuth handler
    client = get_smartsheet_client(config.OAUTH_SCOPES)
    
    if not client:
        logging.error("Authentication failed. Check logs for details.")
        return {"error": "Authentication failed"}
        
    logging.info("Successfully authenticated with OAuth 2.0!")
    
    # Initialize repository and service
    ss_api = SmartsheetRepository(client)  
    ss_workflow = WorkspaceDeletionService(ss_api)
    
    # Verify authentication
    current_user = ss_api.get_current_user()
    logging.info(f"Authenticated as: {current_user.email if current_user else 'Unknown'}")
    
    # Determine which sheet ID to use based on DEV_MODE
    sheet_id = config.S_INTAKE_SHEET_ID if config.DEV_MODE else config.INTAKE_SHEET_ID
    
    # Process the deletion workflow
    logging.info(f"Starting workspace deletion workflow for sheet ID: {sheet_id}")
    summary = ss_workflow.process_deletion_workflow(sheet_id)
    
    # Display results
    if "error" in summary:
        logging.error(f"Workflow error: {summary['error']}")
    
    logging.info("=" * 60)
    logging.info("WORKFLOW SUMMARY")
    logging.info("=" * 60)
    logging.info(f"Total rows processed: {summary['processed_rows']}")
    logging.info(f"Successful deletions: {summary['successful_deletions']}")
    logging.info(f"Skipped: {summary['skipped']}")
    logging.info(f"Errors: {len(summary['errors'])}")
    
    if summary['errors']:
        logging.info("\nError details:")
        for error in summary['errors']:
            logging.error(f"  Row {error['row_index']}: {error['error']}")
    
    logging.info("=" * 60)
    
    return summary

def verify_main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    # Set up file logging for this session
    log_file = setup_file_logging("workspace_verification")

    try:
        config.validate_oauth_config()
    except ConfigurationError as err:
        error_msg = f"Configuration error: {err}"
        logging.error(error_msg)

    client = get_smartsheet_client(config.OAUTH_SCOPES)
    if not client:
        error_msg = "Authentication failed"
        logging.error(error_msg)

    repository = SmartsheetRepository(client)
    service = WorkspaceDeletionService(repository)

    intake_sheet_id = config.S_INTAKE_SHEET_ID if config.DEV_MODE else config.INTAKE_SHEET_ID

    logging.info(
        "Starting workspace verification workflow (no deletion operations enabled)"
    )
    intake_sheet = repository.get_sheet(int(intake_sheet_id))
    all_sheets = repository.list_all_sheets()

    todays_date = get_pacific_today_date()
    if not todays_date:
        error_msg = "Failed to get today's date"
        logging.error(error_msg)
        raise Exception(error_msg)
    
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

    deleted_workspaces = delete_verified_workspaces(log_entries, repository, service, safe_mode=True)
    print(f"Total entries marked as deleted: {len(deleted_workspaces)}")

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

'''
def lambda_handler(event, context):
    """
    AWS Lambda handler function.
    
    Configure in Lambda as: app_local_oauth.lambda_handler
    
    Args:
        event: Lambda event object
        context: Lambda context object
        
    Returns:
        dict: Response with statusCode and body (JSON formatted)
    """
    summary = main()
    
    if "error" in summary:
        return {
            'statusCode': 500,
            'body': json.dumps(summary)
        }
    
    return {
        'statusCode': 200,
        'body': json.dumps(summary)
    }

'''

if __name__ == "__main__":
    verify_main()



