"""
AIND metadata service interactions.
"""

import requests
import json


def fetch_procedures_metadata(subject_id):
    """
    Fetch procedures metadata for a subject from AIND metadata service.
    
    Args:
        subject_id: Subject ID to fetch metadata for
        
    Returns:
        tuple: (success: bool, data: dict or None, message: str)
    """
    base_url = "http://aind-metadata-service"
    url = f"{base_url}/procedures/{str(subject_id)}"
    
    print(f"  Fetching procedures from: {url}")
    
    try:
        response = requests.get(url)
        print(f"    Response status: {response.status_code}")
        
        if response.status_code == 200:
            rj = response.json()
            data = rj.get("data")
            message = rj.get("message", "Success")
            
            if data is not None:
                return True, data, message
            else:
                return False, None, f"No data returned: {message}"
        
        elif response.status_code == 406:
            # 406 responses often still contain the data we need
            rj = response.json()
            data = rj.get("data")
            message = rj.get("message", "Success despite validation errors")
            
            if data is not None:
                return True, data, f"Success (with validation warnings): {message}"
            else:
                return False, None, f"406 error and no data: {message}"
        else:
            response.raise_for_status()
            
    except requests.exceptions.RequestException as e:
        return False, None, f"Request failed: {str(e)}"
    except json.JSONDecodeError as e:
        return False, None, f"JSON decode error: {str(e)}"
    except Exception as e:
        return False, None, f"Unexpected error: {str(e)}"
