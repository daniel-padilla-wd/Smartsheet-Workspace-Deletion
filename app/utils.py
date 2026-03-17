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


def filter_intake_data(intake_sheet_data: SmartsheetSheet, todays_date: str) -> list[SmartsheetRow]:
    """
    Return rows whose deletion date is today or in the past.

    Args:
        intake_sheet_data: Smartsheet sheet object containing rows and cells.
        todays_date: Today's date in "YYYY-MM-DD" format.

    Returns:
        list[Any]: Filtered list of Smartsheet row objects.
    """
    filtered_rows: list[SmartsheetRow] = []
    deletion_date_col_id = config.COLUMN_TITLES["deletion_date"]

    for row in getattr(intake_sheet_data, "rows", []):
        deletion_date = None
        for cell in getattr(row, "cells", []):
            if getattr(cell, "column_id", None) == deletion_date_col_id:
                deletion_date = getattr(cell, "value", None)
                break

        if not deletion_date:
            continue

        date_string = str(deletion_date).split("T")[0]
        if is_date_past_or_today(date_string, todays_date):
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
    return string.split('?')[0]


def get_workspace_id_from_csv(folder_url: str, csv_file: str = "intake_sheet_w_workspaces_data.csv") -> Optional[int]:
    """
    Look up workspace ID from CSV file by matching folder URL.
    
    Args:
        folder_url: The folder URL to search for
        csv_file: Path to the CSV file containing workspace data
        
    Returns:
        int or None: The workspace ID if found, None otherwise
        
    Raises:
        FileNotFoundError: If the CSV file doesn't exist
        Exception: For other CSV reading errors
    """
    import pandas as pd
    
    try:
        workspace_df = pd.read_csv(csv_file)
        matched_row = workspace_df[workspace_df['folder_url_hyperlink'] == folder_url]
        
        if matched_row.empty:
            logging.warning(f"Could not find workspace ID for folder URL: {folder_url}")
            return None
        
        workspace_id = int(matched_row.iloc[0]['workspace_id'])
        logging.info(f"Found workspace ID {workspace_id} for folder URL: {folder_url}")
        return workspace_id
        
    except FileNotFoundError:
        logging.error(f"CSV file not found: {csv_file}")
        raise
    except Exception as e:
        logging.error(f"Error reading workspace data from CSV: {e}")
        raise


def setup_file_logging(session_name: str, log_dir: str = "logs") -> str:
    """
    Set up logging to both console and file.

    This function configures the root logger to output logs to both the console and a file.
    Useful for capturing logs from long-running operations while still seeing output.

    Args:
        session_name: Name of the session/function (used in log filename)
        log_dir: Directory to store logs (default: "logs")

    Returns:
        str: Path to the log file

    Example:
        log_file = setup_file_logging("workspace_verification")
        # Now all logging calls will also write to logs/workspace_verification_YYYYMMDD_HHMMSS.log
    """
    from pathlib import Path

    # Create logs directory if it doesn't exist
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_path / f"{session_name}_{timestamp}.log"

    # Set up file handler
    file_handler = logging.FileHandler(log_file, mode="w")
    file_handler.setLevel(logging.DEBUG)

    # Format for file logs
    file_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)

    # Add file handler to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)
    root_logger.setLevel(logging.DEBUG)

    logging.info(f"Logging to file: {log_file}")
    return str(log_file)


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
    expected_action: str = "KEEP_WORKSPACE"
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
