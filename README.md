# Apache Jira Scraper & LLM Dataset Pipeline

A robust, production-ready data scraping and transformation system that fetches public issue data from Apache Jira projects and converts it into a clean JSONL dataset suitable for LLM training.

## 📋 Overview

This project creates LLM-ready datasets by:
- Scraping public Jira issues from Apache projects (SPARK, KAFKA, HADOOP)
- Handling pagination, rate limits, and network failures gracefully
- Cleaning and transforming raw JSON data into structured format
- Generating derived tasks (summarization, QnA, classification) for instruction-tuning
- Outputting everything in JSONL format for easy consumption

**Purpose**: Extract, clean, and enrich Jira issue data to create high-quality training corpora for Large Language Models.

## 🏗️ Architecture

The system follows a modular, three-layer pipeline design:

```
┌─────────────────────────────────────────────────────────────┐
│                    Data Scraping Layer                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │  SPARK   │  │  KAFKA   │  │  HADOOP  │                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
│       ↓              ↓              ↓                        │
│  ┌─────────────────────────────────────┐                    │
│  │  Jira API (REST) + Pagination       │                    │
│  │  • Rate limit handling              │                    │
│  │  • Checkpointing & resume           │                    │
│  │  • Exponential backoff retries       │                    │
│  └─────────────────────────────────────┘                    │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ↓ (Raw JSON)
┌─────────────────────────────────────────────────────────────┐
│                 Data Transformation Layer                    │
│  ┌─────────────────────────────────────┐                    │
│  │  Clean & Structure                  │                    │
│  │  • Remove HTML/Markdown             │                    │
│  │  • Extract fields (title, desc,     │                    │
│  │    comments, metadata)              │                    │
│  │  • Normalize data structures        │                    │
│  └─────────────────────────────────────┘                    │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ↓ (Structured JSON)
┌─────────────────────────────────────────────────────────────┐
│              Derived Task Generation Layer                   │
│  ┌─────────────────────────────────────┐                    │
│  │  LLM Task Generation                │                    │
│  │  • Summarization                    │                    │
│  │  • Classification (Bug/Feature/etc) │                    │
│  │  • Q&A pair generation              │                    │
│  └─────────────────────────────────────┘                    │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ↓
              ┌─────────────────────┐
              │  final_dataset.jsonl │
              │  (LLM-ready corpus)  │
              └─────────────────────┘
```

### Component Breakdown

1. **Scraper** (`src/scraper.py`)
   - Handles API calls to Apache Jira REST API
   - Manages pagination with configurable batch sizes
   - Implements retry logic with exponential backoff
   - Supports checkpointing to resume after interruptions

2. **Transformer** (`src/transformer.py`)
   - Parses raw nested JSON responses
   - Extracts and cleans text fields (removes HTML/Markdown)
   - Normalizes data structures
   - Outputs clean structured JSON

3. **Derived Tasks Generator** (`src/derived_tasks.py`)
   - Generates summarization tasks
   - Classifies issues (Bug, Feature, Improvement, Task)
   - Creates Q&A pairs from issue data
   - Outputs final JSONL dataset

4. **Utilities** (`src/utils.py`)
   - Retry decorators with exponential backoff
   - Logging configuration
   - File I/O helpers
   - Checkpoint management
   - HTML cleaning utilities

## 🚀 Setup & Installation

### Prerequisites

- Python 3.9 or higher
- pip (Python package manager)

### Installation

