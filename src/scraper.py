"""
Jira API scraper for fetching issues from Apache Jira projects.
Handles pagination, rate limits, checkpoints, and error recovery.
"""

import os
import time
import requests
from typing import Dict, List, Optional

from utils import (
    log_info, log_warning, log_error, log_debug,
    save_json, load_json, ensure_directory,
    save_checkpoint, load_checkpoint, retry_with_backoff
)


class JiraScraper:
    """Scraper for Apache Jira REST API."""
    
    BASE_URL = "https://issues.apache.org/jira/rest/api/2"
    
    def __init__(
        self,
        projects: List[str],
        max_results: int = 50,
        data_dir: str = "data/raw",
        checkpoint_file: str = "checkpoints/state.json",
        max_issues_per_project: Optional[int] = None
    ):
        """
        Initialize Jira scraper.
        
        Args:
            projects: List of project keys (e.g., ['SPARK', 'KAFKA', 'HADOOP'])
            max_results: Number of results per API call (max 100)
            data_dir: Directory to save raw JSON responses
            checkpoint_file: Path to checkpoint file
            max_issues_per_project: Maximum number of issues to fetch per project (None = fetch all)
        """
        self.projects = projects
        self.max_results = min(max_results, 100)  # Jira API limit
        self.data_dir = data_dir
        self.checkpoint_file = checkpoint_file
        self.max_issues_per_project = max_issues_per_project
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'Apache-Jira-Scraper/1.0'
        })
        
        ensure_directory(self.data_dir)
        ensure_directory(os.path.dirname(self.checkpoint_file))
    
    @retry_with_backoff(max_retries=3, initial_delay=2.0)
    def _make_request(self, url: str, params: Optional[Dict] = None) -> Dict:
        """
        Make HTTP request to Jira API with retry logic.
        Handles connection errors, timeouts, HTTP errors, and malformed JSON.
        
        Raises:
            Exception: For HTTP error responses, connection errors, timeouts, or malformed JSON
        """
        # Create custom exception class with status_code attribute
        class HTTPErrorWithCode(Exception):
            def __init__(self, status_code, message):
                super().__init__(message)
                self.status_code = status_code
        
        try:
            # Make request with timeout (30 seconds for connect, 30 seconds for read)
            response = self.session.get(url, params=params, timeout=(30, 30))
        except requests.exceptions.Timeout as e:
            # Handle timeout errors
            log_error(f"Request timeout for {url}: {e}")
            # Wrap timeout as a retryable error (status_code 0 indicates timeout)
            timeout_error = HTTPErrorWithCode(0, f"Request timeout: {str(e)}")
            raise timeout_error
        except requests.exceptions.ConnectionError as e:
            # Handle connection errors (network issues, DNS failures, etc.)
            log_error(f"Connection error for {url}: {e}")
            # Wrap connection error as retryable (status_code 0 indicates connection error)
            conn_error = HTTPErrorWithCode(0, f"Connection error: {str(e)}")
            raise conn_error
        except requests.exceptions.RequestException as e:
            # Handle other request-related errors
            log_error(f"Request error for {url}: {e}")
            req_error = HTTPErrorWithCode(0, f"Request error: {str(e)}")
            raise req_error
        
        # Check HTTP status code
        if response.status_code >= 400:
            raise HTTPErrorWithCode(response.status_code, f"HTTP {response.status_code}: {response.reason}")
        
        # Validate response is not empty
        if not response.content:
            log_warning(f"Empty response received from {url}")
            empty_error = HTTPErrorWithCode(response.status_code, "Empty response received")
            raise empty_error
        
        # Parse JSON and handle malformed JSON errors
        try:
            data = response.json()
        except ValueError as e:
            # JSONDecodeError inherits from ValueError
            log_error(f"Malformed JSON in response from {url}: {e}")
            log_debug(f"Response content (first 500 chars): {response.text[:500]}")
            json_error = HTTPErrorWithCode(response.status_code, f"Malformed JSON: {str(e)}")
            raise json_error
        
        # Validate response structure (should have 'issues' or 'total' key for search API)
        if not isinstance(data, dict):
            log_warning(f"Unexpected response type from {url}: expected dict, got {type(data)}")
            type_error = HTTPErrorWithCode(response.status_code, f"Unexpected response type: {type(data)}")
            raise type_error
        
        return data
    
    def fetch_issues_page(
        self,
        project: str,
        start_at: int = 0
    ) -> Optional[Dict]:
        """
        Fetch a single page of issues for a project.
        
        Args:
            project: Project key (e.g., 'SPARK')
            start_at: Starting index for pagination
            
        Returns:
            JSON response from Jira API or None on failure
        """
        url = f"{self.BASE_URL}/search"
        params = {
            'jql': f'project={project}',
            'startAt': start_at,
            'maxResults': self.max_results,
            'expand': 'renderedFields,names,schema',  # Get full issue details
            'fields': 'key,summary,description,status,priority,assignee,reporter,created,updated,labels,comment'
        }
        
        try:
            log_info(f"Fetching {project} issues: startAt={start_at}, maxResults={self.max_results}")
            data = self._make_request(url, params)
            
            # Validate response has expected structure
            if 'issues' not in data:
                log_warning(f"Response missing 'issues' field for {project} at startAt={start_at}")
                # Check if it's an empty result (sometimes API returns different structure)
                if 'total' in data and data.get('total') == 0:
                    log_info(f"No issues found for {project} at startAt={start_at}")
                    return data
                else:
                    log_error(f"Unexpected response structure for {project}: {list(data.keys())}")
                    return None
            
            total = data.get('total', 0)
            issues = data.get('issues', [])
            
            # Validate issues is a list
            if not isinstance(issues, list):
                log_error(f"Expected 'issues' to be a list, got {type(issues)}")
                return None
            
            log_info(f"Fetched {len(issues)} issues for {project} (total: {total})")
            
            return data
        except Exception as e:
            log_error(f"Error fetching {project} page {start_at}: {e}")
            return None
    
    def save_raw_response(self, project: str, page: int, data: Dict) -> None:
        """Save raw API response to disk."""
        filename = os.path.join(self.data_dir, f"{project}_page_{page}.json")
        save_json(data, filename)
        log_debug(f"Saved raw response to {filename}")
    
    def scrape_project(self, project: str, resume: bool = True) -> int:
        """
        Scrape all issues for a project.
        
        Args:
            project: Project key
            resume: Whether to resume from checkpoint
            
        Returns:
            Number of pages scraped
        """
        log_info(f"Starting scrape for project: {project}")
        
        # Load checkpoint if resuming
        start_page = 0
        if resume:
            start_page = load_checkpoint(project, self.checkpoint_file)
        
        # Fetch first page to get total count
        first_page_data = self.fetch_issues_page(project, start_at=start_page * self.max_results)
        if not first_page_data:
            log_error(f"Failed to fetch initial page for {project}")
            return 0
        
        total_issues = first_page_data.get('total', 0)
        
        # Apply limit if specified
        if self.max_issues_per_project and total_issues > self.max_issues_per_project:
            total_issues = self.max_issues_per_project
            log_info(f"{project}: Limiting to {total_issues} issues (total available: {first_page_data.get('total', 0)})")
        
        total_pages = (total_issues + self.max_results - 1) // self.max_results
        log_info(f"{project}: Fetching {total_issues} issues, {total_pages} pages")
        
        # Save first page
        self.save_raw_response(project, start_page, first_page_data)
        save_checkpoint(project, start_page, self.checkpoint_file)
        
        pages_scraped = 1
        
        # Fetch remaining pages
        for page in range(start_page + 1, total_pages):
            start_at = page * self.max_results
            
            page_data = self.fetch_issues_page(project, start_at=start_at)
            if page_data:
                self.save_raw_response(project, page, page_data)
                save_checkpoint(project, page, self.checkpoint_file)
                pages_scraped += 1
                
                # Small delay to be respectful to API
                time.sleep(0.5)
            else:
                log_error(f"Failed to fetch page {page} for {project}, stopping")
                break
        
        log_info(f"Completed scraping {project}: {pages_scraped} pages")
        return pages_scraped
    
    def scrape_all(self, resume: bool = True) -> Dict[str, int]:
        """
        Scrape all configured projects.
        
        Args:
            resume: Whether to resume from checkpoints
            
        Returns:
            Dictionary mapping project to pages scraped
        """
        results = {}
        
        for project in self.projects:
            try:
                pages = self.scrape_project(project, resume=resume)
                results[project] = pages
                
                # Delay between projects to be respectful
                time.sleep(1)
            except KeyboardInterrupt:
                log_info("Scraping interrupted by user")
                break
            except Exception as e:
                log_error(f"Error scraping {project}: {e}")
                results[project] = 0
        
        return results


def main():
    """Main entry point for scraper."""
    projects = ['SPARK', 'KAFKA', 'HADOOP']
    
    scraper = JiraScraper(
        projects=projects,
        max_results=50,
        data_dir="data/raw",
        checkpoint_file="checkpoints/state.json"
    )
    
    log_info("Starting Jira scraper...")
    results = scraper.scrape_all(resume=True)
    
    log_info("Scraping completed!")
    log_info(f"Results: {results}")


if __name__ == "__main__":
    main()

