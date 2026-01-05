"""
Repository layer for Smartsheet API interactions.

This module encapsulates all direct interactions with the Smartsheet API,
providing a clean interface for data access and manipulation. All API calls
and error handling are centralized here.
"""
import json
import logging
from typing import Optional, List, Dict, Any
from utils import is_workspaces_substring
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

    def list_all_sheets(self) -> List[Any]:
        """
        Retrieve all sheets from Smartsheet.
        
        Returns:
            List[Any]: List of sheet objects
            
        Raises:
            SmartsheetAPIError: If the API call fails
        """
        try:
            response = self.client.Sheets.list_sheets(include_all=True)
            return response.data
        except Exception as e:
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
        except Exception as e:
            logging.error(f"Failed to list workspaces: {e}")
            raise SmartsheetAPIError(f"Failed to list workspaces: {e}")
    
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
                
        except Exception as e:
            logging.error(f"Error deleting workspace {workspace_id}: {e}")
            raise SmartsheetAPIError(f"Failed to delete workspace {workspace_id}: {e}")
    
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
        response_ss_object = self.client.Sheets.get_sheet(sheet_id)
        response = response_ss_object.to_dict()
        
        if "result" in response and isinstance(response["result"], dict):
            result = response["result"]
            if "errorCode" in result or "statusCode" in result:
                error_code = result.get("errorCode", result.get("statusCode"))
                error_msg = result.get("message", "Unknown error")
                logging.error(f"Failed to get sheet {sheet_id}: {error_msg} (code: {error_code})")
                raise SmartsheetAPIError(
                    f"Failed to get sheet: {sheet_id}: {json.dumps(result, indent=4)})"
                )
        
        return response_ss_object
        
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
        except Exception as e:
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
        logging.info(f"Updating cell in row {row_id}, column {column_id} to '{new_value}'")
        
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
            logging.info(f"Cell updated successfully: {response}")
            return True
            
        except Exception as e:
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
        except Exception as e:
            logging.error(f"Failed to get current user: {e}")
            raise SmartsheetAPIError(f"Failed to get current user: {e}")
        
