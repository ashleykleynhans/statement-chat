# Bank Statement Chat Bot

A CLI application that parses PDF bank statements, imports them into SQLite, auto-classifies transactions using a local LLM (Ollama), and provides a chat interface to query your transaction history.

## Features

- **PDF Parsing**: Extract transactions from bank statement PDFs
- **Auto-Classification**: Uses Ollama to categorize transactions (doctor, groceries, utilities, etc.)
- **Chat Interface**: Ask natural language questions about your spending
- **File Watcher**: Automatically imports new statements when added
- **Extensible**: Easy to add support for new banks

## Requirements

- Python 3.10+
- [Ollama](https://ollama.ai/) running locally

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd statement-chat

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .
```

## Setup

1. **Start Ollama** and pull a model:
   ```bash
   ollama serve
   ollama pull llama3.2
   ```

2. **Configure** (optional - edit `config.yaml`):
   ```yaml
   bank: fnb                    # Bank parser to use
   ollama:
     model: llama3.2           # Ollama model for classification
   ```

3. **Add statements**: Place PDF bank statements in the `statements/` directory

## Usage

```bash
# Activate virtual environment
source .venv/bin/activate

# Import all PDF statements
python -m src.main import

# Watch for new statements (auto-import)
python -m src.main watch

# Start interactive chat
python -m src.main chat

# List recent transactions
python -m src.main list
python -m src.main list -n 50    # Show 50 transactions

# Search transactions
python -m src.main search "doctor"
python -m src.main search "woolworths"

# View spending by category
python -m src.main categories

# Database statistics
python -m src.main stats

# List available bank parsers
python -m src.main parsers
```

## Re-importing Statements

If you update classification rules in `config.yaml`, you'll need to clear the database and re-import to apply the new rules:

```bash
# Delete the database and re-import all statements
rm ./data/statements.db && python -m src.main import
```

## Chat Examples

Once you've imported statements, start a chat session:

```
$ python -m src.main chat

You: When did I last pay the doctor?
Assistant: Your last payment to a doctor was on 2024-01-15 for R850.00...

You: How much did I spend on groceries last month?
Assistant: Last month you spent R4,523.50 on groceries across 12 transactions...

You: Show my largest expenses
Assistant: Your largest expenses were...
```

## Adding Support for New Banks

1. Create a new file in `src/parsers/` (e.g., `standardbank.py`)
2. Implement a parser class that inherits from `BaseBankParser`:

```python
from . import register_parser
from .base import BaseBankParser, StatementData

@register_parser
class StandardBankParser(BaseBankParser):
    @classmethod
    def bank_name(cls) -> str:
        return "standardbank"

    def parse(self, pdf_path) -> StatementData:
        # Implement PDF parsing logic
        ...
```

3. Update `config.yaml`:
   ```yaml
   bank: standardbank
   ```

## Configuration

Edit `config.yaml` to customize:

```yaml
# Bank parser to use
bank: fnb

# Ollama settings
ollama:
  host: localhost
  port: 11434
  model: llama3.2

# File paths
paths:
  statements_dir: ./statements
  database: ./data/statements.db

# Transaction categories (customize as needed)
categories:
  - doctor
  - optician
  - groceries
  - garden_service
  - dog_parlour
  - domestic_worker
  - education
  - fuel
  - utilities
  - insurance
  - entertainment
  - transfer
  - salary
  - other
```

## Project Structure

```
statement-chat/
├── statements/           # Place PDF files here
├── data/
│   └── statements.db    # SQLite database
├── src/
│   ├── main.py          # CLI entry point
│   ├── database.py      # Database operations
│   ├── classifier.py    # Ollama classifier
│   ├── chat.py          # Chat interface
│   ├── watcher.py       # File watcher
│   ├── config.py        # Config loader
│   └── parsers/
│       ├── base.py      # Base parser class
│       ├── fnb.py       # FNB parser
│       └── __init__.py  # Parser registry
├── config.yaml
├── requirements.txt
└── pyproject.toml
```

## Privacy Note

Your bank statements contain sensitive financial data. This application:
- Processes everything locally (no cloud services)
- Uses a local LLM via Ollama
- Stores data in a local SQLite database

The `statements/` and `data/` directories are gitignored by default.

## License

GPLv3

