"""
Microapp to extract workspace and sheet IDs from intake sheet.
"""

import json
import csv
import logging
import time
import pandas as pd
from config import config, ConfigurationError
from oauth_handler import get_smartsheet_client
from repository import SmartsheetRepository


def extract_sheets(ss_api):
    """
    Extract all sheets with OWNER access.
    
    Args:
        ss_api: SmartsheetRepository instance
        
    Returns:
        list: Sheet records
    """
    logging.info("Fetching all sheets...")
    try:
        all_sheets = ss_api.list_all_sheets()
        logging.info(f"Retrieved {len(all_sheets)} sheets")
    except Exception as e:
        logging.error(f"Failed to list sheets: {e}")
        return []
    
    # Record sheet data
    sheet_records = []
    for sheet in all_sheets:
        record = {
            "id": sheet.id,
            "permalink": sheet.permalink
        }
        sheet_records.append(record)
    
    logging.info(f"Recorded {len(sheet_records)} sheets")
    return sheet_records


def extract_workspaces(ss_api):
    """
    Extract all workspaces with OWNER access.
    
    Args:
        ss_api: SmartsheetRepository instance
        
    Returns:
        list: Workspace records
    """
    logging.info("Fetching all workspaces...")
    try:
        all_workspaces = ss_api.list_workspaces()
        logging.info(f"Retrieved {len(all_workspaces)} workspaces")
    except Exception as e:
        logging.error(f"Failed to list workspaces: {e}")
        return []
    
    # Record workspace data
    workspace_records = []
    for workspace in all_workspaces:
        # Only record if accessLevel is OWNER
        access_level = workspace.access_level if hasattr(workspace, 'access_level') else None
        if access_level != "OWNER":
            continue
        
        record = {
            "id": workspace.id,
            "permalink": workspace.permalink
        }
        workspace_records.append(record)
    
    logging.info(f"Recorded {len(workspace_records)} workspaces with OWNER access")
    return workspace_records


def get_sheet_info(ss_api, sheet_id):
    """
    Get sheet information by sheet ID.
    
    Args:
        ss_api: SmartsheetRepository instance
        sheet_id: ID of the sheet to retrieve
        
    Returns:
        dict: Sheet info with name, id, permalink, workspace_id, workspace_name, workspace_permalink
              or None if not found
    """
    try:
        sheet = ss_api.get_sheet(sheet_id)
        
        info = {
            "name": sheet.name,
            "id": sheet.id,
            "permalink": sheet.permalink,
            "workspace_id": sheet.workspace.id if hasattr(sheet, 'workspace') and hasattr(sheet.workspace, 'id') else None,
            "workspace_name": sheet.workspace.name if hasattr(sheet, 'workspace') and hasattr(sheet.workspace, 'name') else None,
            "workspace_permalink": sheet.workspace.permalink if hasattr(sheet, 'workspace') and hasattr(sheet.workspace, 'permalink') else None
        }
        
        #logging.info(f"Retrieved sheet: {info['name']}: {info}")
        #logging.info(f"Retrieved sheet RAW: {sheet}")
        return info
    except Exception as e:
        logging.error(f"Failed to get sheet {sheet_id}: {e}")
        return None


def get_workspace_info(ss_api, workspace_id):
    """
    Get workspace information by workspace ID.
    
    Args:
        ss_api: SmartsheetRepository instance
        workspace_id: ID of the workspace to retrieve
        
    Returns:
        dict: Workspace info with name, id, permalink
              or None if not found
    """
    try:
        workspace = ss_api.client.Workspaces.get_workspace(workspace_id)
        
        info = {
            "name": workspace.name,
            "id": workspace.id,
            "permalink": workspace.permalink
        }
        
        logging.info(f"Retrieved workspace: {info['name']} (ID: {info['id']})")
        return info
    except Exception as e:
        logging.error(f"Failed to get workspace {workspace_id}: {e}")
        return None


