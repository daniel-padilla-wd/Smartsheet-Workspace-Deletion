import smartsheet
import os
from dotenv import load_dotenv
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
import re


load_dotenv()
logging.basicConfig(level=logging.INFO)

SMARTSHEET_ACCESS_TOKEN=os.getenv("SMARTSHEET_ACCESS_TOKEN")

# Aquire this through the sheet properties
mega_intake_sheet=os.getenv("PROD_TEST_SHEET")
column_titles=os.getenv("COLUMN_TITLES").split(",")

class WorkspaceNotFoundError(Exception): pass
class InvalidDateError(Exception): pass

# config.py
class Config:
    # Loads and validates env vars
    pass

# repository.py
class SmartsheetRepository:
    # All API calls and error handling
    pass

# service.py
class WorkspaceDeletionService:
    # Business logic only, uses repository
    pass


def return_workspace_id(client, permalink: str) -> int:
    """
    Returns the workspace ID for a given permalink.

    Args:
        permalink (str): The permalink of the workspace to search for.
    Returns:
        int: The ID of the matching workspace, or None if not found.
    """
    def is_workspaces_substring(string_a: str, string_b: str)-> bool:
        """
        Checks if the 'workspaces/*' substring from string_a is present in string_b.

        Args:
            string_a (str): The string containing the pattern (e.g., 'path/to/workspaces/dev*').
            string_b (str): The string to search within (e.g., 'path/to/workspaces/dev-project').

        Returns:
            bool: True if the 'workspaces' pattern from string_a is a substring of string_b,
            False otherwise.
        """
        # Define the regex pattern to capture 'workspaces/' followed by any characters
        pattern = r'(workspaces/.*)\*?'
        
        # Search for the pattern in string_a
        match = re.search(pattern, string_a)
        
        if match:
            # If a match is found, extract the captured group (the content
            # inside the parentheses) which is our desired substring.
            workspaces_substring = match.group(1)
            
            # Now, check if this extracted substring is in string_b.
            return workspaces_substring in string_b
        
        # If no 'workspaces/' pattern is found in string_a, return False.
        return False
    
    logging.info(f"Searching for workspace with permalink: {permalink}")
    workspaces = client.Workspaces.list_workspaces(include_all=True).data
    for workspace in workspaces:
        workspace_obj = {
            "id": workspace.id,
            "name": workspace.name,
            "permalink": workspace.permalink
        }
        #logging.info(f"Checking workspace: {workspace_obj}")
        if is_workspaces_substring(permalink, workspace.permalink):
            logging.info(f"Found matching workspace: Information:\n{workspace_obj}")
            return workspace.id
    logging.info(f"No workspace found with permalink: {permalink}")
    return None
    
def delete_workspace(client, workspace_id: int):
    """
    Deletes a workspace by its ID.

    Args:
        workspace_id (int): The ID of the workspace to delete.
    """
    response = client.Workspaces.delete_workspace(workspace_id)
    if response.message == "SUCCESS":
        logging.info(f"Workspace with ID {workspace_id} deleted successfully.")
        return True
    else:
        logging.error(f"Failed to delete workspace with ID {workspace_id}. Response: {response}")
        return False
    

def get_column_ids(client, sheet_id: int) -> dict:
    """
    Retrieves the IDs of specific columns in a Smartsheet by their titles.

    Args:
        sheet_id (int): The ID of the Smartsheet to query.
    Returns:
        dict: A dictionary mapping column titles to their corresponding IDs.
    """
    columns = client.Sheets.get_columns(sheet_id,include_all=True).data
    column_ids = {}
    for column in columns:
        if column.title in column_titles:
            if column.title == column_titles[1]:  # Primary Column
                column_ids["delete_date"] = column.id
            elif column.title == column_titles[2]:  # EM Notification of Deletion Date
                column_ids["em_notification"] = column.id
            elif column.title == column_titles[3]:  # Workspaces
                column_ids["workspaces"] = column.id
            elif column.title == column_titles[4]:  # status
                column_ids["status"] = column.id
    return column_ids

