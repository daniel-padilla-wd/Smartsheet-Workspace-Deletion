"""
Service layer for workspace deletion business logic.

This module contains the business logic for processing workspace deletions,
coordinating between the repository layer and utility functions. It orchestrates
the workflow without direct API calls.
"""

import logging
from typing import Dict, List, Optional, Any
from config import config
from smartsheet.models.sheet import Sheet as SmartsheetSheet
from smartsheet.models.row import Row as SmartsheetRow
from smartsheet.models.cell import Cell as SmartsheetCell
from smartsheet.models.sheet import Sheet as SmartsheetSheet
from smartsheet.models.row import Row as SmartsheetRow
from smartsheet.models.cell import Cell as SmartsheetCell
from smartsheet.models.folder import Folder as SmartsheetFolder
from smartsheet.models.sight import Sight as SmartsheetSight
from smartsheet.models.report import Report as SmartsheetReport
from smartsheet.models.template import Template as SmartsheetTemplate
from repository import SmartsheetRepository, SmartsheetAPIError
from utils import (
    should_workspace_be_deleted,
    get_pacific_today_date,
    get_key_from_value,
    is_workspaces_substring,
    is_pattern_substring,
    remove_query_string,
    validate_complete_cell_values,
    remove_query_string,
    RowLogEntry
)



class WorkspaceDeletionError(Exception):
    """Raised when workspace deletion process encounters an error."""
    pass