def create_sheets_with_workspace_info(ss_api, input_file="matched_intake_sheet_data.csv", output_file="intake_sheet_w_workspaces_data.csv", batch_size=200, delay_seconds=2):
    """
    Create a CSV with sheet and workspace information.
    
    Reads sheets from input CSV, fetches workspace info for each,
    and writes enriched data to output CSV.
    
    Args:
        ss_api: SmartsheetRepository instance
        input_file: Input CSV file with sheet IDs
        output_file: Output CSV file with workspace info added
        batch_size: Number of API calls before adding a delay (default: 100)
        delay_seconds: Seconds to delay after each batch (default: 1)
        
    Returns:
        int: Number of records processed
    """
    logging.info(f"Reading sheet data from {input_file}...")
    df = pd.read_csv(input_file)
    
    # Add new columns for workspace info
    df['workspace_id'] = None
    df['workspace_name'] = None
    df['workspace_permalink'] = None
    
    logging.info(f"Fetching workspace info for {len(df)} sheets...")
    for count, (index, row) in enumerate(df.iterrows(), start=1):
        try:
            sheet_id = int(row['id'])
        except Exception as e:
            logging.error(f"Invalid sheet ID at row {index}: {row['id']}")
            continue
        logging.info(f"Processing sheet {count}/{len(df)}: {sheet_id}")
        sheet_info = get_sheet_info(ss_api, sheet_id)
        
        if sheet_info and sheet_info.get('workspace_id') is not None:
            df.at[index, 'workspace_id'] = sheet_info.get('workspace_id', None)
            df.at[index, 'workspace_name'] = sheet_info.get('workspace_name', None)
            df.at[index, 'workspace_permalink'] = sheet_info.get('workspace_permalink', None)
            #logging.info(f"Updated sheet {sheet_id}: workspace={sheet_info.get('workspace_name', None)}")
        
        # Add delay after every batch_size calls
        if count % batch_size == 0:
            logging.info(f"Processed {count} sheets, pausing for {delay_seconds} second(s)...")
            time.sleep(delay_seconds)
    
    # Filter out rows with no workspace
    df = df[df['workspace_id'].notna()]
    
    # Write to output CSV
    df.to_csv(output_file, index=False)
    logging.info(f"Wrote {len(df)} records to {output_file}")
    
    return len(df)


def write_to_csv(records, output_file):
    """
    Write records to CSV file using pandas.
    
    Args:
        records: List of dictionaries to write
        output_file: Output file path
        
    Returns:
        int: Number of records written
    """
    df = pd.DataFrame(records)
    df.to_csv(output_file, index=False)
    return len(records)


def extract_intake_sheet_data(ss_api, output_file="intake_sheet_data.csv"):
    """
    Extract Folder URL and row number from the intake sheet.
    
    Args:
        ss_api: SmartsheetRepository instance
        output_file: Output CSV file path
        
    Returns:
        int: Number of records extracted
    """
    logging.info("Fetching intake sheet...")
    
    try:
        # Get the intake sheet ID from config
        intake_sheet_id = config.INTAKE_SHEET_ID if not config.DEV_MODE else config.S_INTAKE_SHEET_ID
        folder_url_column_id = config.FOLDER_URL_ID if not config.DEV_MODE else config.S_FOLDER_URL_ID
        
        # Fetch the sheet
        sheet = ss_api.get_sheet(intake_sheet_id)
        logging.info(f"Retrieved intake sheet: {sheet.name} with {sheet.total_row_count} rows")
        
        # Extract data
        records = []
        for row in sheet.rows:
            # Find the Folder URL cell
            folder_url = None
            folder_url_hyperlink = None
            for cell in row.cells:
                if cell.column_id == folder_url_column_id:
                    folder_url = cell.value
                    # Check if cell has a hyperlink
                    if hasattr(cell, 'hyperlink') and cell.hyperlink:
                        folder_url_hyperlink = cell.hyperlink.url if hasattr(cell.hyperlink, 'url') else None
                    break
            
            record = {
                "row_number": row.row_number,
                "folder_url": folder_url,
                "folder_url_hyperlink": folder_url_hyperlink
            }
            records.append(record)
        
        # Write to CSV
        count = write_to_csv(records, output_file)
        logging.info(f"Wrote {count} records to {output_file}")
        return count
        
    except Exception as e:
        logging.error(f"Failed to extract intake sheet data: {e}")
        return 0


def match_intake_to_sheets(sheets_file="sheets_data.csv", intake_file="intake_sheet_data.csv", output_file="intake_sheet_data.csv"):
    """
    Match folder URLs from intake sheet to sheet IDs.
    
    Reads sheets_data.csv and intake_sheet_data.csv, matches folder_url_hyperlink
    to sheet permalinks, and adds folder_url_sheet_id column to intake data.
    
    Args:
        sheets_file: CSV file with sheet data (id, permalink)
        intake_file: CSV file with intake sheet data (row_number, folder_url, folder_url_hyperlink)
        output_file: Output CSV file (defaults to overwriting intake_file)
        
    Returns:
        int: Number of matches found
    """
    logging.info(f"Reading sheets data from {sheets_file}...")
    sheets_df = pd.read_csv(sheets_file)
    
    logging.info(f"Reading intake data from {intake_file}...")
    intake_df = pd.read_csv(intake_file)
    
    # Add new column for matched sheet ID
    intake_df['folder_url_sheet_id'] = None
    
    # Create a mapping of permalink to id from sheets_df
    permalink_to_id = dict(zip(sheets_df['permalink'], sheets_df['id']))
    
    logging.info(f"Matching {len(intake_df)} intake rows to sheets...")
    matches = 0
    for index, row in intake_df.iterrows():
        folder_url_hyperlink = row['folder_url_hyperlink']
        
        if pd.notna(folder_url_hyperlink) and folder_url_hyperlink in permalink_to_id:
            matched_id = permalink_to_id[folder_url_hyperlink]
            intake_df.at[index, 'folder_url_sheet_id'] = matched_id
            matches += 1
            logging.info(f"Row {row['row_number']}: Matched hyperlink to sheet ID {matched_id}")
        else:
            logging.debug(f"Row {row['row_number']}: No match found for {folder_url_hyperlink}")
    
    # Write to output CSV
    intake_df.to_csv(output_file, index=False)
    logging.info(f"Wrote {len(intake_df)} records with {matches} matches to {output_file}")
    
    return matches