def should_workspace_be_deleted(em_notification_date: str, deletion_date: str, todays_date: str) -> bool:
    """
    Determines if a workspace should be deleted based on the EM notification date,
    deletion date, and today's date.

    Args:
        em_notification_date (str): The EM notification date in 'YYYY-MM-DD' format.    
        delete_date (str): The deletion date in 'YYYY-MM-DD' format.
        today_date (str): Today's date in 'YYYY-MM-DD' format.
    Returns:
        bool: True if the workspace should be deleted, False otherwise.
    """
    def is_date_past_or_today(date_string: str, todays_date: str) -> bool:
        """
        Compares a given date string (date_string) to today's date (todays_date).

        Args:
            date_string (str): The date string to compare, in "YYYY-MM-DD" format.

        Returns:
            bool: True if Date A is on or before today's date, otherwise False.
        """

        try:
            # Parse the input date string into a datetime.date object
            # The format code '%m-%d-%Y' matches "MM-DD-YYYY"
            date_a = datetime.strptime(date_string, '%Y-%m-%d').date()
            date_b = datetime.strptime(todays_date, '%Y-%m-%d').date()
        except ValueError:
            print(f"Error: Invalid date format for '{date_string}'. Expected YYYY-MM-DD.")
            return False

        # Compare Date A to today's date
        # This comparison works because both are now datetime.date objects
        if date_a <= date_b:
            print(f"'{date_string}' is on or before today ({todays_date}). Action can proceed.")
            return True
        else:
            print(f"'{date_string}' is in the future ({todays_date}). No action.")
            return False
    is_today_em_notification = em_notification_date == todays_date
    is_today_deletion_date = is_date_past_or_today(deletion_date, todays_date)
    proceed_with_deletion = is_today_deletion_date and not is_today_em_notification
    logging.info(f"EM Notification Date: {em_notification_date}, Deletion Date: {deletion_date}, Today's Date: {todays_date}")
    logging.info(f"Should workspace be deleted? {proceed_with_deletion}")
    # Workspace should be deleted if today is the deletion date and NOT the EM notification date
    return proceed_with_deletion      

def update_cell(client, row_id: int, column_id: int, new_value: str):
    """ 
    Updates a specific cell in a Smartsheet row.

    Args:
        row_id (int): The ID of the row containing the cell to update.
        column_id (int): The ID of the column containing the cell to update.
        new_value (str): The new value to set in the cell.
    """
    logging.info(f"Updating cell in row {row_id}, column {column_id} to '{new_value}'")
    # Build new cell value
    new_cell = client.models.Cell()
    new_cell.column_id = column_id
    new_cell.value = new_value
    new_cell.strict = False
    # Build the row to update
    new_row = client.models.Row()
    new_row.id = row_id
    new_row.cells.append(new_cell)
    try:
        response = client.Sheets.update_rows(mega_intake_sheet, [new_row])
        logging.info(f"Cell updated successfully: {response}")
    except Exception as e:
        logging.error(f"Error updating cell: {e}")

