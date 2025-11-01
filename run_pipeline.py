"""
Main orchestration script to run the entire Jira scraping and transformation pipeline.
"""

import sys
import logging
import argparse
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from utils import logger
from scraper import JiraScraper
from transformer import JiraTransformer
from derived_tasks import DerivedTaskGenerator


def main(max_issues_per_project=None, test_mode=False):
    """
    Run the complete pipeline: Scrape → Transform → Generate Tasks.
    
    Args:
        max_issues_per_project: Maximum number of issues to fetch per project (None = fetch all)
        test_mode: If True, fetch only 100 issues per project for testing
    """
    projects = ['SPARK', 'KAFKA', 'HADOOP']
    
    # Test mode: fetch limited issues
    if test_mode:
        max_issues_per_project = 100
        logger.info("TEST MODE: Fetching only 100 issues per project")
    
    logger.info("=" * 60)
    logger.info("Apache Jira Scraper & LLM Dataset Pipeline")
    logger.info("=" * 60)
    
    # Step 1: Scrape
    logger.info("\n[Step 1/3] Starting data scraping...")
    if max_issues_per_project:
        logger.info(f"LIMITED MODE: Fetching maximum {max_issues_per_project} issues per project")
    else:
        logger.info("FULL MODE: Fetching ALL issues from all projects (this may take hours)")
        logger.info("⚠️  WARNING: This will fetch tens of thousands of issues!")
        logger.info("⚠️  Use --limit N or --test to limit the number of issues")
    
    scraper = JiraScraper(
        projects=projects,
        max_results=50,
        data_dir="data/raw",
        checkpoint_file="checkpoints/state.json",
        max_issues_per_project=max_issues_per_project
    )
    scrape_results = scraper.scrape_all(resume=True)
    logger.info(f"Scraping completed: {scrape_results}")
    
    # Step 2: Transform
    logger.info("\n[Step 2/3] Starting data transformation...")
    transformer = JiraTransformer(
        raw_data_dir="data/raw",
        processed_data_dir="data/processed"
    )
    transform_results = transformer.process_all(projects)
    logger.info(f"Transformation completed: {transform_results}")
    
    # Step 3: Generate Derived Tasks
    logger.info("\n[Step 3/3] Starting derived task generation...")
    generator = DerivedTaskGenerator(
        processed_data_dir="data/processed",
        output_dir="output"
    )
    total_issues = generator.generate_all(projects, output_filename="final_dataset.jsonl")
    
    logger.info("\n" + "=" * 60)
    logger.info("Pipeline completed successfully!")
    logger.info(f"Total issues in final dataset: {total_issues}")
    logger.info(f"Output file: output/final_dataset.jsonl")
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Apache Jira Scraper & LLM Dataset Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_pipeline.py                  # Fetch ALL issues (may take hours/days)
  python run_pipeline.py --test           # Test mode: 100 issues per project
  python run_pipeline.py --limit 500      # Fetch 500 issues per project
  python run_pipeline.py --limit 50 --test # Ignored: --test takes precedence
        """
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Maximum number of issues to fetch per project (default: fetch all)'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Test mode: fetch only 100 issues per project'
    )
    
    args = parser.parse_args()
    
    try:
        main(
            max_issues_per_project=args.limit,
            test_mode=args.test
        )
    except KeyboardInterrupt:
        logger.info("\nPipeline interrupted by user. Progress saved in checkpoints.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Pipeline failed with error: {e}", exc_info=True)
        sys.exit(1)