def get_matched_intake_records(intake_file="intake_sheet_data.csv", output_file="matched_intake_sheet_data.csv"):
    """
    Get intake records that have a matched sheet ID.
    
    Reads intake_sheet_data.csv and returns only records with a value
    in the folder_url_sheet_id column.
    
    Args:
        intake_file: CSV file with intake sheet data
        output_file: Output CSV file path
        
    Returns:
        list: List of dictionaries with matched records
    """
    logging.info(f"Reading intake data from {intake_file}...")
    df = pd.read_csv(intake_file)
    
    # Filter for records with a id value
    matched_df = df[df['id'].notna()]
    
    # Convert numeric columns to integers
    matched_df['row_number'] = matched_df['row_number'].astype(int)
    matched_df['id'] = matched_df['id'].astype(int)
    
    logging.info(f"Found {len(matched_df)} matched records out of {len(df)} total")
    
    # Write to CSV
    matched_df.to_csv(output_file, index=False)
    logging.info(f"Wrote {len(matched_df)} matched records to {output_file}")
    
    # Convert to list of dictionaries
    records = matched_df.to_dict('records')
    return records


def main():
    """Main entry point."""
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    # Validate configuration
    try:
        config.validate_oauth_config()
        config.validate_sheet_config()
    except ConfigurationError as e:
        logging.error(f"Configuration error: {e}")
        return
    
    # Get authenticated client
    client = get_smartsheet_client(config.OAUTH_SCOPES)
    if not client:
        logging.error("Authentication failed")
        return
    
    logging.info("Successfully authenticated!")
    
    # Initialize repository
    ss_api = SmartsheetRepository(client)

    #test = get_sheet_info(ss_api, 7487459868757892)
    #logging.info(f"Test sheet info: {test}")
    
    # Extract sheets and workspaces
    #sheet_records = extract_sheets(ss_api)
    #workspace_records = extract_workspaces(ss_api)
    
    # Write to CSV files
    #sheets_count = write_to_csv(sheet_records, "sheets_data.csv")
    #print(f"Recorded {sheets_count} sheets to sheets_data.csv")
    
    #workspaces_count = write_to_csv(workspace_records, "workspace_data.csv")
    #print(f"Recorded {workspaces_count} workspaces to workspace_data.csv")

    # Match intake sheet URLs to sheet IDs
    #matches = match_intake_to_sheets()
    #print(f"Matched {matches} folder URLs to sheet IDs in intake_sheet_data.csv")

    #matched_intake_records = get_matched_intake_records()
    #matched_count = write_to_csv(matched_intake_records, "matched_intake_sheet_data.csv")
    #print(f"Wrote {matched_count} matched intake records to matched_intake_sheet_data.csv")
    
    # Create enriched CSV with workspace information
    #enriched_count = create_sheets_with_workspace_info(ss_api)
    #print(f"Created sheets_and_workspaces.csv with {enriched_count} enriched records")
    
    # Extract intake sheet data
    #intake_count = extract_intake_sheet_data(ss_api)
    #print(f"Recorded {intake_count} rows from intake sheet to intake_sheet_data.csv")

    # Get workspace info
    workspace_info = get_workspace_info(ss_api, 6700046944102276)
    logging.info(f"Workspace info: {workspace_info}")

    workspace_childs = ss_api.client.Workspaces.get_workspace_children(6700046944102276)
    logging.info(f"Workspace childs: {workspace_childs}")

    folder_id = 6632637314951044
    folder_contents = ss_api.client.Folders.get_folder_children(folder_id)
    logging.info(f"Folder contents: {folder_contents}")
    
    
    
    logging.info("Done!")


if __name__ == "__main__":
    main()
