"""
Data transformation module for cleaning and converting raw Jira JSON to structured JSONL.
"""

import os
import json
from typing import Any, Dict, List, Optional
from pathlib import Path

from utils import logger, load_json, clean_html, ensure_directory


class JiraTransformer:
    """Transform raw Jira JSON responses to clean structured data."""
    
    def __init__(
        self,
        raw_data_dir: str = "data/raw",
        processed_data_dir: str = "data/processed"
    ):
        """
        Initialize transformer.
        
        Args:
            raw_data_dir: Directory containing raw JSON responses
            processed_data_dir: Directory to save processed JSON files
        """
        self.raw_data_dir = raw_data_dir
        self.processed_data_dir = processed_data_dir
        ensure_directory(processed_data_dir)
    
    def extract_field_value(self, issue: Dict, field_key: str, default: Optional[Any] = None) -> Optional[Any]:
        """
        Extract field value from Jira issue JSON.
        
        Args:
            issue: Raw issue JSON
            field_key: Field key (e.g., 'summary', 'description')
            default: Default value if field not found
            
        Returns:
            Field value or default
        """
        fields = issue.get('fields', {})
        
        # Handle nested field structures
        if field_key in fields:
            field_value = fields[field_key]
            
            # Handle user objects (e.g., assignee, reporter)
            if isinstance(field_value, dict):
                return field_value.get('name') or field_value.get('displayName') or field_value.get('key')
            
            # Handle status/priority objects
            if isinstance(field_value, dict) and 'name' in field_value:
                return field_value['name']
            
            return field_value
        
        return default
    
    def extract_comments(self, issue: Dict) -> List[Dict]:
        """
        Extract comments from issue.
        
        Args:
            issue: Raw issue JSON
            
        Returns:
            List of comment dictionaries with 'author' and 'body'
        """
        comments = []
        comment_field = self.extract_field_value(issue, 'comment')
        
        if comment_field and isinstance(comment_field, dict):
            comment_list = comment_field.get('comments', [])
        elif isinstance(comment_field, list):
            comment_list = comment_field
        else:
            return comments
        
        for comment in comment_list:
            author_info = comment.get('author', {})
            author = author_info.get('name') or author_info.get('displayName') or 'Unknown'
            
            body = comment.get('body', '')
            if body:
                body = clean_html(body)
            
            if body:  # Only include non-empty comments
                comments.append({
                    'author': author,
                    'body': body
                })
        
        return comments
    
    def extract_labels(self, issue: Dict) -> List[str]:
        """Extract labels from issue."""
        labels = self.extract_field_value(issue, 'labels', [])
        if isinstance(labels, list):
            return labels
        return []
    
    def transform_issue(self, issue: Dict) -> Optional[Dict]:
        """
        Transform a single raw issue to clean structured format.
        
        Args:
            issue: Raw issue JSON from Jira API
            
        Returns:
            Cleaned issue dictionary or None if transformation fails
        """
        try:
            issue_key = issue.get('key', '')
            if not issue_key:
                logger.warning("Issue missing key, skipping")
                return None
            
            # Extract basic fields
            summary = self.extract_field_value(issue, 'summary', '')
            description = self.extract_field_value(issue, 'description', '')
            
            # Clean HTML from text fields
            summary = clean_html(summary) if summary else ''
            description = clean_html(description) if description else ''
            
            # Extract metadata
            status_obj = self.extract_field_value(issue, 'status')
            status = status_obj.get('name') if isinstance(status_obj, dict) else str(status_obj) if status_obj else 'Unknown'
            
            priority_obj = self.extract_field_value(issue, 'priority')
            priority = priority_obj.get('name') if isinstance(priority_obj, dict) else str(priority_obj) if priority_obj else 'Unknown'
            
            reporter = self.extract_field_value(issue, 'reporter', 'Unknown')
            assignee = self.extract_field_value(issue, 'assignee', 'Unassigned')
            created = self.extract_field_value(issue, 'created', '')
            updated = self.extract_field_value(issue, 'updated', '')
            
            # Extract project from issue key (e.g., SPARK-1234 -> SPARK)
            project = issue_key.split('-')[0] if '-' in issue_key else 'Unknown'
            
            # Extract comments and labels
            comments = self.extract_comments(issue)
            labels = self.extract_labels(issue)
            
            # Build cleaned issue
            cleaned_issue = {
                'issue_key': issue_key,
                'project': project,
                'title': summary,
                'description': description,
                'status': status,
                'priority': priority,
                'reporter': reporter or 'Unknown',
                'assignee': assignee or 'Unassigned',
                'created': created,
                'updated': updated,
                'labels': labels,
                'comments': comments
            }
            
            return cleaned_issue
            
        except Exception as e:
            logger.error(f"Error transforming issue {issue.get('key', 'unknown')}: {e}")
            return None
    
    def transform_page(self, raw_data: Dict) -> List[Dict]:
        """
        Transform a page of issues (raw API response).
        
        Args:
            raw_data: Raw JSON response from Jira API
            
        Returns:
            List of cleaned issue dictionaries
        """
        issues = raw_data.get('issues', [])
        cleaned_issues = []
        
        for issue in issues:
            cleaned = self.transform_issue(issue)
            if cleaned:
                cleaned_issues.append(cleaned)
        
        logger.info(f"Transformed {len(cleaned_issues)}/{len(issues)} issues")
        return cleaned_issues
    
    def process_project(self, project: str) -> int:
        """
        Process all raw files for a project.
        
        Args:
            project: Project key (e.g., 'SPARK')
            
        Returns:
            Number of issues processed
        """
        logger.info(f"Processing project: {project}")
        
        # Find all raw files for this project
        raw_files = sorted(Path(self.raw_data_dir).glob(f"{project}_page_*.json"))
        
        if not raw_files:
            logger.warning(f"No raw files found for {project}")
            return 0
        
        all_issues = []
        
        for raw_file in raw_files:
            logger.info(f"Processing {raw_file.name}")
            raw_data = load_json(str(raw_file))
            
            if not raw_data:
                logger.warning(f"Failed to load {raw_file.name}")
                continue
            
            cleaned_issues = self.transform_page(raw_data)
            all_issues.extend(cleaned_issues)
        
        # Save processed data as JSON
        output_file = os.path.join(self.processed_data_dir, f"{project}_processed.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_issues, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Processed {len(all_issues)} issues for {project}")
        return len(all_issues)
    
    def process_all(self, projects: List[str]) -> Dict[str, int]:
        """
        Process all projects.
        
        Args:
            projects: List of project keys
            
        Returns:
            Dictionary mapping project to number of issues processed
        """
        results = {}
        
        for project in projects:
            try:
                count = self.process_project(project)
                results[project] = count
            except Exception as e:
                logger.error(f"Error processing {project}: {e}")
                results[project] = 0
        
        return results


def main():
    """Main entry point for transformer."""
    projects = ['SPARK', 'KAFKA', 'HADOOP']
    
    transformer = JiraTransformer(
        raw_data_dir="data/raw",
        processed_data_dir="data/processed"
    )
    
    logger.info("Starting data transformation...")
    results = transformer.process_all(projects)
    
    logger.info("Transformation completed!")
    logger.info(f"Results: {results}")


if __name__ == "__main__":
    main()