1. **Clone or navigate to the project directory:**
   ```bash
   cd apache-jira-scraper
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

   This installs:
   - `requests` - HTTP client for API calls
   - `beautifulsoup4` - HTML parsing and cleaning
   - `lxml` - XML/HTML parser backend
   - `tqdm` - Progress bars (optional, for future enhancements)

3. **Verify installation:**
   ```bash
   python -c "import requests, bs4; print('Dependencies installed successfully!')"
   ```

## 📖 Usage

### Running the Complete Pipeline

The easiest way to run the entire pipeline (scrape → transform → generate tasks):

#### ⚠️ IMPORTANT: Default Behavior

**By default, `python run_pipeline.py` will fetch ALL issues from all 3 projects!**

For SPARK alone, this means **53,718+ issues**. For all 3 projects, this could be **100,000+ issues**, which may take **hours or even days** to complete!

#### Recommended: Use Limits for Testing

```bash
# Test mode: Fetch only 100 issues per project (recommended for testing)
python run_pipeline.py --test

# Custom limit: Fetch 500 issues per project
python run_pipeline.py --limit 500

# Fetch ALL issues (use with caution!)
python run_pipeline.py
```

#### Command Options:

- `--test` : Fetch only **100 issues per project** (300 total)
- `--limit N` : Fetch maximum **N issues per project** (e.g., `--limit 500` = 500 per project)
- No arguments : Fetch **ALL issues** (may take hours/days!)

#### What the Pipeline Does:

1. Scrape issues from SPARK, KAFKA, and HADOOP projects
2. Transform raw data to clean JSON
3. Generate derived tasks and create final JSONL dataset

### Running Individual Components

You can also run each component separately:

#### 1. Scraping Data

```bash
python src/scraper.py
```

This fetches all issues from the configured projects and saves raw JSON responses to `data/raw/`.

**Features:**
- Automatic pagination (fetches all issues)
- Checkpoint saving after each page
- Resume capability (restarts from last checkpoint if interrupted)
- Rate limit handling (waits 60s on 429 errors)
- Retry logic for transient failures

#### 2. Transforming Data

```bash
python src/transformer.py
```

This processes raw JSON files and outputs cleaned structured data to `data/processed/`.

**Features:**
- Extracts all relevant fields (title, description, comments, metadata)
- Removes HTML tags and Markdown formatting
- Handles nested JSON structures
- Skips malformed or missing data gracefully

#### 3. Generating Derived Tasks

```bash
python src/derived_tasks.py
```

This adds LLM training tasks (summarization, classification, Q&A) and creates the final JSONL dataset in `output/final_dataset.jsonl`.

**Features:**
- Automatic issue classification
- Smart summarization generation
- Q&A pair extraction from issues and comments
- JSONL output (one JSON object per line)

## 📁 Project Structure

```
apache-jira-scraper/
│
├── src/
│   ├── __init__.py          # Package initialization
│   ├── scraper.py           # Jira API scraper with pagination & retries
│   ├── transformer.py       # Data cleaning and transformation
│   ├── derived_tasks.py     # LLM task generation (summarization, QnA)
│   └── utils.py             # Utilities (retry, logging, file I/O)
│
├── data/
│   ├── raw/                 # Raw JSON responses from Jira API
│   │   ├── SPARK_page_0.json
│   │   ├── SPARK_page_1.json
│   │   └── ...
│   └── processed/           # Clean structured JSON
│       ├── SPARK_processed.json
│       ├── KAFKA_processed.json
│       └── HADOOP_processed.json
│
├── checkpoints/
│   └── state.json           # Progress checkpoint (page numbers per project)
│
├── logs/
│   └── scraper_*.log        # Execution logs with timestamps
│
├── output/
│   └── final_dataset.jsonl  # Final LLM-ready corpus (JSONL format)
│
├── run_pipeline.py          # Main orchestration script
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

## 🔧 Configuration

### Changing Projects

To scrape different Apache Jira projects, edit the `projects` list in:

- `run_pipeline.py` (line ~12)
- `src/scraper.py` (line ~170)
- `src/transformer.py` (line ~221)
- `src/derived_tasks.py` (line ~188)

Example:
```python
projects = ['SPARK', 'KAFKA', 'HADOOP', 'FLINK']  # Add more projects
```

### Adjusting Batch Size

In `src/scraper.py`, modify the `max_results` parameter:

