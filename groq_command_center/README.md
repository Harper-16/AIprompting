# NEXUS // Groq Command Center

A split-screen terminal UI with a streaming Groq chat panel, an operational
agent activity feed, and multiple independent local shell tabs.

## Run

Requires Python 3.10+ on Linux or macOS.

```bash
cd groq_command_center
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export GROQ_API_KEY="your-groq-api-key"
python app.py
```

Optional environment variables:

- `GROQ_MODEL`: model name (defaults to `llama-3.3-70b-versatile`)
- `GROQ_BASE_URL`: API-compatible endpoint (defaults to Groq's API URL)

## Controls

- Enter a prompt in the left panel to stream a response.
- Enter a command in the right panel to run it in that tab's persistent shell.
- `+` or `Ctrl+N`: create a shell tab.
- `Ctrl+Tab` / `Ctrl+Shift+Tab`: cycle shell tabs.
- `×`: close a shell tab. Closing the last tab opens a fresh one.
- `INTERRUPT`: send SIGINT to the active shell.
- `Ctrl+L`: clear the active terminal's display.
- `Ctrl+Q`: quit.

The activity feed reports request and shell lifecycle events. It intentionally
does not expose hidden model reasoning.
