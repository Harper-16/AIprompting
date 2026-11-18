# AI Prompting

A collection of Python prompt-engineering exercises and AI demos. The main app
is a Streamlit image generator that enhances a description, checks it with a
safety-filter API, then generates an image with Cloudflare Workers AI.

## Features

- **Safe AI Image Generator** — prompt enhancement, safety checks, image
  generation, and PNG download.
- **Prompt-engineering exercises** — interactive command-line activities for
  improving prompts and exploring temperature.
- **NEXUS Groq Command Center** — a separate terminal UI with a Groq chat panel
  and local shell tabs.

## Requirements

- Python 3.10 or newer
- API credentials for the services used by the app you want to run

## Run the image generator

From the project root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Start the app:

```bash
streamlit run src/main_7.py
```

The app asks for a Cloudflare account ID and Workers AI API token if they are
not configured in the environment. Create a token with **Workers AI Read** and
**Workers AI Edit** permissions from the
[Cloudflare Workers AI dashboard](https://dash.cloudflare.com/?to=/:account/ai/workers-ai).
The image backend uses Cloudflare's `@cf/black-forest-labs/flux-1-schnell`
model. Cloudflare account usage limits and pricing apply.

Prompt enhancement uses the Groq-compatible API client. Set a Groq API key
before starting Streamlit:

```bash
export GROQ_API_KEY="your-groq-api-key"
```

To avoid entering Cloudflare credentials in the app each time, set these
environment variables before launching it:

```bash
export CLOUDFLARE_ACCOUNT_ID="your-cloudflare-account-id"
export CLOUDFLARE_API_TOKEN="your-workers-ai-api-token"
```

`GROQ_BASE_URL` can optionally override the Groq API URL. Never commit API
tokens or put them in source files.

## Run the prompt exercises

With the root virtual environment active and `GROQ_API_KEY` set:

```bash
python src/main.py
```

For the temperature and instruction exercise:

```bash
python src/main_2.py
```

Other `src/main_*.py` files are additional examples and exercises.

## Run the NEXUS command center

The terminal UI has its own dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r groq_command_center/requirements.txt
export GROQ_API_KEY="your-groq-api-key"
python groq_command_center/app.py
```

The command center can send prompts to Groq and run commands in local shell
tabs. Only run shell commands you trust.

## Project layout

```text
src/
  main_7.py              Streamlit image generator
  main.py                Basic prompt-engineering exercise
  main_2.py              Temperature and instruction exercise
  groq.py                Groq-compatible chat client
  hf.py                  Optional Hugging Face chat client
  config.py              Environment-based configuration
groq_command_center/
  app.py                 Textual terminal application
  requirements.txt       Command center dependencies
requirements.txt         Main project dependencies
```

## Troubleshooting

- **Cloudflare authentication error:** verify the Cloudflare email, confirm the
  token was successfully created, and use its full value (not its name). The
  token and account ID must belong to the same account.
- **Prompt enhancement error:** set a valid `GROQ_API_KEY`.
- **Safety filter error:** the app needs network access to the configured
  safety-filter API.
