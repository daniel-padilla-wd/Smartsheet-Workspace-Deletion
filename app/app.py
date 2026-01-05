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
    
    # Process the deletion workflow
    sheet_url = "https://app.smartsheet.com/sheets/jgcJXmr2fhvvgv48XWWWvP2w2RrJ4Qjp75ff4VQ1"
    
    logging.info(f"Starting workspace deletion workflow for sheet: {sheet_url}")
    summary = ss_workflow.process_deletion_workflow(sheet_url)
    
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


if __name__ == "__main__":
    main()



