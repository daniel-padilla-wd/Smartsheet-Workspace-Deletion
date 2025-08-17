import smartsheet
import os
from dotenv import load_dotenv
import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re


# Environment configuration
load_dotenv()
logging.basicConfig(level=logging.INFO)

SMARTSHEET_ACCESS_TOKEN=os.getenv("SMARTSHEET_ACCESS_TOKEN")

# Initialize Smartsheet connection
smartsheet = smartsheet.Smartsheet(SMARTSHEET_ACCESS_TOKEN)  

# Aquire this through the sheet properties
mega_intake_sheet=os.getenv("MEGA_SHEET_ID")
column_titles=os.getenv("COLUMN_TITLES").split(",")

def is_workspaces_substring(string_a: str, string_b: str) -> bool:
    """
    Checks if the 'workspaces/*' substring from string_a is present in string_b.

    This function extracts the substring from string_a that starts with
    "workspaces/" and continues up to a potential wildcard character (*).
    It then checks if this extracted substring is found within string_b.

    Args:
        string_a: The string containing the pattern (e.g., 'path/to/workspaces/dev*').
        string_b: The string to search within (e.g., 'path/to/workspaces/dev-project').

    Returns:
        True if the 'workspaces' pattern from string_a is a substring of string_b,
        False otherwise.
    """
    # Define the regex pattern to capture the 'workspaces/' portion of string_a.
    # The pattern looks for 'workspaces/' followed by any characters, up to
    # a potential asterisk (*).
    # The parentheses create a capturing group for the part we want to extract.
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

def return_workspace_id(permalink: str) -> int:
    print(f"Searching for workspace with permalink: '{permalink}'")
    workspaces = smartsheet.Workspaces.list_workspaces(include_all=True).data
    for workspace in workspaces:
        print(f"Checking workspace: {workspace.name} with permalink {workspace.permalink}")
        if is_workspaces_substring(permalink, workspace.permalink):
            print(f"---------Found workspace with permalink {permalink}:----------")
            print(f"Workspace Information:\nID: {workspace.id}\nName: {workspace.name}\nPermalink: {workspace.permalink}")
            return workspace.id
    print(f"No workspace found with permalink: {permalink}")
    return None

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
    # print(f"Column IDs: {column_ids}")
    rows = smartsheet.Sheets.get_sheet(sheet_id).rows
    extracted_row_data = {}  # This dictionary will store data for the CURRENT row being processed
    print("--- Process Rows ---\n")
    for row in rows:
        # print("\n--- Row Data ---\n")
        # print(row)
        for cell in row.cells:
            if (cell.column_id in column_ids.values()) and cell.value != None:
                key_from_value = get_key_from_value(column_ids, cell.column_id)
                if key_from_value:
                    extracted_row_data[key_from_value] = cell.to_dict()
        print("--- Extracted Row Data ---\n")
        print(extracted_row_data,"\n")
        # After processing all cells in the row, we can now check the conditions
        print("--- Checking conditions for today's date... ---")
        try:
            is_today_em_notification = extracted_row_data["em_notification"]["value"] == get_pacific_today_date()
            #print(f"Is today EM Notification Date? {is_today_em_notification}", f"{extracted_row_data["em_notification"]["value"]}", f"{get_pacific_today_date()}")
            is_today_delete_date = extracted_row_data["delete_date"]["value"] == get_pacific_today_date()
            #print(f"Is today Delete Date? {is_today_delete_date}")

            if not is_today_em_notification:  # If today is NOT the EM notification date
                #print(f"EM Notification of Deletion Date: {extracted_row_data['em_notification']['value']}")
                if is_today_delete_date:  # AND today IS the delete date
                    print(f"Deletion Date: {extracted_row_data['delete_date']["value"]}")
                    print(f"PermaLink: {extracted_row_data["workspaces"]['hyperlink']['url']}")
                    print("Delete workspace in progress")
                    workspace_to_delete = return_workspace_id(extracted_row_data["workspaces"]['hyperlink']['url'])
                    if workspace_to_delete is None:
                        print("Workspace id not found, skipping deletion.")
                        continue
                    response = smartsheet.Workspaces.delete_workspace(workspace_to_delete)
                    if response.message == "SUCCESS":
                        print(f"Workspace with ID {workspace_to_delete} deleted successfully.")
        except KeyError as e:
            logging.error(f"KeyError: {e} - One of the required keys is missing in the row data.")
        print("--- End of Row ---\n")
            
    



return_row_data(mega_intake_sheet)

