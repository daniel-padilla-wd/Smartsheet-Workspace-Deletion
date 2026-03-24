"""
Utility functions for Smartsheet Workspace Deletion application.

This module contains pure utility functions for date handling, string matching,
and other helper operations that don't depend on external clients or services.
"""


import re
import logging
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from functools import wraps
from typing import Optional, Dict, Any, Callable, Iterable, TypeVar
from config import config
from smartsheet.models.sheet import Sheet as SmartsheetSheet
from smartsheet.models.row import Row as SmartsheetRow
from smartsheet.models.cell import Cell as SmartsheetCell
from smartsheet.models.folder import Folder as SmartsheetFolder
from smartsheet.models.sight import Sight as SmartsheetSight
from smartsheet.models.report import Report as SmartsheetReport
from smartsheet.models.template import Template as SmartsheetTemplate

@dataclass(frozen=True)
class RowLogEntry:
    """Structured row-level logging entry used by verification workflows."""

    row_index: int
    row_id: Optional[int] = None
    workspace_id: Optional[int] = None
    workspace_permalink: Optional[str] = None
    folder_url: Optional[str] = None
    deletion_date: Optional[str] = None
    em_notification_date: Optional[str] = None
    deletion_status: Optional[str] = None
    expected_action: str = "N/A"
    automation_action: str = "N/A"

    def to_dict(self) -> Dict[str, Any]:
        """Return normalized dictionary representation used by log output."""
        return {
            "row_index": self.row_index,
            "row_id": self.row_id or "N/A",
            "workspace_id": self.workspace_id or "N/A",
            "workspace_permalink": self.workspace_permalink or "N/A",
            "folder_url": self.folder_url or "N/A",
            "deletion_date": self.deletion_date or "N/A",
            "em_notification_date": self.em_notification_date or "N/A",
            "deletion_status": self.deletion_status or "N/A",
            "expected_action": self.expected_action,
            "automation_action": self.automation_action,
        }


T = TypeVar("T")
def limit_iterable(max_items: int) -> Callable[[Callable[..., Iterable[T]]], Callable[..., list[T]]]:
    """Limit iterable results from a function to the first max_items entries."""
    def decorator(func: Callable[..., Iterable[T]]) -> Callable[..., list[T]]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> list[T]:
            return list(func(*args, **kwargs))[:max_items]

        return wrapper

    return decorator


def get_pacific_today_date() -> Optional[str]:
    """
    Returns today's date in the configured timezone, formatted as 'YYYY-MM-DD'.
    
    Uses the timezone from config.TIMEZONE (defaults to 'America/Los_Angeles').
    
    Returns:
        str: The formatted date string (e.g., '2025-12-19') or None if error occurs.
    """
    try:
        tz = ZoneInfo(config.TIMEZONE)
        now = datetime.now(tz)
        formatted_date = now.strftime('%Y-%m-%d')
        return formatted_date
    except ZoneInfoNotFoundError:
        logging.error(f"Timezone '{config.TIMEZONE}' not found.")
        logging.warning("Please ensure your system's timezone data is up-to-date or install 'tzdata' package.")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred while getting today's date: {e}")
        return None


def is_date_past_or_today(date_string: str, todays_date: str) -> bool:
    """
    Compares a given date string to today's date.
    
    Args:
        date_string: The date string to compare, in "YYYY-MM-DD" format.
        todays_date: Today's date in "YYYY-MM-DD" format.
    
    Returns:
        bool: True if date_string is on or before today's date, False otherwise.
    """
    try:
        date_a = datetime.strptime(date_string, '%Y-%m-%d').date()
        date_b = datetime.strptime(todays_date, '%Y-%m-%d').date()
    except ValueError:
        logging.error(f"Invalid date format for '{date_string}'. Expected YYYY-MM-DD.")
        return False
    
    if date_a <= date_b:
        #logging.debug(f"'{date_string}' is on or before today ({todays_date}). Action can proceed.")
        return True
    else:
        #logging.debug(f"'{date_string}' is in the future ({todays_date}). No action.")
        return False
    