def process_row(client, column_ids: dict, row: dict):
    """
    Processes a single row to determine if a workspace should be deleted.
    
    Args:
        client: The Smartsheet client instance.
        column_ids (dict): A dictionary mapping column titles to their IDs.
        row (dict): The row data to process.
    """
    def get_key_from_value(dictionary:dict, value_to_find)-> str:
        """
        Searches a dictionary for a given value and returns the first key
        associated with that value.

        Args:
            dictionary (dict): The dictionary to search.
            value_to_find: The value to look for.

        Returns:
            str or None: The key corresponding to the value, or None if the value is not found.
        """
        for key, value in dictionary.items():
            if value == value_to_find:
                return key
        return None
    
    def get_pacific_today_date()->str:
        """
        Returns today's date in the Pacific (Los Angeles) timezone,
        formatted as 'YYYY-MM-DD', using the zoneinfo module.

        Returns:
            str: The formatted date string (e.g., '2025-07-08').
        """
        try:
            pacific_now = datetime.now(ZoneInfo('America/Los_Angeles'))
            formatted_date = pacific_now.strftime('%Y-%m-%d')
            return formatted_date
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}")
            return None
    
    extracted_row_data = {} 
    extracted_row_data["row_id"]= row.id
    for cell in row.cells:
        if (cell.column_id in column_ids.values()) and cell.value != None:
            key_from_value = get_key_from_value(column_ids, cell.column_id)
            if key_from_value:
                extracted_row_data[key_from_value] = cell.to_dict()

    em_notification_date = extracted_row_data["em_notification"]["value"]
    deletion_date = extracted_row_data["delete_date"]["value"]
    todays_date = get_pacific_today_date()
    if should_workspace_be_deleted(em_notification_date, deletion_date, todays_date):
        logging.info(f"Extracted row data:\n {extracted_row_data}")
        logging.info("Conditions met for deletion. Proceeding to delete workspace.")
        workspace_to_delete = return_workspace_id(client, extracted_row_data['workspaces']['hyperlink']['url'])
        if workspace_to_delete is None:
            logging.warning("Workspace id not found, skipping deletion.")
            return
        logging.info(f"Workspace ID to delete: {workspace_to_delete}")
        # logging.warning("Deletion step is currently commented out for safety.")
        
        if not delete_workspace(client, workspace_to_delete):
            logging.warning("Workspace deletion failed, skipping row update.") 
            return
        update_cell(client, extracted_row_data["row_id"], column_ids["status"], "Deleted")


def process_workspace_deletions(client, sheet_id):
    """
    Minimal wrapper to allow external callers (e.g. Lambda) to reuse the
    existing helpers in this module while providing their own authenticated
    Smartsheet client.

    This function is intentionally non-invasive: it sets the module-level
    `smartsheet` variable to the provided `client` and then runs the same
    basic loop as `main()`, returning a small summary dict.
    """
    #global smartsheet
    #smartsheet = client

    summary = {"processed_rows": 0, "skipped": 0, "errors": []}
    try:
        column_ids = get_column_ids(client, sheet_id)
        rows = client.Sheets.get_sheet(sheet_id).rows
    except Exception as e:
        return {"error": "failed_to_fetch_sheet_or_columns", "detail": str(e)}

    for i, row in enumerate(rows):
        try:
            logging.info(f"Processing rows {i+1}/{len(rows)}:\n{row}")
            process_row(client, column_ids, row)
            summary["processed_rows"] += 1
        except Exception as e:
            summary["skipped"] += 1
            summary["errors"].append({"row_index": i, "error": str(e)})

    return summary

def main():
    logging.info("Starting Smartsheet Workspace Deletion Script.")
    # Initialize Smartsheet connection
    smartsheet_client = smartsheet.Smartsheet(SMARTSHEET_ACCESS_TOKEN)  
    logging.info(f"Using Mega Intake Sheet ID: {mega_intake_sheet}")
    logging.info(f"Using Column Titles: {column_titles}")
    logging.info("Fetching column IDs...")
    column_ids = get_column_ids(smartsheet_client,mega_intake_sheet)
    logging.info("Fetching rows...")
    rows = smartsheet_client.Sheets.get_sheet(mega_intake_sheet).rows

    logging.info(smartsheet_client.Users.get_current_user())

    for i, row in enumerate(rows):
        logging.info(f"Processing rows {i+1}/{len(rows)}:\n{row}")
        process_row(smartsheet_client, column_ids, row)
    
    logging.info("Smartsheet Workspace Deletion Script finished.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Script interrupted by user.")
    except Exception as e:
        logging.critical(f"Script terminated due to unhandled exception: {e}")