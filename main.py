import smartsheet
import os
from dotenv import load_dotenv
import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Environment configuration
load_dotenv()
logging.basicConfig(level=logging.INFO)

SMARTSHEET_ACCESS_TOKEN=os.getenv("SMARTSHEET_ACCESS_TOKEN")

# Initialize Smartsheet connection
smartsheet = smartsheet.Smartsheet(SMARTSHEET_ACCESS_TOKEN)  

# Aquire this through the sheet properties
mega_intake_sheet=os.getenv("MEGA_SHEET_ID")
column_titles=os.getenv("COLUMN_TITLES").split(",")

def print_workspaces():
    workspaces = smartsheet.Workspaces.list_workspaces(include_all=True).data
    for workspace in workspaces:
        print(workspace)
        print(f"Workspace ID: {workspace.id}, Name: {workspace.name}")

def return_workspace_id(permalink: str) -> int:
    workspaces = smartsheet.Workspaces.list_workspaces(include_all=True).data
    for workspace in workspaces:
        if workspace.permalink == permalink:
            return workspace.id

def get_key_from_value(dictionary, value_to_find):
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
        # Define the Pacific timezone using ZoneInfo
        pacific_tz = ZoneInfo('America/Los_Angeles')
        # Get the current time directly in the Pacific timezone
        # datetime.now() with a tzinfo argument returns a timezone-aware datetime
        pacific_now = datetime.now(pacific_tz)
        # Format the date as YYYY-MM-DD
        formatted_date = pacific_now.strftime('%Y-%m-%d')
        return formatted_date
    except ZoneInfoNotFoundError:
        print("Error: 'America/Los_Angeles' timezone data not found.")
        print("Please ensure your system's timezone data is up-to-date or install the 'tzdata' package (`pip install tzdata`).")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

def get_column_ids() -> dict:
    columns = smartsheet.Sheets.get_columns(mega_intake_sheet,include_all=True).data
    column_ids = {}
    for column in columns:
        if column.title in column_titles:
            if column.title == column_titles[1]:  # Primary Column
                column_ids["delete_date"] = column.id
            elif column.title == column_titles[2]:  # EM Notification of Deletion Date
                column_ids["em_notification"] = column.id
            elif column.title == column_titles[3]:  # Workspaces
                column_ids["workspaces"] = column.id
    return column_ids

def return_row_data(sheet_id: int):
    column_ids=get_column_ids()
    print(f"Column IDs: {column_ids}")
    rows = smartsheet.Sheets.get_sheet(sheet_id).rows
    extracted_row_data = {}  # This dictionary will store data for the CURRENT row being processed
    for row in rows:
        print("\n--- Row Data ---\n")
        print(row)
        print("--- Processing Row Data ---\n")
        for cell in row.cells:
            print(cell)
            if (cell.column_id in column_ids.values()) and cell.value != None:
                key_from_value = get_key_from_value(column_ids, cell.column_id)
                if key_from_value:
                    extracted_row_data[key_from_value] = cell.to_dict()
                    print(f"Extracted {key_from_value}: {extracted_row_data[key_from_value]}")
        print("\n--- Extracted Row Data ---\n")
        print(extracted_row_data,"\n")
        print("--- End of Row ---\n")

        # After processing all cells in the row, we can now check the conditions
        print("--- Checking conditions for today's date... ---")
        try:
            is_today_em_notification = extracted_row_data["em_notification"]["value"] == get_pacific_today_date()
            print(f"Is today EM Notification Date? {is_today_em_notification}", f"{extracted_row_data["em_notification"]["value"]}", f"{get_pacific_today_date()}")
            is_today_delete_date = extracted_row_data["delete_date"]["value"] == get_pacific_today_date()
            print(f"Is today Delete Date? {is_today_delete_date}")

            if not is_today_em_notification:  # If today is NOT the EM notification date
                print(f"EM Notification of Deletion Date: {extracted_row_data['em_notification']['value']}")
                if is_today_delete_date:  # AND today IS the delete date
                    print(f"Deletion Date: {extracted_row_data['delete_date']['value']}")
                    print("Delete workspace in progress")
        except KeyError as e:
            logging.error(f"KeyError: {e} - One of the required keys is missing in the row data.")
            
    



return_row_data(mega_intake_sheet)