def validate_complete_cell_values(cells: list[SmartsheetCell]) -> bool:
    """
    Validates that a Smartsheet row has complete values for deletion date, EM notification date, and folder URL hyperlink.
     Args:
        row: SmartsheetRow object to validate.
    Returns:
        bool: True if all required values are present, False if any are missing.
    """
    for cell in cells:
        if getattr(cell, "column_id", None) == config.COLUMN_TITLES["deletion_date"]:
            deletion_date = getattr(cell, "value", None)
            #logging.info(f"Validating deletion date cell: {deletion_date}")
            if not deletion_date:
                return False
        elif getattr(cell, "column_id", None) == config.COLUMN_TITLES["em_notification_date"]:
            em_notification_date = getattr(cell, "value", None)
            #logging.info(f"Validating EM notification date cell: {em_notification_date}")
            if not em_notification_date:
                return False
            
    if not get_hyperlink_from_cell(cells):
        return False

    return True

def get_hyperlink_from_cell(cells: list[SmartsheetCell]) -> Optional[str]:
    """
    Extract the hyperlink from a Smartsheet row based on the configured column ID.

    Args:
        row: SmartsheetRow object containing cells with potential hyperlinks.
    Returns:
        str or None: The hyperlink value if found, otherwise None.
    """
    hyperlink_col_id = config.COLUMN_TITLES["folder_url"]
    for cell in cells:
        if getattr(cell, "column_id", None) == hyperlink_col_id:
            if getattr(cell, "hyperlink", None):
                cell_hyperlink = getattr(cell, "hyperlink")
                return getattr(cell_hyperlink, "url", None)
    return None


def filter_intake_data(intake_sheet_data: SmartsheetSheet, todays_date: Optional[str] = None, has_folder_url: Optional[bool] = None) -> list[SmartsheetRow]:
    """
    Return rows that satisfy one or both optional filters.

    Args:
        intake_sheet_data: Smartsheet sheet object containing rows and cells.
        todays_date: If provided, keep rows whose deletion date is today or in the past.
        has_folder_url: If provided, keep rows that either have (`True`) or do not have (`False`) a folder URL hyperlink.

    Returns:
        list[SmartsheetRow]: Filtered list of Smartsheet row objects.

    Raises:
        ValueError: If both `todays_date` and `has_folder_url` are None.
    """
    if todays_date is None and has_folder_url is None:
        raise ValueError("At least one of `todays_date` or `has_folder_url` must be provided")

    filtered_rows: list[SmartsheetRow] = []
    deletion_date_col_id = config.COLUMN_TITLES["deletion_date"]

    for row in getattr(intake_sheet_data, "rows", []):
        if has_folder_url is not None:
            row_has_folder_url = bool(get_hyperlink_from_cell(row.cells))
            if row_has_folder_url != has_folder_url:
                continue

        if todays_date is not None:
            deletion_date = None
            for cell in getattr(row, "cells", []):
                if getattr(cell, "column_id", None) == deletion_date_col_id:
                    deletion_date = getattr(cell, "value", None)
                    break

            if not deletion_date:
                continue

            date_string = str(deletion_date).split("T")[0]
            if not is_date_past_or_today(date_string, todays_date):
                continue

        filtered_rows.append(row)

    return filtered_rows


def should_workspace_be_deleted(em_notification_date: str, deletion_date: str, todays_date: str) -> bool:
    """
    Determines if a workspace should be deleted based on dates.
    
    Business logic: A workspace should be deleted if:
    - Today is on or after the deletion date AND
    - Today is NOT the EM notification date
    
    Args:
        em_notification_date: The EM notification date in 'YYYY-MM-DD' format.
        deletion_date: The deletion date in 'YYYY-MM-DD' format.
        todays_date: Today's date in 'YYYY-MM-DD' format.
    
    Returns:
        bool: True if the workspace should be deleted, False otherwise.
    """
    is_today_em_notification = em_notification_date == todays_date
    is_today_deletion_date = is_date_past_or_today(deletion_date, todays_date)
    proceed_with_deletion = is_today_deletion_date and not is_today_em_notification

    #logging.info(f"Should workspace be deleted? {proceed_with_deletion}")
    
    return proceed_with_deletion