```python
scraper = JiraScraper(
    projects=projects,
    max_results=100,  # Jira API allows up to 100
    ...
)
```

### Retry Configuration

Adjust retry behavior in `src/scraper.py`:

```python
@retry_with_backoff(
    max_retries=5,        # Number of retry attempts
    initial_delay=2.0,    # Initial delay (seconds)
    exponential_base=2.0, # Backoff multiplier
    max_delay=120.0       # Maximum wait time (seconds)
)
```

## 🛡️ Edge Cases & Fault Tolerance

The system handles various edge cases and failures gracefully:

### 1. HTTP 429 (Rate Limiting)
- **Detection**: Automatic detection of 429 status code
- **Response**: Waits 60 seconds before retrying
- **Recovery**: Continues from checkpoint after rate limit clears

### 2. HTTP 5xx (Server Errors)
- **Detection**: Catches 500, 502, 503, 504 status codes
- **Response**: Exponential backoff (2s, 4s, 8s, ...)
- **Recovery**: Retries up to 3 times before failing

### 3. Network Failures
- **Detection**: Connection timeouts and network errors
- **Response**: Retries with exponential backoff
- **Recovery**: Resumes from last checkpoint after network recovers

### 4. Power Loss / Interruption
- **Detection**: KeyboardInterrupt or unexpected termination
- **Response**: Checkpoint saved after each successful page fetch
- **Recovery**: Automatically resumes from `checkpoints/state.json` on restart

### 5. Empty or Malformed JSON
- **Detection**: JSON parsing errors and empty responses
- **Response**: Skips problematic issues, logs warnings
- **Recovery**: Continues processing remaining data

### 6. Missing Fields
- **Detection**: Missing optional fields in issue data
- **Response**: Uses default values (e.g., "Unknown", "Unassigned")
- **Recovery**: All issues processed, missing fields don't block pipeline

## 📊 Output Format

### Final JSONL Dataset

Each line in `output/final_dataset.jsonl` is a valid JSON object:

```json
{
  "issue_key": "SPARK-1234",
  "project": "SPARK",
  "title": "Fix NPE in DataFrame API",
  "description": "Null pointer exception occurs when using collect()...",
  "status": "Resolved",
  "priority": "Major",
  "reporter": "john_doe",
  "assignee": "jane_dev",
  "created": "2024-03-01T12:34:56.000+0000",
  "updated": "2024-03-05T09:12:00.000+0000",
  "labels": ["bug", "api"],
  "comments": [
    {"author": "Alice", "body": "Needs test case."},
    {"author": "Bob", "body": "Merged successfully."}
  ],
  "derived_tasks": {
    "summarization": "Fixes a null pointer exception in DataFrame collect().",
    "classification": "Bug",
    "qna": [
      {
        "question": "What is the issue in SPARK-1234?",
        "answer": "Fix NPE in DataFrame API"
      },
      {
        "question": "How was SPARK-1234 resolved?",
        "answer": "Merged successfully."
      }
    ]
  }
}
```

### JSONL Format Benefits

- **Streaming-friendly**: Process one line at a time
- **Memory-efficient**: No need to load entire dataset
- **LLM-ready**: Standard format for training datasets
- **Tool compatibility**: Works with Hugging Face datasets, PyTorch DataLoader, etc.

## 🔍 Monitoring & Logging

### Log Files

All execution logs are saved to `logs/scraper_<timestamp>.log`:

```
2024-11-01 19:43:12 - INFO - Starting Jira scraper...
2024-11-01 19:43:13 - INFO - Fetching SPARK issues: startAt=0, maxResults=50
2024-11-01 19:43:15 - INFO - Fetched 50 issues for SPARK (total: 12500)
2024-11-01 19:43:15 - INFO - Checkpoint saved: SPARK at page 0
```

### Checkpoint File

Progress is saved in `checkpoints/state.json`:

