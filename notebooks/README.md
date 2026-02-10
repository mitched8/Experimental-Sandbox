# Walkthrough notebooks

These notebooks walk through the two main pipelines in **markets-briefing** (Experimental-Sandbox).

## Prerequisites

- Python 3.11+
- Dependencies installed from project root: `pip install -e .` (or `pip install -r` requirements from `pyproject.toml`)
- Copy `.env.example` to `.env` and set the API keys you need (see below)

## Notebooks

| Notebook | Pipeline | Description |
|----------|----------|-------------|
| **01_podcast_processor_walkthrough.ipynb** | Podcast processor | RSS → download → transcribe → speaker attribution → summary → markdown. Needs `ANTHROPIC_API_KEY` and one of `ASSEMBLYAI_API_KEY` or `OPENAI_API_KEY`. |
| **02_polymarket_fx_monitor_walkthrough.ipynb** | Polymarket FX monitor | Fetch markets → keyword filter → Claude FX classification → SQLite snapshot → markdown report. Needs `ANTHROPIC_API_KEY` for classification; fetch and filter work without keys. |

## How to run

1. **Start from project root** so imports work. In Jupyter/Lab, set the kernel’s working directory to the repo root (the folder that contains `podcast_processor/`, `polymarket_monitor/`, and `notebooks/`).  
   Or from a terminal: `cd /path/to/Experimental-Sandbox` then `jupyter notebook notebooks/` (or `jupyter lab`).

2. Run the **Setup** cell first in each notebook so `ROOT` and `sys.path` point to the project root and `.env` is loaded.

3. Run cells in order. Steps that require API keys will either run (if keys are set) or use mocks/dry-run behaviour and print a short message.

## API keys (.env)

- **Podcast:** `ANTHROPIC_API_KEY` (speaker attribution + summary); `ASSEMBLYAI_API_KEY` or `OPENAI_API_KEY` (transcription). Optional: `OUTPUT_DIR`.
- **Polymarket:** `ANTHROPIC_API_KEY` (FX classification). Fetch and keyword filter use no keys.

See `.env.example` in the project root for variable names.
