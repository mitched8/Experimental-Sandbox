# Walkthrough notebooks

These notebooks walk through the two main pipelines in **markets-briefing** (Experimental-Sandbox).

## Prerequisites

- Python 3.11+
- Dependencies installed from project root: `pip install -e .` (or `pip install -r` requirements from `pyproject.toml`)
- Copy `.env.example` to `.env` and set the API keys you need (see below)
- Optional: from project root run `./.venv/bin/pip install ipykernel` so the `.venv` appears in the notebook kernel list

## Notebooks

| Notebook | Pipeline | Description |
|----------|----------|-------------|
| **01_podcast_processor_walkthrough.ipynb** | Podcast processor | RSS → download → transcribe → speaker attribution → summary → markdown. Needs `ANTHROPIC_API_KEY` and one of `ASSEMBLYAI_API_KEY` or `OPENAI_API_KEY`. |
| **02_polymarket_fx_monitor_walkthrough.ipynb** | Polymarket FX monitor | Fetch markets → keyword filter → Claude FX classification → SQLite snapshot → markdown report. Needs `ANTHROPIC_API_KEY` for classification; fetch and filter work without keys. |

## How to run

1. **Use the project .venv as the notebook kernel** so dotenv and other deps are available. In Jupyter/Lab, set the kernel’s working directory to the repo root (the folder that contains `podcast_processor/`, `polymarket_monitor/`, and `notebooks/`).  
From terminal: `cd Experimental-Sandbox && .venv/bin/jupyter notebook notebooks/`.

2. Run the **Setup** cell first in each notebook (it finds project root and loads `.env`).

3. Run cells in order. With API keys in `.env`, you can test the full pipeline (Polymarket Claude classification; Podcast transcription + summary).

## API keys (.env)

- **Podcast:** `ANTHROPIC_API_KEY` (speaker attribution + summary); `ASSEMBLYAI_API_KEY` or `OPENAI_API_KEY` (transcription). Optional: `OUTPUT_DIR`.
- **Polymarket:** `ANTHROPIC_API_KEY` (FX classification). Fetch and keyword filter use no keys.

See `.env.example` in the project root for variable names.
