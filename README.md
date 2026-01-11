# BankBot

A local-first application that parses South African bank statement PDFs, auto-classifies
transactions using a local LLM (Ollama), and lets you explore your spending through a
modern web UI or CLI chat interface. All data stays on your machine.

## Supported Banks

- [FNB](https://www.fnb.co.za/) (First National Bank)

Want to add support for another bank? See [Adding Support for New Banks](
#adding-support-for-new-banks).

> [!WARNING]
> This application processes sensitive financial data. **Run locally only** - do
> not deploy to cloud services or expose to the internet. Your bank statements
> contain personal information that should never leave your machine.

## Features

- **PDF Parsing**: Extract transactions from bank statement PDFs
- **Auto-Classification**: Uses Ollama to categorize transactions (doctor, groceries, utilities, etc.)
- **Chat Interface**: Ask natural language questions about your spending
- **REST + WebSocket API**: Integrate with frontend applications
- **Web Frontend**: Svelte-based dashboard with chat, transactions, and analytics
- **Analytics**: Pie charts showing spending breakdown per statement
- **Budget Tracking**: Set monthly budgets per category and track actual vs budgeted spending
- **File Watcher**: Automatically imports new statements when added
- **Extensible**: Easy to add support for new banks

## Tech Stack

- **Backend**: Python 3.11+ (FastAPI, SQLite)
- **Frontend**: Svelte 5, Tailwind CSS
- **AI**: [Ollama](https://ollama.ai/) (local LLM)

## Requirements

- Python 3.11+
- Node.js 18+
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

# Install with test dependencies (pytest, coverage)
pip install -e ".[test]"
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

# Rename PDFs to standardized format: {number}_{month}_{year}.pdf
# This ensures statements are imported in chronological order
python -m src.main rename

# Re-import a specific statement (useful after updating classification rules)
python -m src.main reimport statements/288_Nov_2025.pdf

# Re-import all statements
python -m src.main reimport all

# Export budgets to JSON or YAML
python -m src.main export-budget budgets.json
python -m src.main export-budget budgets.yaml

# Import budgets from file (clears existing budgets first)
python -m src.main import-budget budgets.json

# Start API server (REST + WebSocket)
python -m src.main serve
python -m src.main serve --host 0.0.0.0 --port 3000
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

# Classification rules (override LLM for specific patterns)
classification_rules:
  "Woolworths": groceries
  "Shell": fuel
  "Engen": fuel
  "School Fees": education
```

## API

Start the API server with `python -m src.main serve`. Interactive docs available at `http://localhost:8000/docs`.

### REST Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/v1/stats` | Database statistics |
| GET | `/api/v1/categories` | List all categories |
| GET | `/api/v1/categories/summary` | Spending by category |
| GET | `/api/v1/transactions` | Paginated list (`?limit=20&offset=0`) |
| GET | `/api/v1/transactions/search?q=term` | Search transactions |
| GET | `/api/v1/transactions/category/{cat}` | Filter by category |
| GET | `/api/v1/transactions/type/{type}` | Filter by debit/credit |
| GET | `/api/v1/transactions/date-range?start=&end=` | Date range filter |
| GET | `/api/v1/statements` | List all statements |
| GET | `/api/v1/analytics/latest` | Analytics for latest statement |
| GET | `/api/v1/analytics/statement/{num}` | Analytics for specific statement |
| GET | `/api/v1/budgets` | List all budgets |
| POST | `/api/v1/budgets` | Create/update budget |
| DELETE | `/api/v1/budgets/{category}` | Delete a budget |
| GET | `/api/v1/budgets/summary` | Budget vs actual comparison |

### WebSocket Chat

Connect to `ws://localhost:8000/ws/chat` for real-time chat.

**Send:**
```json
{"type": "chat", "payload": {"message": "How much did I spend on groceries?"}}
```

**Receive:**
```json
{
  "type": "chat_response",
  "payload": {
    "message": "You spent R2,450 on groceries...",
    "transactions": [...],
    "timestamp": "2025-01-07T10:30:00"
  }
}
```

Each WebSocket connection maintains its own conversation history for follow-up questions.

## Web Frontend

A Svelte-based web interface is included in the `frontend/` directory.

### Frontend Setup

```bash
# Install frontend dependencies
cd frontend
npm install

# Start development server (runs on port 5173)
npm run dev
```

### Running Full Stack

You need two terminals:

```bash
# Terminal 1: Start the backend API
source .venv/bin/activate
python -m src.main serve

# Terminal 2: Start the frontend
cd frontend
npm run dev
```

Then open http://localhost:5173 in your browser.

### Frontend Features

- **Chat**: Real-time WebSocket chat with transaction context
- **Dashboard**: Stats overview and spending by category chart
- **Analytics**: Pie charts showing spending breakdown per statement with statement selector
- **Budget**: Set budgets per category, track spending with progress bars (color-coded: green/yellow/red)
- **Transactions**: Searchable, filterable transaction list with pagination

### Building for Production

```bash
cd frontend
npm run build
```

The built files will be in `frontend/dist/`.

## Project Structure

```
statement-chat/
├── statements/           # Place PDF files here
├── data/
│   └── statements.db    # SQLite database (includes budgets table)
├── src/
│   ├── main.py          # CLI entry point
│   ├── database.py      # Database operations
│   ├── classifier.py    # Ollama classifier
│   ├── chat.py          # Chat interface
│   ├── watcher.py       # File watcher
│   ├── config.py        # Config loader
│   ├── api/             # REST + WebSocket API
│   │   ├── app.py       # FastAPI application
│   │   ├── models.py    # Pydantic schemas
│   │   ├── session.py   # WebSocket session management
│   │   └── routers/
│   │       ├── stats.py       # Stats and categories
│   │       ├── transactions.py # Transaction queries
│   │       ├── analytics.py   # Analytics endpoints
│   │       ├── budgets.py     # Budget CRUD
│   │       └── chat.py        # WebSocket chat
│   └── parsers/
│       ├── base.py      # Base parser class
│       ├── fnb.py       # FNB parser
│       └── __init__.py  # Parser registry
├── frontend/             # Svelte web frontend
│   ├── src/
│   │   ├── App.svelte   # Main app layout
│   │   ├── lib/         # API client, WebSocket, stores
│   │   └── components/
│   │       ├── Chat.svelte        # Chat interface
│   │       ├── Dashboard.svelte   # Stats overview
│   │       ├── Analytics.svelte   # Pie chart analytics
│   │       ├── Budget.svelte      # Budget management
│   │       ├── Transactions.svelte # Transaction list
│   │       ├── PieChart.svelte    # Reusable pie chart
│   │       └── CategoryChart.svelte # Bar chart
│   ├── package.json
│   └── vite.config.js
├── tests/                # Test suite
├── config.yaml
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

