"""
Repository layer for Smartsheet API interactions.

This module encapsulates all direct interactions with the Smartsheet API,
providing a clean interface for data access and manipulation. All API calls
and error handling are centralized here.
"""
import logging
from typing import Optional, List, Any, Dict
import smartsheet.exceptions



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
            all_sheets.extend(response.data)
            logging.info(f"Retrieved page 1/{response.total_pages} with {len(response.data)} sheets")
            
            # Get remaining pages
            for page in range(2, response.total_pages + 1):
                response = self.client.Sheets.list_sheets(include_all=True, page=page)
                all_sheets.extend(response.data)
                logging.info(f"Retrieved page {page}/{response.total_pages} with {len(response.data)} sheets")
            
            logging.info(f"Total sheets retrieved: {len(all_sheets)}")
            return all_sheets
        except smartsheet.exceptions.SmartsheetException as e:
            logging.error(f"Failed to list sheets: {e}")
            raise SmartsheetAPIError(f"Failed to list sheets: {e}")
    
    def list_workspaces(self) -> List[Any]:
        """
        Retrieve all workspaces from Smartsheet.
        
        Returns:
            List[Any]: List of workspace objects
            
        Raises:
            SmartsheetAPIError: If the API call fails
        """
        try:
            response = self.client.Workspaces.list_workspaces(include_all=True)
            return response.data
        except smartsheet.exceptions.SmartsheetException as e:
            logging.error(f"Failed to list workspaces: {e}")
            raise SmartsheetAPIError(f"Failed to list workspaces: {e}")

    def get_all_workspaces(self) -> List[Any]:
        """
        Retrieve all workspaces from Smartsheet using explicit pagination.

        Returns:
            List[Any]: List of all workspace objects from all pages

        Raises:
            SmartsheetAPIError: If the API call fails
        """
        try:
            all_workspaces = []
            last_key = None
            max_items = 1000

            # Token pagination with last_key/max_items replaces deprecated page/page_size.
            while True:
                response = self.client.Workspaces.list_workspaces(
                    last_key=last_key,
                    max_items=max_items,
                    pagination_type="token",
                )
                page_data = getattr(response, "data", []) or []
                # logging.debug(f"this is a page date:\n{page_data}")
                all_workspaces.extend(page_data)
                next_last_key = getattr(response, "last_key", None)

                logging.info(
                    f"Retrieved {len(page_data)} workspaces (running total: {len(all_workspaces)}). "
                    f"Has more pages: {bool(next_last_key)}"
                )

                if not next_last_key:
                    break
                last_key = next_last_key

            logging.info(f"Total workspaces retrieved: {len(all_workspaces)}")
            return all_workspaces
        except smartsheet.exceptions.SmartsheetException as e:
            logging.error(f"Failed to retrieve all workspaces: {e}")
            raise SmartsheetAPIError(f"Failed to retrieve all workspaces: {e}")

    def get_all_workspaces_as_dicts(self) -> List[Dict[str, Any]]:
        """
        Retrieve all workspaces and serialize each workspace model to a dictionary.

        Returns:
            List[Dict[str, Any]]: Serialized workspace dictionaries

        Raises:
            SmartsheetAPIError: If workspace retrieval fails
        """
        workspaces = self.get_all_workspaces()
        serialized: List[Dict[str, Any]] = []

        for workspace in workspaces:
            to_dict = getattr(workspace, "to_dict", None)
            if callable(to_dict):
                payload = to_dict()
                if isinstance(payload, dict):
                    serialized.append(payload)
                else:
                    serialized.append({"value": payload})
            else:
                # Fallback for unexpected objects that don't expose to_dict.
                fallback = vars(workspace)
                serialized.append(fallback if isinstance(fallback, dict) else {"value": fallback})

        return serialized
    
    def delete_workspace(self, workspace_id: int) -> bool:
        """
        Delete a workspace by its ID.
        
        Args:
            workspace_id: The ID of the workspace to delete
            
        Returns:
            bool: True if deletion was successful, False otherwise
            
        Raises:
            SmartsheetAPIError: If the API call fails with an unexpected error
        """
        try:
            response = self.client.Workspaces.delete_workspace(workspace_id)
            
            if response.message == "SUCCESS":
                logging.info(f"Workspace with ID {workspace_id} deleted successfully.")
                return True
            else:
                logging.error(f"Failed to delete workspace with ID {workspace_id}. Response: {response}")
                return False
                
        except smartsheet.exceptions.SmartsheetException as e:
            logging.error(f"Error deleting workspace {workspace_id}: {e}")
            raise SmartsheetAPIError(f"Failed to delete workspace {workspace_id}: {e}")
        
    def delete_folder(self, folder_id: int) -> bool:
        """
        Delete a folder by its ID.
        
        Args:
            folder_id: The ID of the folder to delete
            
        Returns:
            bool: True if deletion was successful, False otherwise
            
        Raises:
            SmartsheetAPIError: If the API call fails with an unexpected error
        """
        try:
            response = self.client.Folders.delete_folder(folder_id)
            logging.info(f"Delete folder response: {response}")
            
            if response.message == "SUCCESS":
                logging.info(f"Folder with ID {folder_id} deleted successfully.")
                return True
            else:
                logging.error(f"Failed to delete folder with ID {folder_id}. Response: {response}")
                return False
                
        except smartsheet.exceptions.SmartsheetException as e:
            logging.error(f"Error deleting folder {folder_id}: {e}")
            raise SmartsheetAPIError(f"Failed to delete folder {folder_id}: {e}")
    
    def get_workspace_children(self, workspace_id: int) -> List[Any]:
        """
        Retrieve all children (sheets, folders, reports, etc.) from a workspace.
        
        Args:
            workspace_id: The ID of the workspace
            
        Returns:
            List[Any]: List of workspace children objects
            
        Raises:
            SmartsheetAPIError: If the API call fails
        """
        try:
            
            response = self.client.Workspaces.get_workspace_children(
                workspace_id
            )
            #logging.info(f"Retrieved {len(response)} children for workspace {workspace_id}")
            logging.debug(f"Workspace {workspace_id} children: {response}")
            return response
            
        except smartsheet.exceptions.SmartsheetException as e:
            logging.error(f"Failed to get workspace children for {workspace_id}: {e}")
            raise SmartsheetAPIError(f"Failed to get workspace children for {workspace_id}: {e}")
        
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
            #logging.debug(f"Retrieved workspace {workspace_id}")
            return workspace
        except smartsheet.exceptions.SmartsheetException as e:
            if self._is_not_found_error(e):
                #logging.info(f"Workspace {workspace_id} not found (404)")
                return None
            logging.error(f"Failed to get workspace {workspace_id}: {e}")
            raise SmartsheetAPIError(f"Failed to get workspace {workspace_id}: {e}")
    
    def get_folder_children(self, folder_id: int) -> List[Any]:
        """
        Retrieve all children (sheets, folders, reports, etc.) from a folder.
        
        Args:
            folder_id: The ID of the folder
            
        Returns:
            List[Any]: List of folder children objects
            
        Raises:
            SmartsheetAPIError: If the API call fails
        """
        try:
            response = self.client.Folders.get_folder_children(
                    folder_id,
                )
            logging.info(f"Retrieved {len(response.data)} children for folder {folder_id}")
            logging.debug(f"Folder {folder_id} children: {response}")
            return response
            
        except smartsheet.exceptions.SmartsheetException as e:
            logging.error(f"Failed to get folder children for {folder_id}: {e}")
            raise SmartsheetAPIError(f"Failed to get folder children for {folder_id}: {e}")
    
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
    
    def update_cell(self, sheet_id: int, row_id: int, column_id: int, new_value: str) -> bool:
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
        #logging.info(f"Updating cell in row {row_id}, column {column_id} to '{new_value}'")
        
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
        
