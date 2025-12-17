# Q3 Goals to GitHub Project Board

This project helps populate the AIND Scientific Computing GitHub project board with Q3 2025 goals from the planning spreadsheet.

## Files

- `parse_excel_goals.py` - Parses the Excel spreadsheet and extracts goals to JSON
- `q3_goals.json` - Contains all extracted goals (68 total)
- `populate_goals_on_github.py` - Creates GitHub issues and adds them to the project board
- `setup_github.py` - Helps set up required environment variables
- `verify_goals.py` - Verifies the extracted goals data

## Setup Instructions

### 1. Set up GitHub Token

1. Go to https://github.com/settings/tokens
2. Generate a new token with these permissions:
   - `repo` (for creating issues)
   - `project` (for adding to project boards)
3. Set the environment variable:
   ```bash
   export GITHUB_TOKEN='your_token_here'
   ```

### 2. Get Project ID

Run the setup script to get your project ID:
```bash
python setup_github.py
```

This will show you the project ID to use. Set it as an environment variable:
```bash
export GITHUB_PROJECT_ID='your_project_id_here'
```

### 3. Get Custom Field IDs (TODO)

You'll need to get the custom field IDs from your project board for:
- Team field
- Iteration field  
- Start date field
- End date field

These are currently placeholder values in the script.

## Usage

### Test Mode (Create 1 Issue)

To test with just one goal:
```python
main(test_mode=True)
```

### Full Import (Create All Issues)

To import all 68 goals:
```python
main()
```

## Features

- ✅ Loads credentials from environment variables
- ✅ Test mode for creating just one issue
- ✅ Duplicate detection - won't create issues that already exist
- ✅ Proper Q3 2025 iteration and dates (July 1 - Sept 30)
- ✅ Maps platforms to appropriate teams
- ✅ Rate limiting to be nice to GitHub API
- ✅ Simple template matching - uses risks field for both dependencies and risks sections

## Current Status

- ✅ Excel parsing complete (68 goals extracted)
- ✅ Platform mapping updated
- ✅ Environment variable support
- ✅ Test mode implemented
- ✅ Duplicate detection implemented
- ⏳ Need custom field IDs from project board
- ⏳ Ready for testing with one goal
