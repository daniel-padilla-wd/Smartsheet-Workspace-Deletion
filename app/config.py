"""
Configuration management for Smartsheet Workspace Deletion application.

This module handles loading and validating all configuration from environment variables.
It provides a centralized place for all application settings.
"""

import os
from dotenv import load_dotenv
from typing import List
# Load environment variables from .env file
load_dotenv()


class ConfigurationError(Exception):
    """Raised when required configuration is missing or invalid."""
    pass


class Config:
    """
    Application configuration loaded from environment variables.
    
    This class provides validated access to all configuration settings
    required by the application.
    """
    # Mode
    PRODUCTION = False

    # Toggle this flag if you're running in the linux server. 
    # At this time (4/2), the windows server likely cannot read AWS Secrets. 
    LINUX_SERVER = False

    # OAuth Configuration
    CLIENT_ID: str = os.getenv('S_APP_CLIENT_ID', '') if not PRODUCTION else os.getenv('APP_CLIENT_ID', '')
    CLIENT_SECRET: str = os.getenv('S_APP_SECRET', '') if not PRODUCTION else os.getenv('APP_SECRET', '')
    REDIRECT_URI: str = 'http://localhost:8080/callback'
    TOKEN_FILE: str = 'smartsheet_token.json'
    
    # Smartsheet OAuth Endpoints
    AUTH_BASE: str = 'https://app.smartsheet.com/b/authorize'
    TOKEN_URL: str = 'https://api.smartsheet.com/2.0/token'
    
    # OAuth Scopes
    OAUTH_SCOPES: List[str] = [
        'READ_USERS',
        'READ_SHEETS',
        'WRITE_SHEETS',
        'DELETE_SHEETS',
        'ADMIN_WORKSPACES',
        'SHARE_SHEETS',
        'SHARE_SIGHTS'
    ]
    
    
    # SANDBOX Sheet Configuration
    S_INTAKE_SHEET_ID: int = 3553776142077828
    # Column IDs - to be set after fetching sheet details via API
    S_FOLDER_URL_ID: int = 8030922958655364
    S_DELETION_DATE_ID: int = 3568718757711748
    S_EM_NOTIFICATION_ID: int = 8072318385082244
    S_DELETION_STATUS_ID: int = 2055947308191620

    # PROD Sheet Configuration
    INTAKE_SHEET_ID: int = int(os.getenv('INTAKE_SHEET_ID', 0))
    # Column IDs - to be set after fetching sheet details via API
    FOLDER_URL_ID: int = 2443238423455620
    DELETION_DATE_ID: int = 7037757129287556
    EM_NOTIFICATION_ID: int = 4584188631011204
    DELETION_STATUS_ID: int = 3220373305773956

    # Column Titles Mapping
    COLUMN_TITLES: dict = {
        'folder_url': FOLDER_URL_ID if not PRODUCTION else S_FOLDER_URL_ID,
        'deletion_date': DELETION_DATE_ID if not PRODUCTION else S_DELETION_DATE_ID,
        'em_notification_date': EM_NOTIFICATION_ID if not PRODUCTION else S_EM_NOTIFICATION_ID,
        'deletion_status': DELETION_STATUS_ID if not PRODUCTION else S_DELETION_STATUS_ID,
    }

    # Application Settings
    LOG_LEVEL: str = 'INFO'
    FILE_LOGGING_LEVEL: str = os.getenv('FILE_LOGGING_LEVEL', 'DEBUG')
    CONSOLE_LOGGING_LEVEL: str = os.getenv('CONSOLE_LOGGING_LEVEL', 'INFO')
    TIMEZONE: str = os.getenv('TIMEZONE', 'America/Los_Angeles')
    
    @classmethod
    def validate_oauth_config(cls) -> None:
        """
        Validate that required OAuth configuration is present.
        
        Raises:
            ConfigurationError: If required OAuth settings are missing
        """
        missing = []
        
        client_id_var = 'S_APP_CLIENT_ID' if cls.PRODUCTION else 'APP_CLIENT_ID'
        client_secret_var = 'S_APP_SECRET' if cls.PRODUCTION else 'APP_SECRET'
        
        if not cls.CLIENT_ID:
            missing.append(client_id_var)
        if not cls.CLIENT_SECRET:
            missing.append(client_secret_var)
        
        if missing:
            raise ConfigurationError(
                f"Missing required OAuth configuration: {', '.join(missing)}. "
                "Please set these environment variables."
            )
    
    @classmethod
    def get_summary(cls) -> dict:
        """
        Get a summary of current configuration (safe for logging).
        
        Returns:
            dict: Configuration summary with sensitive values masked
        """
        return {
            'oauth': {
                'client_id': cls._mask_value(cls.CLIENT_ID),
                'client_secret': cls._mask_value(cls.CLIENT_SECRET),
                'redirect_uri': cls.REDIRECT_URI,
                'token_file': cls.TOKEN_FILE,
                'scopes': cls.OAUTH_SCOPES,
            },
            'sheet': {
                'column_titles': cls.COLUMN_TITLES,
            },
            'application': {
                'log_level': cls.LOG_LEVEL,
                'timezone': cls.TIMEZONE,
            }
        }
    
    @staticmethod
    def _mask_value(value: str, show_chars: int = 4) -> str:
        """
        Mask a sensitive value for safe logging.
        
        Args:
            value: The value to mask
            show_chars: Number of characters to show at the end
            
        Returns:
            str: Masked value (e.g., "****5678")
        """
        if not value:
            return '<not set>'
        if len(value) <= show_chars:
            return '****'
        return f"****{value[-show_chars:]}"


# Singleton instance for easy import
configuration = Config()