class WorkspaceDeletionService:
    """
    Service for managing workspace deletion workflow.
    
    This class contains the business logic for determining which workspaces
    should be deleted and orchestrating the deletion process.
    """
    
    def __init__(self, repository: SmartsheetRepository):
        """
        Initialize the service with a repository.
        
        Args:
            repository: SmartsheetRepository instance for data access
        """
        self.repository = repository
    
    # Move to utils.py
    def find_workspace(
        self,
        workspaces: List[Any],
        id: Optional[int] = None,
        name: Optional[str] = None,
        access_level: Optional[str] = None,
        perma_link: Optional[str] = None,
    ) -> Optional[Any]:
        """
        Find a workspace by matching only the provided filters.

        Args:
            workspaces: List of workspace objects to search through (required)
            id: Workspace ID
            name: Workspace name
            access_level: Workspace access level (for example: "ADMIN")
            perma_link: Workspace permalink

        Returns:
            Workspace object if a match is found, otherwise None

        Raises:
            WorkspaceDeletionError: If no filter parameter is provided or workspaces list is empty
        """
        if all(value is None for value in (id, name, access_level, perma_link)):
            raise WorkspaceDeletionError(
                "find_workspace requires at least one filter: id, name, access_level, or perma_link"
            )

        if not workspaces:
            logging.warning("find_workspace called with empty workspaces list")
            return None

        for workspace in workspaces:
            workspace_access_level = getattr(workspace, "access_level", None)
            if workspace_access_level is not None:
                workspace_access_level = str(workspace_access_level)

            if id is not None and workspace.id != id:
                continue
            if name is not None and workspace.name != name:
                continue
            if access_level is not None and workspace_access_level != access_level:
                continue
            if perma_link is not None and workspace.permalink != perma_link:
                continue
            return workspace
        return None
    
    # to utils.py
    def extract_row_data(self, row: SmartsheetRow) -> Dict[str, str]:
        """
        Extract relevant data from a sheet row.
        
        Args:
            row: The row object from Smartsheet
            column_ids: Dictionary mapping logical names to column IDs
            
        Returns:
            Dict containing extracted row data
        """
        extracted_data = {}
        target_columns = config.COLUMN_TITLES
        target_columns_ids = target_columns.values()
        
        for cell in row.cells:
            if (cell.column_id in target_columns_ids):
                if cell.column_id == target_columns["folder_url"]:
                    extracted_data.update({"folder_url": cell.hyperlink.url})
                    continue
                key = get_key_from_value(target_columns, cell.column_id)
                if key:
                    extracted_data.update({key: cell.value})
        
        return extracted_data
    
    # Move to utils.py
    def get_sheet_id_from_permalink(self, permalink: str, all_sheets: List[Any]) -> int:
        """
        Find a sheet ID from a pre-fetched list by exact permalink match.

        Args:
            permalink: The permalink URL to search for.
            all_sheets: Pre-fetched list of sheet objects to search through.

        Returns:
            int or None: The sheet ID if found, None otherwise.
        """
        clean_permalink = remove_query_string(permalink)
        sheet_id = next((item.id for item in all_sheets if item.permalink == clean_permalink), None)
        if sheet_id is None:
            logging.warning(f"No sheet found with permalink: {clean_permalink}")
            return 0
        return sheet_id

    def process_row_for_checks(self, smartsheet_row: SmartsheetRow, extracted_row_data: dict[str,str], all_sheets) -> RowLogEntry:
        """
        Process a single row to determine if it meets criteria for workspace deletion.
        This method extracts necessary data from the row and validates required fields.
        Args:
            row: SmartsheetRow object to process
        Returns:
            RowLogEntry containing extracted data and validation results
        """

        if not validate_complete_cell_values(smartsheet_row.cells):
            logging.warning(f"Row {smartsheet_row.id} failed validation checks, skipping: {smartsheet_row.cells}")
            return RowLogEntry(
                row_index=getattr(smartsheet_row, "row_number"),
                row_id=getattr(smartsheet_row, "id"),
                folder_url=extracted_row_data.get("folder_url"),
                deletion_date=extracted_row_data.get("deletion_date"),
                em_notification_date=extracted_row_data.get("em_notification_date"),
                deletion_status=extracted_row_data.get("deletion_status"),
                automation_action="SKIPPED - missing required fields: folder_url, deletion_date, or em_notification_date",
            )
        
        if extracted_row_data.get("deletion_status") == "Deleted":
            logging.warning(f"Row {smartsheet_row.row_number} already marked as 'Deleted', skipping")
            return RowLogEntry(
                row_index=getattr(smartsheet_row, "row_number"),
                row_id=getattr(smartsheet_row, "id"),
                folder_url=extracted_row_data.get("folder_url"),
                deletion_date=extracted_row_data.get("deletion_date"),
                em_notification_date=extracted_row_data.get("em_notification_date"),
                deletion_status=extracted_row_data.get("deletion_status"),
                automation_action="SKIPPED - workspace already appears deleted based on deletion_status column"
            )
        
        folder_url = str(extracted_row_data.get("folder_url"))
        clean_permalink = remove_query_string(folder_url)
        if "https://app.smartsheet.com/sheets/" not in clean_permalink:
            logging.warning(f"Row {smartsheet_row.row_number}: Folder URL does not appear to be a valid Smartsheet sheet permalink: {folder_url}")
            return RowLogEntry(
                row_index=getattr(smartsheet_row, "row_number"),
                row_id=getattr(smartsheet_row, "id"),
                folder_url=clean_permalink,
                deletion_date=extracted_row_data.get("deletion_date"),
                em_notification_date=extracted_row_data.get("em_notification_date"),
                deletion_status=extracted_row_data.get("deletion_status"),
                automation_action="SKIPPED - invalid sheet URL format"
            )
        
        found_sheet_id = self.get_sheet_id_from_permalink(clean_permalink, all_sheets)
        if not found_sheet_id:
            logging.warning(f"Row {smartsheet_row.row_number}: No sheet found with permalink: {clean_permalink}")
            return RowLogEntry(
                row_index=getattr(smartsheet_row, "row_number"),
                row_id=getattr(smartsheet_row, "id"),
                folder_url=clean_permalink,
                deletion_date=extracted_row_data.get("deletion_date"),
                em_notification_date=extracted_row_data.get("em_notification_date"),
                deletion_status=extracted_row_data.get("deletion_status"),
                automation_action="SKIPPED - no matching sheet found from folder URL; sheet DNE and corresponding workspace may have already been deleted"
            )

        return RowLogEntry(
            row_index=getattr(smartsheet_row, "row_number"),
            row_id=getattr(smartsheet_row, "id"),
            automation_action="CONTINUE"
        )
    
    def process_workspace_existence(self, smartsheet_row: SmartsheetRow, workspace_id:int) -> RowLogEntry:
        workspace = self.repository.get_workspace(workspace_id)
        if not workspace:
            return RowLogEntry(
                row_index=getattr(smartsheet_row, "row_number"),
                row_id=getattr(smartsheet_row, "id"),
                workspace_id=workspace_id,
                automation_action="SKIPPED - could not resolve workspace ID or permalink from sheet data"
            )
        return RowLogEntry(
            row_index=getattr(smartsheet_row, "row_number"),
            row_id=getattr(smartsheet_row, "id"),
            workspace_id=workspace_id,
            workspace_permalink=workspace.permalink,
            automation_action="CONTINUE"
        )
    
    def process_workspace_id_resolution(self, smartsheet_row: SmartsheetRow, extracted_row_data: dict[str,str], all_sheets) -> RowLogEntry:
        clean_permalink: str = remove_query_string(extracted_row_data["folder_url"])
        sheet_id: int = self.get_sheet_id_from_permalink(clean_permalink, all_sheets)
        sheet: SmartsheetSheet = self.repository.get_sheet(sheet_id)
        workspace_id: int = getattr(sheet.workspace, "id", 0)
        workspace_permalink: str = getattr(sheet.workspace, "permalink", "")
        if not workspace_id:
            logging.warning(f"Row {smartsheet_row.row_number}: No workspace ID for corresponding sheet.")
            return RowLogEntry(
                row_index=getattr(smartsheet_row, "row_number"),
                row_id=getattr(smartsheet_row, "id"),
                workspace_id=workspace_id,
                workspace_permalink=workspace_permalink,
                folder_url=clean_permalink,
                deletion_date=extracted_row_data.get("deletion_date"),
                em_notification_date=extracted_row_data.get("em_notification_date"),
                deletion_status=extracted_row_data.get("deletion_status"),
                automation_action="SKIPPED - could not resolve workspace ID or permalink from sheet data"
            )
        return RowLogEntry(
            row_index=getattr(smartsheet_row, "row_number"),
            row_id=getattr(smartsheet_row, "id"),
            workspace_id=workspace_id,
            workspace_permalink=workspace_permalink,
            folder_url=clean_permalink,
            deletion_date=extracted_row_data.get("deletion_date"),
            em_notification_date=extracted_row_data.get("em_notification_date"),
            deletion_status=extracted_row_data.get("deletion_status"),
            automation_action="CONTINUE"
        )
    
    def list_resource_items_recursively(
        self,
        resource_list: list[SmartsheetSheet | SmartsheetFolder | SmartsheetReport | SmartsheetSight | SmartsheetTemplate],
        parent_type: str = "workspace",
        parent_id: Optional[int] = None,
    ) -> list[SmartsheetSheet | SmartsheetFolder | SmartsheetReport | SmartsheetSight | SmartsheetTemplate]:

        all_resources_in_workspace = []
        for resource in resource_list:
            logging.debug(f"Processing {parent_type} {parent_id} resource: {getattr(resource, 'name', 'N/A')} (ID: {getattr(resource, 'id', 'N/A')})")
            if isinstance(resource, SmartsheetFolder):
                logging.debug(f"Recursively listing items in folder ID {resource.id}")
                # Recursively list items in the folder
                folder_id = getattr(resource, "id", 0)

                folder_contents = self.repository.get_folder_children(folder_id)
                child_resources = self.list_resource_items_recursively(
                    resource_list=folder_contents,  # Placeholder, replace with actual API call to get folder contents
                    parent_type="folder",
                    parent_id=folder_id,
                )
                all_resources_in_workspace.extend(child_resources)
            #elif isinstance(resource, (SmartsheetSheet, SmartsheetReport, SmartsheetSight, SmartsheetTemplate)):
        return all_resources_in_workspace
    
    def get_all_folder_content(self, folder_id: int) -> List[SmartsheetSheet | SmartsheetFolder | SmartsheetSight]:
        all_folder_content= []
        folder_contents: list = self.repository.get_all_folder_children(folder_id)
        for item in folder_contents:
            if isinstance(item, SmartsheetTemplate) or isinstance(item, SmartsheetReport):
                continue
            if isinstance(item, SmartsheetFolder):
                logging.debug(f"Found item in folder {folder_id}: {getattr(item, 'name', 'N/A')} (ID: {getattr(item, 'id', 'N/A')})")
                all_subfolder_content = []
                subfolder_contents:list = self.get_all_folder_content(item.id)
                all_subfolder_content.extend(subfolder_contents)
                all_folder_content.extend(all_subfolder_content)
            all_folder_content.append(item)
        return all_folder_content
        

    '''
    #######################################
    All legacy methods listed below. 
    #######################################
    '''
    # Legacy
    def find_sheet_by_permalink(self, permalink: str) -> Optional[int]:
        """
        Find a sheet ID by matching its permalink pattern.
        
        This is business logic that uses the repository to get data
        and applies filtering logic.
        
        Args:
            permalink: The permalink URL to search for
            
        Returns:
            int or None: The sheet ID if found, None otherwise
        """
        logging.info(f"Searching for sheet with permalink: {permalink}")
        
        try:
            sheets = self.repository.list_all_sheets()
        except SmartsheetAPIError as e:
            logging.error(f"Failed to list sheets: {e}")
            return None
        
        for sheet in sheets:
            sheet_info = {
                "id": sheet.id,
                "name": sheet.name,
                "permalink": sheet.permalink
            }
            
            if is_pattern_substring(permalink.split('?')[0], sheet.permalink, "sheets"):
                logging.info(f"Found matching sheet: {sheet_info}")
                return sheet.id
        
        logging.info(f"No sheet found with permalink: {permalink}")
        return None
    
    # legacy
    def find_workspace_by_permalink(self, permalink: str) -> Optional[int]:
        """
        Find a workspace ID by matching its permalink pattern.
        
        This is business logic that uses the repository to get data
        and applies filtering logic.
        
        Args:
            permalink: The permalink URL to search for
            
        Returns:
            int or None: The workspace ID if found, None otherwise
        """
        # logging.info(f"Searching for workspace with permalink: {permalink}")
        
        try:
            workspaces = self.repository.list_workspaces()
        except SmartsheetAPIError as e:
            logging.error(f"Failed to list workspaces: {e}")
            return None
        
        for workspace in workspaces:
            workspace_info = {
                "id": workspace.id,
                "name": workspace.name,
                "permalink": workspace.permalink
            }
            
            if is_workspaces_substring(permalink, workspace.permalink):
                logging.info(f"Found matching workspace: {workspace_info}")
                return workspace.id
        
        logging.info(f"No workspace found with permalink: {permalink}")
        return None

    def get_parent_workspace_id_from_sheet(self, permalink: str) -> Optional[int]:
        """
        Get the parent workspace ID for a given sheet permalink.

        Args:
            permalink (str): The permalink URL of the sheet.

        Returns:
            int: The ID of the parent workspace containing the sheet.

        Raises:
            Exception: If the sheet cannot be found by the permalink or if the sheet
                       is not associated with a workspace.
        """
        try:
            logging.info(f"Getting parent workspace ID for sheet with permalink: {permalink}")
            
            # Clean the permalink (remove query parameters)
            clean_permalink = remove_query_string(permalink)
            
            sheet_id = self.find_sheet_by_permalink(permalink=clean_permalink)
            if not sheet_id:
                logging.error(f"Could not find sheet with permalink: {clean_permalink}")
                return None
                
            sheet_data = self.repository.get_sheet(sheet_id)
            
            # Check if sheet belongs to a workspace
            if not hasattr(sheet_data, 'workspace') or not hasattr(sheet_data.workspace, 'id'):
                logging.error(f"Sheet {sheet_id} does not belong to a workspace")
                return None
                
            return sheet_data.workspace.id
            
        except Exception as e:
            logging.error(f"Failed to get parent workspace ID from sheet permalink: {permalink}. Error: {e}")
            return None
    
    def extract_row_data_with_column_ids(
        self, 
        row: Any, 
        folder_url_col_id: int,
        deletion_date_col_id: int,
        em_notification_col_id: int,
        status_col_id: int
    ) -> Dict[str, Any]:
        """
        Extract relevant data from a row using specific column IDs.
        
        This is a specialized extraction for the workspace deletion workflow.
        
        Args:
            row: The row object from Smartsheet
            folder_url_col_id: Column ID for folder URL
            deletion_date_col_id: Column ID for deletion date
            em_notification_col_id: Column ID for EM notification date
            status_col_id: Column ID for deletion status
            
        Returns:
            Dict containing extracted row data
        """
        extracted_data = {"row_id": row.id}
        
        target_column_ids = [
            folder_url_col_id,
            deletion_date_col_id,
            em_notification_col_id,
            status_col_id
        ]
        
        for cell in row.cells:
            if cell.column_id in target_column_ids:
                if cell.column_id == folder_url_col_id:
                    extracted_data["folder_url"] = cell.hyperlink.url
                elif cell.column_id == deletion_date_col_id:
                    extracted_data["deletion_date"] = cell.value
                elif cell.column_id == em_notification_col_id:
                    extracted_data["em_notification_date"] = cell.value
                elif cell.column_id == status_col_id:
                    extracted_data["deletion_status"] = cell.value
        
        return extracted_data
    
    def process_deletion_workflow(self, sheet_id: int) -> Dict[str, Any]:
        """
        Process the complete workspace deletion workflow for a given sheet.
        
        This is the main orchestration method that:
        1. Gets sheet data by ID
        2. Gets column IDs from config
        3. Processes each row
        4. Deletes workspaces when criteria are met
        5. Updates status
        
        Args:
            sheet_id: The ID of the intake sheet
            
        Returns:
            Dict containing processing summary
        """
        summary = {
            "processed_rows": 0,
            "successful_deletions": 0,
            "skipped": 0,
            "errors": []
        }
        
        # Get sheet data
        try:
            sheet = self.repository.get_sheet(sheet_id)
        except SmartsheetAPIError as e:
            error_msg = f"Failed to get sheet {sheet_id}: {e}"
            logging.error(error_msg)
            return {"error": error_msg, "summary": summary}
        
        # Get today's date
        todays_date = get_pacific_today_date()
        if not todays_date:
            error_msg = "Failed to get today's date"
            logging.error(error_msg)
            return {"error": error_msg, "summary": summary}
        
        # Process each row
        rows = sheet.rows
        logging.info(f"Processing {len(rows)} rows from sheet {sheet_id}")
        
        for i, row in enumerate(rows):
            try:
                logging.info(f"Processing row {i+1}/{len(rows)}: {row.id}")
                
                # Extract row data
                extracted_data = self.extract_row_data_with_column_ids(
                    row,
                    config.COLUMN_TITLES["folder_url"],
                    config.COLUMN_TITLES["deletion_date"],
                    config.COLUMN_TITLES["em_notification_date"],
                    config.COLUMN_TITLES["deletion_status"]
                )
                
                summary["processed_rows"] += 1

                # Get folder URL
                folder_url = extracted_data.get("folder_url")
                if not folder_url:
                    logging.warning(f"Row {row.id} missing folder URL, skipping")
                    summary["skipped"] += 1
                    continue

                # Check if workspace already deleted
                delete_status = extracted_data.get("deletion_status", "")
                if delete_status:
                    logging.info(f"Row {row.id} already marked as 'Deleted', skipping")
                    summary["skipped"] += 1
                    continue

                workspace_id = "get_workspace_id_from_csv(folder_url)"
                if workspace_id is None:
                    logging.info(f"Workspace already deleted or not found for folder URL: {folder_url}, skipping")
                    summary["skipped"] += 1
                    continue

                workspace_metadata = "self.repository.get_workspace(workspace_id)"
                if workspace_metadata is None:
                    logging.info(f"Workspace metadata not found for workspace ID: {workspace_id}, assuming already deleted")
                    summary["skipped"] += 1
                    logging.info("UPDATE CELL TO 'Deleted' STATUS")
                    try:
                        update_deletion_status = self.repository.update_cell(
                            sheet_id=sheet_id,
                            row_id=extracted_data["row_id"],
                            column_id=config.COLUMN_TITLES["deletion_status"],
                            new_value="Deleted"
                        )
                        if not update_deletion_status:
                            logging.warning(f"Failed to update deletion status for row {row.id}")
                        else:
                            logging.info(f"Updated deletion status for row {row.id}")
                            summary["successful_deletions"] += 1
                    except SmartsheetAPIError as e:
                        logging.error(f"Error updating status for row {row.id}: {e}")
                    continue

                # Check if required fields are present
                if "deletion_date" not in extracted_data or "em_notification_date" not in extracted_data:
                    logging.debug(f"Row {row.id} missing required date fields, skipping")
                    summary["skipped"] += 1
                    continue
                
                # Check deletion criteria
                if not should_workspace_be_deleted(
                    extracted_data["em_notification_date"],
                    extracted_data["deletion_date"],
                    todays_date
                ):
                    logging.debug(f"Row {row.id} does not meet deletion criteria")
                    summary["skipped"] += 1
                    continue
                
                logging.info(f"Workspace for row {row.row_number} should be deleted")
                
                # Get workspace ID from CSV lookup
                try:
                    workspace_id = "get_workspace_id_from_csv(folder_url)"
                    if workspace_id is None:
                        logging.error(f"Could not find workspace ID for folder URL: {folder_url}")
                        summary["errors"].append({
                            "row_index": i,
                            "row_id": row.id,
                            "error": "Folder URL not found in workspace data CSV"
                        })
                        summary["skipped"] += 1
                        continue
                        
                except FileNotFoundError:
                    #logging.error("intake_sheet_w_workspaces_data.csv not found")
                    summary["errors"].append({
                        "row_index": i,
                        "row_id": row.id,
                        "error": "Workspace data CSV file not found"
                    })
                    summary["skipped"] += 1
                    continue
                except Exception as e:
                    logging.error(f"Error reading workspace data CSV: {e}")
                    summary["errors"].append({
                        "row_index": i,
                        "row_id": row.id,
                        "error": f"CSV lookup error: {str(e)}"
                    })
                    summary["skipped"] += 1
                    continue

                # Process workspace contents
                logging.info(f"Processing contents of workspace ID: {workspace_id}")
                workspace_contents = self.process_workspace_contents(workspace_id)
                #logging.info(f"Workspace contents summary: {workspace_contents}")
                logging.info(f"workspace id: {workspace_id} contents - ")
                logging.info(f"sheets: {len(workspace_contents['sheets'])}, dashboards: {len(workspace_contents['dashboards'])}, skipped: {len(workspace_contents['skipped'])}, folders: {len(workspace_contents['folders'])}")

                # Delete contents before deleting workspace
                for folder in workspace_contents['folders']:
                    logging.info(f"Processing deletion of folder ID: {folder['id']} in workspace ID: {workspace_id}")
                    self.repository.delete_folder(folder['id'])

                
                # Delete workspace
                logging.info(f"Deleting workspace ID: {workspace_id}")
                try:
                    deletion_success = "self.repository.delete_workspace(workspace_id)"
                    if not deletion_success:
                        logging.error(f"Failed to delete workspace ID: {workspace_id}")
                        summary["errors"].append({
                            "row_index": i,
                            "row_id": row.id,
                            "error": f"Deletion failed for workspace {workspace_id}"
                        })
                        summary["skipped"] += 1
                        continue
                except SmartsheetAPIError as e:
                    logging.error(f"Error deleting workspace {workspace_id}: {e}")
                    summary["errors"].append({
                        "row_index": i,
                        "row_id": row.id,
                        "error": str(e)
                    })
                    summary["skipped"] += 1
                    continue
                
                logging.info(f"Workspace {workspace_id} deleted successfully")
                
                # Update deletion status
                try:
                    update_success = self.repository.update_cell(
                        sheet_id=sheet_id,
                        row_id=extracted_data["row_id"],
                        column_id=config.COLUMN_TITLES["deletion_status"],
                        new_value="Deleted"
                    )
                    if not update_success:
                        logging.warning(f"Failed to update deletion status for row {row.id}")
                    else:
                        logging.info(f"Updated deletion status for row {row.id}")
                        summary["successful_deletions"] += 1
                except SmartsheetAPIError as e:
                    logging.error(f"Error updating status for row {row.id}: {e}")
                    # Workspace was deleted but status update failed
                    summary["successful_deletions"] += 1
                    
            except Exception as e:
                logging.error(f"Unexpected error processing row {i}: {e}")
                summary["errors"].append({
                    "row_index": i,
                    "row_id": row.id if hasattr(row, 'id') else None,
                    "error": str(e)
                })
                summary["skipped"] += 1
        
        logging.info(f"Processing complete. Summary: {summary}")
        return summary

    
    
    def _process_children_recursive(self, children, summary, parent_type="workspace", parent_id=None):
        """
        Recursively process children of a workspace or folder.
        
        Args:
            children: List of child objects to process
            summary: Dictionary to accumulate results
            parent_type: Type of parent ("workspace" or "folder")
            parent_id: ID of parent object
        """
        for child in children:
            #logging.info(f"Processing {parent_type} child: {child})")

            if isinstance(child, dict):
                logging.warning(f"Child is a dict, skipping processing: {child}")
                summary["skipped"].append({"id": child.get('id', 'unknown'), "name": child.get('name', 'unknown'), "reason": "Child is a dict"})
                continue
            
            if "sheets" in child.permalink:
                #logging.info(f"Detected sheet {child.id} in {parent_type}")
                summary["sheets"].append({"id": child.id, "name": child.name, "permalink": child.permalink})
                    
            elif "dashboards" in child.permalink or "sights" in child.permalink:
                #logging.info(f"Detected dashboard {child.id} in {parent_type}")
                summary["dashboards"].append({"id": child.id, "name": child.name, "permalink": child.permalink})
                    
            elif "folders" in child.permalink:
                #logging.info(f"Detected folder {child.id} in {parent_type}")
                summary["folders"].append({"id": child.id, "name": child.name, "permalink": child.permalink})
                
                # Recursively process folder contents
                #logging.info(f"Getting folder contents for folder {child.id}...")
                folder_contents = self.repository.get_folder_children(child.id)
                folder_children = self._normalize_children(folder_contents)
                logging.info(f"Found {len(folder_children)} items in folder {child.id}")
                
                # Recursive call for folder children
                self._process_children_recursive(folder_children, summary, parent_type="folder", parent_id=child.id)

    def _normalize_children(self, children_response: Any) -> List[Any]:
        """Return children as a list whether SDK response is list-like or has .data."""
        if children_response is None:
            return []

        if isinstance(children_response, list):
            return children_response

        data = getattr(children_response, "data", None)
        if isinstance(data, list):
            return data

        try:
            return list(children_response)
        except TypeError:
            return []


    def process_workspace_contents(self, workspace_id):
        """
        Recursively process all contents of a workspace including nested folders.
        
        Args:
            workspace_id: ID of the workspace to process
            
        Returns:
            dict: Summary of items found/processed by type
        """
        summary = {
            "sheets": [],
            "dashboards": [],
            "reports": [],
            "skipped": [],
            "folders": []
        }
        
        # Get workspace children
        # logging.info(f"Getting workspace children for workspace {workspace_id}...")
        workspace_children = self.repository.get_workspace_children(workspace_id)
        normalized_workspace_children = self._normalize_children(workspace_children)
        logging.info(f"Found {len(normalized_workspace_children)} children items in workspace {workspace_id}")
        
        # Process all workspace children
        self._process_children_recursive(normalized_workspace_children, summary, parent_type="workspace", parent_id=workspace_id)
        
        #logging.info(f"Processing complete. Summary: {len(summary['sheets'])} sheets, {len(summary['dashboards'])} dashboards, {len(summary['reports'])} reports, {len(summary['folders'])} folders")
        
        return summary
    

    
