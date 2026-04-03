"""
Service layer for workspace deletion business logic.

This module contains the business logic for processing workspace deletions,
coordinating between the repository layer and utility functions. It orchestrates
the workflow without direct API calls.
"""

import logging
from typing import Dict, List, Optional, Any
from config import configuration
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
        target_columns = configuration.COLUMN_TITLES
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
    
    def get_all_workspace_content(self, workspace_id: int) -> List[SmartsheetSheet | SmartsheetFolder | SmartsheetSight]:
        all_workspace_content = []
        workspace_children: list = self.repository.get_all_workspace_children(workspace_id)
        for item in workspace_children:
            if isinstance(item, SmartsheetTemplate) or isinstance(item, SmartsheetReport):
                continue
            if isinstance(item, SmartsheetFolder):
                logging.debug(f"Found item in workspace {workspace_id}: {getattr(item, 'name', 'N/A')} (ID: {getattr(item, 'id', 'N/A')})")
                folder_content:list = self.get_all_folder_content(item.id)
                all_workspace_content.extend(folder_content)
            all_workspace_content.append(item)
        return all_workspace_content
    
    def delete_all_workspace_content(self, all_workspace_content: List[SmartsheetSheet | SmartsheetFolder | SmartsheetSight], safe_mode: bool = True) -> None:
        if type(safe_mode) is not bool:
            raise ValueError(f"safe_mode parameter must be of type bool. Received type {type(safe_mode)} with value {safe_mode}")
        
        if safe_mode:
            logging.info("Safe mode enabled - no deletions will be performed. The following items would be deleted:")

        for item in all_workspace_content:
            if isinstance(item, SmartsheetSheet):
                logging.debug(f"Deleting sheet {item.id} in workspace...")
                self.repository.delete_sheet(item.id, safe_mode=safe_mode)
            elif isinstance(item, SmartsheetFolder):
                logging.debug(f"Deleting folder {item.id} in workspace...")
                self.repository.delete_folder(item.id, safe_mode=safe_mode)
            elif isinstance(item, SmartsheetSight):
                logging.debug(f"Deleting sight {item.id} in workspace...")
                self.repository.delete_sight(item.id, safe_mode=safe_mode)
        logging.info("Workspace deletion complete.")

    def process_deletion_status_update(self, entry: RowLogEntry, safe_mode: bool = True) -> RowLogEntry:
        if type(safe_mode) is not bool:
            raise ValueError(f"read_only parameter must be of type bool. Received type {type(safe_mode)} with value {safe_mode}")
        
        status = "Deleted" if not safe_mode else "SAFE MODE: Deleted"
        
        try:
            self.repository.update_cell(
                sheet_id=configuration.S_INTAKE_SHEET_ID if configuration.PRODUCTION else configuration.INTAKE_SHEET_ID,
                row_id=entry.row_id,
                column_id=configuration.COLUMN_TITLES["deletion_status"],
                new_value="Deleted",
                safe_mode=safe_mode
            )
            return RowLogEntry(
                row_index=entry.row_index,
                row_id=entry.row_id,
                workspace_id=entry.workspace_id,
                workspace_permalink=entry.workspace_permalink,
                folder_url=entry.folder_url,
                deletion_date=entry.deletion_date,
                em_notification_date=entry.em_notification_date,
                deletion_status=status,
                expected_action=entry.expected_action,
                automation_action="WORKSPACE_DELETED" if not safe_mode else "SAFE MODE: WORKSPACE_DELETED",
            )
        except SmartsheetAPIError as e:
            logging.error(f"Error updating deletion status for row {entry.row_id}: {e}")
            return RowLogEntry(
                row_index=entry.row_index,
                row_id=entry.row_id,
                workspace_id=entry.workspace_id,
                workspace_permalink=entry.workspace_permalink,
                folder_url=entry.folder_url,
                deletion_date=entry.deletion_date,
                em_notification_date=entry.em_notification_date,
                deletion_status=f"FAILED_TO_UPDATE_STATUS: {status}",
                expected_action=entry.expected_action,
                automation_action=f"ERROR UPDATING STATUS: {str(e)}"
            )