def get_expected_action(
    deletion_date: Optional[str],
    em_notification_date: Optional[str],
    todays_date: str,
) -> str:
    """
    Determine the expected action for a workspace based on deletion criteria.

    Args:
        deletion_date: The deletion date in 'YYYY-MM-DD' format, or None/empty
        em_notification_date: The EM notification date in 'YYYY-MM-DD' format
        todays_date: Today's date in 'YYYY-MM-DD' format

    Returns:
        str: One of:
            - "MISSING_DELETION_DATE" if deletion_date is None or empty
            - "DELETE_WORKSPACE" if should_workspace_be_deleted() returns True
            - "KEEP_WORKSPACE" if should_workspace_be_deleted() returns False
    """
    if not deletion_date:
        return "MISSING_DELETION_DATE"

    if should_workspace_be_deleted(em_notification_date or "", deletion_date, todays_date):
        return "DELETE_WORKSPACE"
    else:
        return "KEEP_WORKSPACE"

def is_pattern_substring(string_a: str, string_b: str, pattern: str) -> bool:
    """
    Checks if the 'workspaces/*' substring from string_a is present in string_b.
    
    This function extracts a workspace path pattern from string_a and checks
    if it appears in string_b. Used for matching workspace permalinks.
    
    Args:
        string_a: The string containing the pattern (e.g., 'path/to/workspaces/dev*').
        string_b: The string to search within (e.g., 'path/to/workspaces/dev-project').
    
    Returns:
        bool: True if the 'workspaces' pattern from string_a is a substring of string_b,
              False otherwise.
    """
    # Define the regex pattern to capture 'workspaces/' followed by any characters
    regex_pattern = rf'({pattern}/.*)\*?'
    
    # Search for the pattern in string_a
    match = re.search(regex_pattern, string_a)
    
    if match:
        # Extract the captured group (the content inside the parentheses)
        workspaces_substring = match.group(1)
        logging.debug(f"Extracted substring: {workspaces_substring}")
        
        # Check if this extracted substring is in string_b
        return workspaces_substring in string_b
    
    # If no 'workspaces/' pattern is found in string_a, return False
    return False


def is_workspaces_substring(string_a: str, string_b: str) -> bool:
    """
    Checks if the 'workspaces/*' substring from string_a is present in string_b.
    
    This function extracts a workspace path pattern from string_a and checks
    if it appears in string_b. Used for matching workspace permalinks.
    
    Args:
        string_a: The string containing the pattern (e.g., 'path/to/workspaces/dev*').
        string_b: The string to search within (e.g., 'path/to/workspaces/dev-project').
    
    Returns:
        bool: True if the 'workspaces' pattern from string_a is a substring of string_b,
              False otherwise.
    """
    # Define the regex pattern to capture 'workspaces/' followed by any characters
    pattern = r'(workspaces/.*)\*?'
    
    # Search for the pattern in string_a
    match = re.search(pattern, string_a)
    
    if match:
        # Extract the captured group (the content inside the parentheses)
        workspaces_substring = match.group(1)
        
        # Check if this extracted substring is in string_b
        return workspaces_substring in string_b
    
    # If no 'workspaces/' pattern is found in string_a, return False
    return False


def get_key_from_value(dictionary: dict, value_to_find) -> Optional[str]:
    """
    Searches a dictionary for a given value and returns the first key.
    
    Args:
        dictionary: The dictionary to search.
        value_to_find: The value to look for.
    
    Returns:
        str or None: The key corresponding to the value, or None if not found.
    """
    for key, value in dictionary.items():
        if value == value_to_find:
            return key
    return None


def remove_query_string(string: str) -> str:
    """
    Removes the query string portion of a URL or string.
    
    Strips the '?' character and everything after it.
    
    Args:
        string: The string to clean (e.g., URL with query parameters)
    
    Returns:
        str: The cleaned string without query parameters
    
    Examples:
        >>> remove_query_string("https://example.com/path?param=value")
        'https://example.com/path'
        >>> remove_query_string("text without query")
        'text without query'
    """
    if type(string) != str:
        raise TypeError(f"Expected a string but got {type(string)}")
    return string.split('?')[0]


