"""
Utility functions for Smartsheet Workspace Deletion application.

This module contains pure utility functions for date handling, string matching,
and other helper operations that don't depend on external clients or services.
"""


import re
import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Optional
from config import config


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
        logging.debug(f"'{date_string}' is on or before today ({todays_date}). Action can proceed.")
        return True
    else:
        logging.debug(f"'{date_string}' is in the future ({todays_date}). No action.")
        return False


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
    
    logging.info(
        f"EM Notification Date: {em_notification_date}, "
        f"Deletion Date: {deletion_date}, "
        f"Today's Date: {todays_date}"
    )
    logging.info(f"Should workspace be deleted? {proceed_with_deletion}")
    
    return proceed_with_deletion

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
