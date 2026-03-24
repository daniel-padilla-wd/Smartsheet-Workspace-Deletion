"""
Repository layer for Smartsheet API interactions.

This module encapsulates all direct interactions with the Smartsheet API,
providing a clean interface for data access and manipulation. All API calls
and error handling are centralized here.
"""
import logging
from typing import Optional, List, Any
import smartsheet.exceptions
from smartsheet.models.sheet import Sheet as SmartsheetSheet
from smartsheet.models.folder import Folder as SmartsheetFolder
from smartsheet.models.sight import Sight as SmartsheetSight
from smartsheet.models.report import Report as SmartsheetReport
from smartsheet.models.template import Template as SmartsheetTemplate



class SmartsheetAPIError(Exception):
    """Raised when a Smartsheet API operation fails."""
    pass


class SmartsheetRepository:
    """
    Repository for Smartsheet API operations.
    
    This class handles all direct interactions with the Smartsheet API,
    including workspace operations, sheet operations, and cell updates.
    """
    
    def __init__(self, client):
        """
        Initialize the repository with a Smartsheet client.
        
        Args:
            client: Authenticated Smartsheet client instance
        """
        self.client = client

    @staticmethod
    def _is_not_found_error(error: Exception) -> bool:
        """Detect 404-style errors from Smartsheet SDK exception shapes."""
        status_code = getattr(getattr(error, "error", None), "status_code", None)
        if status_code is None:
            status_code = getattr(error, "status_code", None)
        if status_code == 404:
            return True
        return "404" in str(error)
    
    def get_current_user(self) -> Any:
        """
        Get information about the current authenticated user.
        
        Returns:
            User object
            
        Raises:
            SmartsheetAPIError: If the API call fails
        """
        try:
            current_user = self.client.Users.get_current_user()
            user_email = getattr(current_user, 'email', str(current_user))
            logging.info(f"Authenticated as: {user_email}")
            return current_user
        except smartsheet.exceptions.SmartsheetException as e:
            logging.error(f"Failed to get current user: {e}")
            raise SmartsheetAPIError(f"Failed to get current user: {e}")
        
    def get_workspace(self, workspace_id: int) -> Optional[Any]:
        """
        Retrieve workspace metadata by its ID.
        
        Args:
            workspace_id: The ID of the workspace
            
        Returns:
            Workspace object with metadata, or None if workspace not found (404)
            
        Raises:
            SmartsheetAPIError: If the API call fails with an error other than 404
        """
        try:
            workspace = self.client.Workspaces.get_workspace_metadata(workspace_id)
            logging.debug(f"Retrieved workspace {workspace_id}")
            return workspace
        except smartsheet.exceptions.SmartsheetException as e:
            if self._is_not_found_error(e):
                logging.info(f"Workspace {workspace_id} not found (404)")
                return None
            logging.error(f"Failed to get workspace {workspace_id}: {e}")
            raise SmartsheetAPIError(f"Failed to get workspace {workspace_id}: {e}")

    def get_all_workspaces(self) -> List[Any]:
        """
        Retrieve all workspaces from Smartsheet using token-based pagination.

        Returns:
            List[Any]: Flat list of all workspace objects available to the user

        Raises:
            SmartsheetAPIError: If the API call fails
        """
        try:
            all_workspaces: List[Any] = []
            last_key: Optional[str] = None
            max_items = 1000
            page_count = 0

            while True:
                response = self.client.Workspaces.list_workspaces(
                    last_key=last_key,
                    max_items=max_items,
                    pagination_type="token",
                )
                page_count += 1
                all_workspaces.extend(response.data)

                logging.debug(
                    f"Retrieved workspace page {page_count} with {len(response.data)} items"
                )

                last_key = response.last_key
                if not last_key:
                    break

            logging.info(f"Retrieved {len(all_workspaces)} total workspaces")
            return all_workspaces
        except smartsheet.exceptions.SmartsheetException as e:
            logging.error(f"Failed to retrieve all workspaces: {e}")
            raise SmartsheetAPIError(f"Failed to retrieve all workspaces: {e}")
        
    def get_all_workspace_children(self, workspace_id: int) -> List[Any]:
        """
        Retrieve all children from a workspace using token-based pagination.
        
        Args:
            workspace_id: The ID of the workspace
            
        Returns:
            List[Any]: Flat list of all workspace children objects
            
        Raises:
            SmartsheetAPIError: If the API call fails
        """
        try:
            all_children: List[Any] = []
            last_key: Optional[str] = None
            max_items = 1000
            page_count = 0

            while True:
                response = self.client.Workspaces.get_workspace_children(
                    workspace_id,
                    last_key=last_key,
                    max_items=max_items
                )
                page_count += 1
                all_children.extend(response.data)

                logging.debug(f"Retrieved workspace children page {page_count} with {len(response.data)} items")

                last_key = response.last_key
                if not last_key:
                    break

            logging.info(f"Retrieved {len(all_children)} total children for workspace {workspace_id}")
            return all_children
        except smartsheet.exceptions.SmartsheetException as e:
            logging.error(f"Failed to retrieve all workspace children for {workspace_id}: {e}")
            raise SmartsheetAPIError(f"Failed to retrieve all workspace children for {workspace_id}: {e}")
        
    def delete_workspace(self, workspace_id: int, safe_mode: bool = True) -> None:
        """
        Delete a workspace by its ID.
        
        Args:
            workspace_id: The ID of the workspace to delete
            
        Returns:
            bool: True if deletion was successful, False otherwise
            
        Raises:
            SmartsheetAPIError: If the API call fails with an unexpected error
        """
        if type(safe_mode) is not bool:
            raise ValueError(f"safe_mode parameter must be of type bool. Received type {type(safe_mode)} with value {safe_mode}")
        
        if not safe_mode:
            logging.warning(f"Safe mode is disabled. Workspace {workspace_id} will be permanently deleted without confirmation.")
            try:
                response = self.client.Workspaces.delete_workspace(workspace_id)
                logging.debug(f"Delete workspace response: {response}")
            except smartsheet.exceptions.SmartsheetException as e:
                logging.error(f"Error deleting workspace {workspace_id}: {e}")
                raise SmartsheetAPIError(f"Failed to delete workspace {workspace_id}: {e}")
        else:
            logging.info(f"SAFE MODE: Workspace {workspace_id} would be deleted. No action taken.")
        
    def get_all_folder_children(self, folder_id: int) -> List[Any]:
        """
        Retrieve all children from a folder using token-based pagination.
        
        Args:
            folder_id: The ID of the folder
            
        Returns:
            List[Any]: Flat list of all folder children objects
            
        Raises:
            SmartsheetAPIError: If the API call fails
        """
        try:
            all_children: List[Any] = []
            last_key: Optional[str] = None
            max_items = 1000
            page_count = 0

            while True:
                response = self.client.Folders.get_folder_children(
                    folder_id,
                    last_key=last_key,
                    max_items=max_items
                )
                page_count += 1
                all_children.extend(response.data)

                logging.debug(f"Retrieved folder children page {page_count} with {len(response.data)} items")

                last_key = response.last_key
                if not last_key:
                    break

            logging.info(f"Retrieved {len(all_children)} total children for folder {folder_id}")
            return all_children
        except smartsheet.exceptions.SmartsheetException as e:
            logging.error(f"Failed to retrieve all folder children for {folder_id}: {e}")
            raise SmartsheetAPIError(f"Failed to retrieve all folder children for {folder_id}: {e}")
        
    def delete_folder(self, folder_id: int, safe_mode: bool = True) -> None:
        """
        Delete a folder by its ID.
        
        Args:
            folder_id: The ID of the folder to delete
            
        Returns:
            bool: True if deletion was successful, False otherwise
            
        Raises:
            SmartsheetAPIError: If the API call fails with an unexpected error
        """
        if type(safe_mode) is not bool:
            raise ValueError(f"safe_mode parameter must be of type bool. Received type {type(safe_mode)} with value {safe_mode}")
        if not safe_mode:
            logging.warning(f"Safe mode is disabled. Folder {folder_id} will be permanently deleted without confirmation.")
            try:
                response = self.client.Folders.delete_folder(folder_id)
                logging.debug(f"Delete folder response: {response}")
            except smartsheet.exceptions.SmartsheetException as e:
                logging.error(f"Error deleting folder {folder_id}: {e}")
                raise SmartsheetAPIError(f"Failed to delete folder {folder_id}: {e}")
        else:
            logging.info(f"SAFE MODE: Folder {folder_id} would be deleted. No action taken.")

        
    def list_all_sheets(self) -> List[Any]:
        """
        Retrieve all sheets from Smartsheet.
        
        Returns:
            List[Any]: List of sheet objects
            
        Raises:
            SmartsheetAPIError: If the API call fails
        """
        try:
            all_sheets = []
            
            # Get first page
            response = self.client.Sheets.list_sheets(include_all=True)
            logging.info(f"Total sheets available: {response.total_count}, Total pages: {response.total_pages}")
            all_sheets.extend(response.data)
            logging.info(f"Retrieved page 1/{response.total_pages}.")

            # Get remaining pages
            for page in range(2, response.total_pages + 1):
                response = self.client.Sheets.list_sheets(include_all=True, page=page)
                all_sheets.extend(response.data)
                logging.info(f"Retrieved page {page}/{response.total_pages}.")
            
            return all_sheets
        except smartsheet.exceptions.SmartsheetException as e:
            logging.error(f"Failed to list sheets: {e}")
            raise SmartsheetAPIError(f"Failed to list sheets: {e}")
    
    def get_sheet(self, sheet_id: int) -> Any:
        """
        Retrieve a sheet by its ID.
        
        Args:
            sheet_id: The ID of the sheet to retrieve
            
        Returns:
            Sheet object with rows and metadata
            
        Raises:
            SmartsheetAPIError: If the API call fails
        """
        try:
            return self.client.Sheets.get_sheet(sheet_id)
        except smartsheet.exceptions.SmartsheetException as e:
            logging.error(f"Failed to get sheet {sheet_id}: {e}")
            raise SmartsheetAPIError(f"Failed to get sheet {sheet_id}: {e}")
        
    def delete_sheet(self, sheet_id: int, safe_mode:bool=True) -> None:
        """
        Delete a sheet by its ID.
        
        Args:
            sheet_id: The ID of the sheet to delete
            
        Returns:
            bool: True if deletion was successful, False otherwise
            
        Raises:
            SmartsheetAPIError: If the API call fails
        """
        if type(safe_mode) is not bool:
            raise ValueError(f"safe_mode parameter must be of type bool. Received type {type(safe_mode)} with value {safe_mode}")
        if not safe_mode:
            logging.warning(f"Safe mode is disabled. Sheet {sheet_id} will be permanently deleted without confirmation.")
            try:
                response = self.client.Sheets.delete_sheet(sheet_id)
                logging.debug(f"Delete sheet response: {response}")
            except smartsheet.exceptions.SmartsheetException as e:
                logging.error(f"Error deleting sheet {sheet_id}: {e}")
                raise SmartsheetAPIError(f"Failed to delete sheet {sheet_id}: {e}")
        else:
            logging.info(f"SAFE MODE: Sheet {sheet_id} would be deleted. No action taken.")
        
    def delete_sight(self, sight_id: int, safe_mode: bool = True) -> None:
        """
        Delete a sight by its ID.
        
        Args:
            sight_id: The ID of the sight to delete
            
        Returns:
            bool: True if deletion was successful, False otherwise
            
        Raises:
            SmartsheetAPIError: If the API call fails
        """
        if type(safe_mode) is not bool:
            raise ValueError(f"safe_mode parameter must be of type bool. Received type {type(safe_mode)} with value {safe_mode}")
        if not safe_mode:
            logging.warning(f"Safe mode is disabled. Sight {sight_id} will be permanently deleted without confirmation.")
            try:
                response = self.client.Sights.delete_sight(sight_id)
                logging.debug(f"Delete sight response: {response}")
            except smartsheet.exceptions.SmartsheetException as e:
                logging.error(f"Error deleting sight {sight_id}: {e}")
                raise SmartsheetAPIError(f"Failed to delete sight {sight_id}: {e}")
        else:
            logging.info(f"SAFE MODE: Sight {sight_id} would be deleted. No action taken.")
        
    def get_columns(self, sheet_id: int) -> List[Any]:
        """
        Retrieve all columns from a sheet.
        
        Args:
            sheet_id: The ID of the sheet
            
        Returns:
            List of column objects
            
        Raises:
            SmartsheetAPIError: If the API call fails
        """
        try:
            response = self.client.Sheets.get_columns(sheet_id, include_all=True)
            return response.data
        except smartsheet.exceptions.SmartsheetException as e:
            logging.error(f"Failed to get columns for sheet {sheet_id}: {e}")
            raise SmartsheetAPIError(f"Failed to get columns for sheet {sheet_id}: {e}")
    
    def update_cell(self, sheet_id: int, row_id: int, column_id: int, new_value: str, safe_mode: bool = True) -> bool:
        """
        Update a specific cell in a sheet.
        
        Args:
            sheet_id: The ID of the sheet
            row_id: The ID of the row containing the cell
            column_id: The ID of the column containing the cell
            new_value: The new value to set
            
        Returns:
            bool: True if update was successful, False otherwise
            
        Raises:
            SmartsheetAPIError: If the API call fails
        """
        if type(safe_mode) is not bool:
            raise ValueError(f"read_only parameter must be of type bool. Received type {type(safe_mode)} with value {safe_mode}")

        if not safe_mode:
            logging.warning(f"Safe mode is disabled. Cell in row {row_id}, column {column_id} of sheet {sheet_id} would be updated to '{new_value}' without confirmation.")
        
            try:
                # Build new cell value
                new_cell = self.client.models.Cell()
                new_cell.column_id = column_id
                new_cell.value = new_value
                new_cell.strict = False
                
                # Build the row to update
                new_row = self.client.models.Row()
                new_row.id = row_id
                new_row.cells.append(new_cell)
                
                # Update the row
                response = self.client.Sheets.update_rows(sheet_id, [new_row])
                # logging.info(f"Cell updated successfully: {response}")
                return True
                
            except smartsheet.exceptions.SmartsheetException as e:
                logging.error(f"Error updating cell: {e}")
                raise SmartsheetAPIError(f"Failed to update cell: {e}")
        else:
            logging.info(f"SAFE MODE: Cell in row {row_id}, column {column_id} of sheet {sheet_id} would be updated to '{new_value}'. No action taken.")
            return True
        
