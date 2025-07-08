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
    
def print_sheet_information():
    # Call the list_sheets() function and store the response object
    response = smartsheet.Sheets.list_sheets() 
    # Get the ID of the first sheet in the response     
    sheetId = response.data[0].id               
    # Load the sheet by using its ID
    sheet = smartsheet.Sheets.get_sheet(sheetId) 
    # Print information about the sheet
    print(f"The sheet {sheet.name} has {sheet.total_row_count} rows")   
    # Iterate through the list of sheets (each is a Smartsheet Sheet object)
    for sheet in response.data:
        print(f"Sheet ID: {sheet.id}, Name: {sheet.name}")
        # You can access other sheet properties like:
        print(f"Access Level: {sheet.access_level}")
        print(f"Permalink: {sheet.permalink}")

def print_columns():
    sheet_id = os.getenv("SHEET_ID")
    columns = smartsheet.Sheets.get_columns(sheet_id,include_all=True).data
    for column in columns:
        print(column.id)
        print(column.title)

def print_column_data():
    sheet_id = os.getenv("SHEET_ID")
    deletion_date_col_id= os.getenv("DELETION_DATE_ID")
    em_notification_col_id=os.getenv("EM_NOTIFICATION_ID")
    todays_date = get_pacific_today_date()

    rows = smartsheet.Sheets.get_sheet(sheet_id).rows
    for row in rows:
        print("Row")
        for cell in row.cells:
            if cell.column_id == em_notification_col_id:
                if cell.value != todays_date:
                    if cell.column_id == deletion_date_col_id:
                        if cell.value == todays_date:
                            #smartsheet.Workspaces.delete_workspace("workspace_id")
                            print("Delete PSA Project Name and all corresponding projects.")
    

print(print_column_data())