```json
{
  "SPARK": {
    "last_fetched_page": 12,
    "last_updated": 1698860595.123
  },
  "KAFKA": {
    "last_fetched_page": 5,
    "last_updated": 1698860610.456
  },
  "HADOOP": {
    "last_fetched_page": 8,
    "last_updated": 1698860625.789
  }
}
```

## ⚡ Optimization Features

### Batch Fetching
- Fetches up to 50-100 issues per API call (configurable)
- Minimizes number of HTTP requests
- Reduces API rate limit pressure

### Checkpointing
- Saves progress after each page
- Enables resume without re-fetching
- Reduces redundant API calls

### Caching
- Raw responses saved to disk (`data/raw/`)
- Processed data cached (`data/processed/`)
- Skip already-fetched pages on resume

### Rate Limit Respect
- Automatic delays between requests (0.5s default)
- 60-second wait on 429 errors
- Configurable request throttling

## 🚀 Future Improvements

### Planned Enhancements

1. **Async Fetching**
   - Implement `aiohttp` for concurrent requests
   - Parallelize fetching across projects
   - Reduce total scraping time

2. **Cloud Storage Integration**
   - Save raw data to AWS S3 / Google Cloud Storage
   - Enable distributed processing
   - Reduce local storage requirements

3. **Advanced Task Generation**
   - Use LLM APIs for better summarization
   - Generate more sophisticated Q&A pairs
   - Extract code snippets and technical details

4. **Data Quality Metrics**
   - Compute statistics (avg description length, comment count)
   - Filter low-quality issues
   - Generate data quality reports

5. **Fine-tuning Examples**
   - Create example fine-tuning scripts
   - Demonstrate dataset usage with Hugging Face
   - Include evaluation metrics

### Contributing

To extend the system:

1. **Add new projects**: Modify `projects` list in configuration
2. **Custom transformers**: Extend `JiraTransformer` class
3. **New task types**: Add methods to `DerivedTaskGenerator`
4. **Export formats**: Implement additional output formats (Parquet, CSV, etc.)

## 📚 API Reference

### Jira REST API Endpoints Used

| Endpoint | Description |
|----------|-------------|
| `/rest/api/2/search` | Search issues by project (JQL) |
| `/rest/api/2/issue/{key}` | Fetch detailed issue info (for future use) |
| `/rest/api/2/serverInfo` | Get API version info (for validation) |

**Example API Calls:**

```bash
# Search SPARK issues
curl "https://issues.apache.org/jira/rest/api/2/search?jql=project=SPARK&startAt=0&maxResults=50"

# Get specific issue
curl "https://issues.apache.org/jira/rest/api/2/issue/SPARK-1234"
```

### Key Query Parameters

- `jql`: Jira Query Language (e.g., `project=SPARK`)
- `startAt`: Pagination offset
- `maxResults`: Number of results per page (max 100)
- `expand`: Additional fields to include
- `fields`: Specific fields to retrieve

## 🐛 Troubleshooting

### Common Issues

**Issue**: `ModuleNotFoundError: No module named 'utils'`
- **Solution**: Run scripts from project root, or use `run_pipeline.py`

**Issue**: `HTTP 429: Too Many Requests`
- **Solution**: System automatically waits 60s. If persistent, reduce `max_results` or add longer delays.

**Issue**: `JSONDecodeError` when loading checkpoint
- **Solution**: Delete `checkpoints/state.json` and restart (will resume from beginning)

**Issue**: Empty output files
- **Solution**: Check `logs/` for errors. Verify API is accessible and projects exist.

**Issue**: Missing comments or fields
- **Solution**: Some issues may have missing fields. System handles this gracefully with defaults.

## 📄 License

This project is provided as-is for educational and research purposes. Please respect Apache Jira's terms of service and rate limits when scraping.

## 🙏 Acknowledgments

- Apache Software Foundation for providing public Jira API access
- Beautiful Soup for HTML parsing
- Requests library for HTTP handling

---

**Built with ❤️ for LLM dataset creation**

