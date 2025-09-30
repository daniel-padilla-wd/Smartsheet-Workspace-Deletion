# Smartsheet-Workspace-Deletion

### About this script

This Python script automates the deletion of Smartsheet workspaces based on data from a designated "Mega Intake" sheet. It identifies workspaces scheduled for deletion and marks them as "Deleted" in the sheet after a successful removal.

-----

### ⚙️ How It Works

The script performs the following steps:

1.  **Authentication**: It uses a Smartsheet API access token and a sheet ID from a `.env` file to connect to your Smartsheet account.
2.  **Date Check**: It fetches today's date in the Pacific Time Zone.
3.  **Row Processing**: It iterates through each row in the specified "Mega Intake" sheet.
4.  **Deletion Logic**: For each row, it checks two key dates:
      * **Deletion Date**: The script verifies if the designated deletion date for a workspace has passed or is today.
      * **EM Notification Date**: It ensures that today is not also the day when the project manager (EM) was notified. This prevents accidental deletion on the same day as the notification is sent.
5.  **Workspace Deletion**: If both conditions are met, the script extracts the workspace ID from the permalink, and then initiates the deletion process.
6.  **Status Update**: After a successful deletion, it updates the "Status" column for that row in the Smartsheet to "Deleted."

-----

### 🚀 Getting Started

#### Prerequisites

  * **Python**: Version 3.8 or higher.
  * **Smartsheet API Access Token**: You'll need a personal access token with **Admin** permissions to delete workspaces. You can generate one from your Smartsheet account settings.
  * **Smartsheet Sheet ID**: The ID of the sheet you'll be using as your intake list.
  * **Required Columns**: Your intake sheet must contain columns with the following titles to work correctly:
      * `Delete Date` (or similar, mapped to `column_titles[1]` in the code)
      * `EM Notification of Deletion Date` (mapped to `column_titles[2]`)
      * `Workspaces` (This column should contain the Smartsheet permalink, mapped to `column_titles[3]`)
      * `Status` (mapped to `column_titles[4]`)

#### Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/your-username/your-repo-name.git
    cd your-repo-name
    ```
2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
    This assumes you have a `requirements.txt` file. If not, you can create one with the following contents:
    ```
    smartsheet-python-sdk
    python-dotenv
    tzdata
    ```

#### Configuration

Create a `.env` file in the root directory of your project with the following variables:

```
SMARTSHEET_ACCESS_TOKEN="YOUR_API_ACCESS_TOKEN"
MEGA_SHEET_ID="YOUR_SHEET_ID"
COLUMN_TITLES="Primary Column Title,Delete Date,EM Notification of Deletion Date,Workspaces,Status"
```

  * **SMARTSHEET\_ACCESS\_TOKEN**: Your personal Smartsheet API token.
  * **MEGA\_SHEET\_ID**: The ID of your intake sheet.
  * **COLUMN\_TITLES**: A comma-separated list of the exact column titles in your sheet, in the correct order.

-----

### 🏃 How to Run

Simply execute the script from your terminal:

```bash
python your_script_name.py
```

The script will log its progress, including which rows it's processing and whether it's performing a deletion. The deletion step is currently commented out for safety (`#delete_workspace(workspace_to_delete)`). **To enable deletion, remove the `#` before this line.**

-----

### ⚠️ Important Notes

  * **Backup**: Deleting a Smartsheet workspace is permanent. It's highly recommended to back up any critical data before running this script.
  * **Permissions**: The API token must have sufficient permissions to list workspaces, get sheet data, and delete workspaces.
  * **Logging**: The script uses Python's `logging` module to provide detailed output on its progress and any errors encountered. Review the log output to monitor its execution.
  * **User Experience**: When a user clicks on a link of a deleted workspace, the user is redirected to a "You don't have permission to access this workspace" splash page.  Unfortunately, this is expected per Smartsheet team. Due to this experience, the user may assume the workspace still exists.
