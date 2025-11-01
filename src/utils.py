"""
Utility functions for retry logic, messaging, file management, and checkpoint handling.
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from functools import wraps

# Simple print-based messaging (no logging)
def log_info(message: str):
    """Print info message."""
    print(f"[INFO] {message}")

def log_warning(message: str):
    """Print warning message."""
    print(f"[WARNING] {message}")

def log_error(message: str):
    """Print error message."""
    print(f"[ERROR] {message}")

def log_debug(message: str):
    """Print debug message (no-op in production)."""
    pass


def ensure_directory(path: str) -> None:
    """Ensure a directory exists, create if it doesn't."""
    Path(path).mkdir(parents=True, exist_ok=True)


def save_json(data: Any, filepath: str) -> None:
    """Save data to a JSON file."""
    ensure_directory(os.path.dirname(filepath))
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_json(filepath: str) -> Optional[Dict]:
    """Load data from a JSON file."""
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        log_error(f"Error loading JSON from {filepath}: {e}")
        return None


def save_checkpoint(project: str, last_page: int, checkpoint_file: str = "checkpoints/state.json") -> None:
    """Save checkpoint state for a project."""
    ensure_directory(os.path.dirname(checkpoint_file))
    
    state = load_json(checkpoint_file) or {}
    if project not in state:
        state[project] = {}
    
    state[project]["last_fetched_page"] = last_page
    state[project]["last_updated"] = time.time()
    
    save_json(state, checkpoint_file)
    log_info(f"Checkpoint saved: {project} at page {last_page}")


def load_checkpoint(project: str, checkpoint_file: str = "checkpoints/state.json") -> int:
    """Load checkpoint state for a project, return last fetched page number."""
    state = load_json(checkpoint_file)
    if state and project in state:
        last_page = state[project].get("last_fetched_page", 0)
        log_info(f"Resuming {project} from page {last_page}")
        return last_page
    return 0


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 2.0,
    exponential_base: float = 2.0,
    max_delay: float = 60.0,
    retryable_errors: tuple = (0, 429, 500, 502, 503, 504)  # 0 = timeout/connection errors
):
    """
    Decorator for retrying function calls with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        exponential_base: Base for exponential backoff
        max_delay: Maximum delay in seconds
        retryable_errors: Tuple of HTTP status codes to retry on
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    # Check if it's a retryable HTTP error
                    if hasattr(e, 'status_code'):
                        status_code = e.status_code
                        
                        if status_code not in retryable_errors:
                            log_error(f"Non-retryable error {status_code}: {e}")
                            raise
                        
                        if status_code == 429:
                            # Rate limit: wait for max_delay
                            wait_time = max_delay
                            log_warning(f"Rate limited (429). Waiting {wait_time}s before retry...")
                        elif status_code == 0:
                            # Connection error or timeout: exponential backoff
                            wait_time = min(
                                initial_delay * (exponential_base ** attempt),
                                max_delay
                            )
                            log_warning(f"Connection/timeout error on attempt {attempt + 1}/{max_retries + 1}. Retrying in {wait_time}s...")
                        else:
                            # Other 5xx errors: exponential backoff
                            wait_time = min(
                                initial_delay * (exponential_base ** attempt),
                                max_delay
                            )
                            log_warning(f"Error {status_code} on attempt {attempt + 1}/{max_retries + 1}. Retrying in {wait_time}s...")
                    else:
                        # Unknown error: exponential backoff
                        wait_time = min(
                            initial_delay * (exponential_base ** attempt),
                            max_delay
                        )
                        log_warning(f"Error on attempt {attempt + 1}/{max_retries + 1}: {e}. Retrying in {wait_time}s...")
                    
                    if attempt < max_retries:
                        time.sleep(wait_time)
                    else:
                        log_error(f"Max retries exceeded for {func.__name__}")
                        raise last_exception
            
            return None
        return wrapper
    return decorator


def clean_html(text: str) -> str:
    """Remove HTML tags from text."""
    if not text:
        return ""
    
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(text, 'html.parser')
        return soup.get_text(separator=' ', strip=True)
    except ImportError:
        # Fallback: simple regex-based cleaning if BeautifulSoup not available
        import re
        text = re.sub(r'<[^>]+>', '', text)
        return text.strip()


def format_timestamp(timestamp: str) -> str:
    """Format Jira timestamp to readable format."""
    try:
        from datetime import datetime
        dt = datetime.strptime(timestamp.split('.')[0], '%Y-%m-%dT%H:%M:%S')
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return timestamp

