# LLM Council - fork w/ Cursor CLI back-end

Same as original, except Cursor CLI as back-end + allow setting of working directory for your project.

![llmcouncil](header.jpg)

The idea of this repo is that instead of asking a question to your favorite LLM provider (e.g. OpenAI GPT 5.1, Google Gemini 3.0 Pro, Anthropic Claude Opus 4.5, xAI Grok 4, etc.), you can group them into your "LLM Council". This repo is a simple, local web app that essentially looks like ChatGPT except it uses **Cursor CLI** to send your query to multiple LLMs in parallel, it then asks them to review and rank each other's work, and finally a Chairman LLM produces the final response.

In a bit more detail, here is what happens when you submit a query:

1. **Stage 1: First opinions**. The user query is given to all LLMs individually in parallel, and the responses are collected. The individual responses are shown in a "tab view", so that the user can inspect them all one by one.
2. **Stage 2: Review**. Each individual LLM is given the responses of the other LLMs. Under the hood, the LLM identities are anonymized so that the LLM can't play favorites when judging their outputs. The LLM is asked to rank them in accuracy and insight.
3. **Stage 3: Final response**. The designated Chairman of the LLM Council takes all of the model's responses and compiles them into a single final answer that is presented to the user. When the final answer is ready, you'll receive a browser notification (even if you're in another app).

## Key Features

- **Parallel LLM Queries**: All models respond simultaneously for faster results
- **Workspace Selection**: Choose a project directory so models can answer questions about your codebase
- **Browser Notifications**: Get notified when the final answer is ready
- **Real-time Progress**: See incremental output as models generate responses
- **Model Rankings**: See how each model ranks the others' responses
- **Aggregate Rankings**: View consensus rankings across all models

## Vibe Code Alert

This project was 99% vibe coded as a fun Saturday hack because I wanted to explore and evaluate a number of LLMs side by side in the process of [reading books together with LLMs](https://x.com/karpathy/status/1990577951671509438). It's nice and useful to see multiple responses side by side, and also the cross-opinions of all LLMs on each other's outputs. I'm not going to support it in any way, it's provided here as is for other people's inspiration and I don't intend to improve it. Code is ephemeral now and libraries are over, ask your LLM to change it in whatever way you like.

## Prerequisites

- **Cursor**: You need [Cursor](https://cursor.sh/) installed and authenticated
- **Python 3.10+**: For the backend
- **Node.js**: For the frontend
- **uv**: Python package manager ([install guide](https://docs.astral.sh/uv/))

## Setup

### 1. Install Dependencies

The project uses [uv](https://docs.astral.sh/uv/) for Python project management.

**Backend:**
```bash
uv sync
```

**Frontend:**
```bash
cd frontend
npm install
cd ..
```

### 2. Authenticate Cursor CLI

Make sure you're authenticated with Cursor:

```bash
cursor agent login
```

This will open a browser to authenticate. The Cursor CLI needs to be authenticated to access the models.

### 3. Configure Models (Optional)

Edit `backend/config.py` to customize the council:

```python
COUNCIL_MODELS = [
    "openai/gpt-5.1",              # Maps to gpt-5.1-high
    "google/gemini-3-pro-preview",  # Maps to gemini-3-pro
    "anthropic/claude-opus-4.5",   # Maps to opus-4.5-thinking
    "x-ai/grok-4",                  # Maps to grok
]

CHAIRMAN_MODEL = "google/gemini-3-pro-preview"
```

The models are automatically mapped to Cursor CLI model names (using "max" mode variants where available). See `CURSOR_MODEL_MAP` in `config.py` for the full mapping.

### 4. Configure Workspace (Optional)

You can set a default workspace directory via environment variable:

```bash
# In .env file or export
CURSOR_WORKSPACE=/path/to/your/project
```

Or select it in the UI when creating a new conversation (recommended).

## Running the Application

**Option 1: Use the start script**
```bash
./start.sh
```

**Option 2: Run manually**

Terminal 1 (Backend):
```bash
uv run python -m backend.main
```

Terminal 2 (Frontend):
```bash
cd frontend
npm run dev
```

Then open http://localhost:5173 in your browser.

## Usage

1. **Create a Conversation**: Click "New Conversation" in the sidebar
2. **Select Workspace** (optional): Choose a project directory from the dropdown before sending your first message. This gives models context about your codebase.
3. **Ask a Question**: Type your question and press Enter
4. **Watch the Process**: 
   - Stage 1: See individual responses from each model
   - Stage 2: See how models rank each other's responses
   - Stage 3: See the final synthesized answer
5. **Get Notified**: You'll receive a browser notification when the final answer is ready (you'll be prompted to allow notifications on first use)

## How It Works

### Cursor CLI Integration

Instead of using OpenRouter API, this project uses Cursor's CLI (`cursor agent`) to execute queries. Each model query runs as:

```bash
cursor agent --model "model-name" --print --workspace "/path/to/workspace" -
```

The query is passed via stdin, and output is captured from stdout. Models run in parallel using Python's `asyncio`.

### Workspace Context

When you select a workspace directory, all Cursor CLI commands run with `--workspace` flag pointing to that directory. This allows models to:
- Answer questions about your codebase
- Reference specific files
- Understand project structure
- Provide context-aware responses

The workspace is persisted per conversation, so each conversation can have its own project context.

### Output Files

Each model's response is saved to a temporary Markdown file:
- Stage 1: `data/cursor_outputs/stage1_*/{model}.md`
- Stage 2: `data/cursor_outputs/stage2_*/{model}.md`
- Stage 3: `data/cursor_outputs/stage3_*/{model}.md`

These files are cleaned up automatically but can be useful for debugging.

## Tech Stack

- **Backend:** FastAPI (Python 3.10+), asyncio for parallel execution, Cursor CLI
- **Frontend:** React + Vite, react-markdown for rendering
- **Storage:** JSON files in `data/conversations/`
- **Package Management:** uv for Python, npm for JavaScript
- **LLM Access:** Cursor CLI (no API keys needed, uses Cursor authentication)

## Troubleshooting

### Models Timing Out

If models are timing out (default timeout is 180 seconds):
- Check that Cursor CLI is authenticated: `cursor agent status`
- Verify model names are correct in `config.py`
- Check logs for detailed error messages (stderr is logged)

### No Workspace Options

The workspace dropdown lists directories one level up from where you started the server. Make sure you're running the server from the project root.

### Browser Notifications Not Working

- Make sure you've allowed notifications in your browser
- Check browser console for any errors
- Notifications only appear when Stage 3 completes

## Project Structure

```
.
├── backend/
│   ├── main.py           # FastAPI server
│   ├── council.py        # 3-stage orchestration logic
│   ├── cursor_cli.py     # Cursor CLI integration
│   ├── config.py         # Configuration (models, workspace)
│   └── storage.py        # Conversation storage
├── frontend/
│   └── src/
│       ├── App.jsx       # Main app component
│       ├── components/   # UI components
│       └── api.js        # API client
└── data/
    └── conversations/    # Stored conversations (JSON)
```

## License

This project is provided as-is for inspiration and experimentation.
