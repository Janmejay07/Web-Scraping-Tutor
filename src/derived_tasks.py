"""
Generate derived LLM tasks (summarization, QnA, classification) from cleaned issues.
"""

import os
import json
from typing import Dict, List, Optional
from pathlib import Path

from utils import logger, load_json, ensure_directory


class DerivedTaskGenerator:
    """Generate derived tasks for LLM training from Jira issues."""
    
    def __init__(
        self,
        processed_data_dir: str = "data/processed",
        output_dir: str = "output"
    ):
        """
        Initialize task generator.
        
        Args:
            processed_data_dir: Directory containing processed JSON files
            output_dir: Directory to save final JSONL dataset
        """
        self.processed_data_dir = processed_data_dir
        self.output_dir = output_dir
        ensure_directory(output_dir)
    
    def classify_issue(self, issue: Dict) -> str:
        """
        Classify issue type based on title and description.
        
        Args:
            issue: Cleaned issue dictionary
            
        Returns:
            Classification label: 'Bug', 'Improvement', 'Task', 'Feature', or 'Other'
        """
        title_lower = (issue.get('title', '') or '').lower()
        desc_lower = (issue.get('description', '') or '').lower()
        combined = f"{title_lower} {desc_lower}"
        
        # Simple keyword-based classification
        bug_keywords = ['bug', 'error', 'exception', 'crash', 'failure', 'broken', 'fix', 'npe', 'nullpointer']
        improvement_keywords = ['improve', 'optimize', 'enhance', 'refactor', 'cleanup', 'performance']
        feature_keywords = ['feature', 'add', 'new', 'implement', 'support']
        
        if any(keyword in combined for keyword in bug_keywords):
            return 'Bug'
        elif any(keyword in combined for keyword in feature_keywords):
            return 'Feature'
        elif any(keyword in combined for keyword in improvement_keywords):
            return 'Improvement'
        else:
            return 'Task'
    
    def generate_summary(self, issue: Dict) -> str:
        """
        Generate a short summary of the issue.
        
        Args:
            issue: Cleaned issue dictionary
            
        Returns:
            Short summary string
        """
        title = issue.get('title', '')
        description = issue.get('description', '')
        status = issue.get('status', '')
        
        # Use title as base, add context from description if short
        if title:
            summary = title
            if description and len(description) < 200:
                summary = f"{title}. {description[:150]}"
        else:
            summary = description[:200] if description else "No description available"
        
        # Add status context if resolved
        if status and 'resolve' in status.lower():
            summary = f"{summary} [Status: {status}]"
        
        return summary.strip()
    
    def generate_qna(self, issue: Dict) -> List[Dict]:
        """
        Generate Q&A pairs from issue.
        
        Args:
            issue: Cleaned issue dictionary
            
        Returns:
            List of Q&A dictionaries
        """
        qna = []
        
        title = issue.get('title', '')
        description = issue.get('description', '')
        status = issue.get('status', '')
        comments = issue.get('comments', [])
        
        # Basic Q&A about the issue
        if title:
            qna.append({
                'question': f'What is the issue in {issue.get("issue_key", "")}?',
                'answer': title
            })
        
        if description:
            qna.append({
                'question': f'What is the description of {issue.get("issue_key", "")}?',
                'answer': description[:500]  # Truncate long descriptions
            })
        
        if status:
            qna.append({
                'question': f'What is the status of {issue.get("issue_key", "")}?',
                'answer': status
            })
        
        # Q&A from comments (especially resolution comments)
        resolution_comments = [c for c in comments if any(word in c.get('body', '').lower() 
                                                          for word in ['fixed', 'resolved', 'merged', 'closed'])]
        
        if resolution_comments:
            latest_resolution = resolution_comments[-1]
            qna.append({
                'question': f'How was {issue.get("issue_key", "")} resolved?',
                'answer': latest_resolution.get('body', '')[:300]
            })
        
        return qna
    
    def add_derived_tasks(self, issue: Dict) -> Dict:
        """
        Add derived tasks to an issue.
        
        Args:
            issue: Cleaned issue dictionary
            
        Returns:
            Issue dictionary with derived_tasks field added
        """
        derived_tasks = {
            'summarization': self.generate_summary(issue),
            'classification': self.classify_issue(issue),
            'qna': self.generate_qna(issue)
        }
        
        issue['derived_tasks'] = derived_tasks
        return issue
    
    def process_project(self, project: str) -> List[Dict]:
        """
        Process all issues for a project and add derived tasks.
        
        Args:
            project: Project key (e.g., 'SPARK')
            
        Returns:
            List of issues with derived tasks
        """
        logger.info(f"Generating derived tasks for {project}")
        
        processed_file = os.path.join(self.processed_data_dir, f"{project}_processed.json")
        
        if not os.path.exists(processed_file):
            logger.warning(f"Processed file not found: {processed_file}")
            return []
        
        issues = load_json(processed_file)
        if not issues:
            logger.warning(f"No issues loaded from {processed_file}")
            return []
        
        issues_with_tasks = []
        
        for issue in issues:
            try:
                issue_with_tasks = self.add_derived_tasks(issue.copy())
                issues_with_tasks.append(issue_with_tasks)
            except Exception as e:
                logger.error(f"Error generating tasks for {issue.get('issue_key', 'unknown')}: {e}")
        
        logger.info(f"Generated tasks for {len(issues_with_tasks)} issues in {project}")
        return issues_with_tasks
    
    def save_jsonl(self, issues: List[Dict], filename: str) -> None:
        """
        Save issues to JSONL file (one JSON object per line).
        
        Args:
            issues: List of issue dictionaries
            filename: Output filename
        """
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            for issue in issues:
                json_line = json.dumps(issue, ensure_ascii=False)
                f.write(json_line + '\n')
        
        logger.info(f"Saved {len(issues)} issues to {filepath}")
    
    def generate_all(self, projects: List[str], output_filename: str = "final_dataset.jsonl") -> int:
        """
        Generate derived tasks for all projects and combine into single JSONL file.
        
        Args:
            projects: List of project keys
            output_filename: Name of output JSONL file
            
        Returns:
            Total number of issues in final dataset
        """
        logger.info("Starting derived task generation...")
        
        all_issues = []
        
        for project in projects:
            try:
                issues = self.process_project(project)
                all_issues.extend(issues)
                logger.info(f"Processed {len(issues)} issues from {project}")
            except Exception as e:
                logger.error(f"Error processing {project}: {e}")
        
        # Save combined dataset
        self.save_jsonl(all_issues, output_filename)
        
        logger.info(f"Generated final dataset with {len(all_issues)} issues")
        return len(all_issues)


def main():
    """Main entry point for derived task generator."""
    projects = ['SPARK', 'KAFKA', 'HADOOP']
    
    generator = DerivedTaskGenerator(
        processed_data_dir="data/processed",
        output_dir="output"
    )
    
    logger.info("Starting derived task generation...")
    total_issues = generator.generate_all(projects)
    
    logger.info(f"Completed! Generated dataset with {total_issues} issues")


if __name__ == "__main__":
    main()


