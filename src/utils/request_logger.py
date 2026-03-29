# IN YOUR routes/nlp.py FILE:

# REMOVE THIS LINE:
# from LARS.app import RequestResponseLogger

# ADD THIS INSTEAD (create the class directly in the file):

import logging
import json
from datetime import datetime
from fastapi import Request
import re

class RequestResponseLogger:
    """Simple logging for debugging - no Streamlit dependencies"""
    
    def __init__(self):
        self.logger = logging.getLogger("request_response")
        
    async def log_request_response(self, request: Request, response_data: dict):
        """Log request and response details"""
        timestamp = datetime.now().isoformat()
        
        # Extract basic request info
        request_info = {
            "method": request.method,
            "url": str(request.url),
            "query_params": dict(request.query_params),
        }
        
        # Log the details
        self.logger.error(f"=== REQUEST DEBUG {timestamp} ===")
        self.logger.error(f"URL: {request_info['url']}")
        self.logger.error(f"Method: {request_info['method']}")
        self.logger.error(f"Query Params: {request_info['query_params']}")
        self.logger.error(f"Response Success: {response_data.get('success', False)}")
        self.logger.error(f"Response Error: {response_data.get('error', 'None')}")
        self.logger.error(f"Retrieved Docs: {response_data.get('retrieved_docs_count', 0)}")
        self.logger.error(f"=== END REQUEST DEBUG ===")

def extract_year_from_text(text: str):
    """Extract year from text"""
    year_match = re.search(r'\b(202[2-5])\b', text)
    if year_match:
        return year_match.group(1)
    return None

# Then use this class in your endpoint instead of importing from LARS.app