def setup_file_logging(session_name: str, log_dir: str = "logs", file_level: Optional[str] = None) -> str:
    """
    Set up file logging with configurable level.

    This function adds a file handler to the root logger without escalating the root logger level.
    The file handler level is independent from the console/root logger level, allowing detailed
    file logs while keeping console output clean.

    Args:
        session_name: Name of the session/function (used in log filename)
        log_dir: Directory to store logs (default: "logs")
        file_level: Logging level for file handler ("DEBUG", "INFO", "WARNING", "ERROR").
                   If None, uses config.FILE_LOGGING_LEVEL (default: "DEBUG")

    Returns:
        str: Path to the log file

    Example:
        log_file = setup_file_logging("workspace_verification")
        # File captures DEBUG, console stays at INFO (from basicConfig)
        
        log_file = setup_file_logging("workspace_verification", file_level="WARNING")
        # File captures WARNING and above only
    """
    from pathlib import Path

    # Use provided level or read from config
    if file_level is None:
        file_level = config.FILE_LOGGING_LEVEL
    
    # Validate logging level
    valid_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
    level_upper = file_level.upper()
    if level_upper not in valid_levels:
        raise ValueError(f"Invalid logging level '{file_level}'. Must be one of: {', '.join(valid_levels)}")
    
    # Create logs directory if it doesn't exist
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_path / f"{session_name}_{timestamp}.log"

    # Set up file handler with configured level
    file_handler = logging.FileHandler(log_file, mode="w")
    file_handler.setLevel(getattr(logging, level_upper))

    # Format for file logs
    file_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)

    # Add file handler to root logger
    # Note: We do NOT escalate the root logger level here.
    # The root logger level is set by basicConfig and stays independent from the file handler level.
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)

    logging.info(f"File logging initialized: {log_file} (level: {level_upper})")
    logging.debug(f"Root logger level: {logging.getLevelName(root_logger.level)}, Console output level: INFO (from basicConfig)")
    return str(log_file)




def build_row_log_entry(
    row_index: int,
    row_id: Optional[int] = None,
    workspace_id: Optional[int] = None,
    workspace_permalink: Optional[str] = None,
    folder_url: Optional[str] = None,
    deletion_date: Optional[str] = None,
    em_notification_date: Optional[str] = None,
    deletion_status: Optional[str] = None,
    expected_action: str = "KEEP_WORKSPACE",
    automation_action: str = "N/A",
) -> Dict[str, Any]:
    """
    Build a standardized row log entry dictionary.

    All optional values default to "N/A" if not provided.

    Args:
        row_index: Enumeration index of the row
        row_id: Smartsheet row ID
        folder_url: Folder/workspace URL
        deletion_date: Deletion date value
        em_notification_date: Email notification date
        deletion_status: Deletion status value
        expected_action: Expected action (DELETE_WORKSPACE, KEEP_WORKSPACE, MISSING_DELETION_DATE)
        automation_action: Action taken (e.g., "skipped", "cell updated", "marked deleted")

    Returns:
        Dict with standardized log structure
    """
    return RowLogEntry(
        row_index=row_index,
        row_id=row_id,
        workspace_id=workspace_id,
        workspace_permalink=workspace_permalink,
        folder_url=folder_url,
        deletion_date=deletion_date,
        em_notification_date=em_notification_date,
        deletion_status=deletion_status,
        expected_action=expected_action,
        automation_action=automation_action,
    ).to_dict()


def log_row_entry(entry: RowLogEntry | Dict[str, Any], level: str = "INFO") -> None:
    """
    Log a structured row entry at the specified level.

    Args:
        entry: Dictionary from build_row_log_entry()
        level: Logging level ("INFO", "DEBUG", "WARNING", "ERROR")
    """
    import json

    if isinstance(entry, RowLogEntry):
        entry = entry.to_dict()

    log_message = json.dumps(entry, indent=2)
    log_method = getattr(logging, level.lower(), logging.info)
    log_method(log_message)
