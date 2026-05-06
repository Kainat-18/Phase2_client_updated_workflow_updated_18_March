# Theology Academy Studio - Beginner Setup Guide

This guide is written for a non-technical person.  
Follow the steps exactly, top to bottom.

## What this project does

You give a script (`.md`, `.txt`, `.docx`, `.pdf`) and it generates:

- scene-wise storyboard JSON/CSV
- Canva-ready image prompts
- overlay text content
- references/citation structure
- compliance report and preview files

Output is saved inside the `output/` folder.

---

## 1) Requirements (install once)

Install these on your computer:

- Python 3.11+ (recommended: 3.12)
- pip (usually included with Python)
- Git (optional, only if you need to clone)

Check installation:

```bash
python3 --version
pip3 --version
```

---

## 2) Open project folder

In terminal, go to the project root (where `main.py` exists):

```bash
cd /path/to/Phase2_client_updated_workflow
```

---

## 3) Create virtual environment (recommended)

If you are setting up fresh:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

If your project already has `venv/`, you can use it instead:

```bash
source venv/bin/activate
```

After activation, your terminal usually shows `(.venv)` or `(venv)`.

---

## 4) Install libraries

```bash
pip install -r requirements.txt
```

---

## 5) Create `.env` file and add API key

Copy example:

```bash
cp .env.example .env
```

Open `.env` and set your real xAI key:

```dotenv
LLM_PROVIDER=xai
LLM_BASE_URL=https://api.x.ai/v1
LLM_MODEL=grok-4-fast-reasoning
XAI_API_KEY=your_real_xai_api_key_here
```

Optional but useful:

```dotenv
LLM_STRICT=true
LLM_DEBUG=true
```

---

## 6) Put input script in `uploads/`

Example:

```bash
uploads/my_script.md
```

Supported file types:

- `.md`
- `.txt`
- `.docx`
- `.pdf`

---

## 7) Run project for one script

If using `.venv`:

```bash
python main.py run --input "uploads/my_script.md"
```

If using existing `venv`:

```bash
./venv/bin/python main.py run --input "uploads/my_script.md"
```

If successful, terminal shows:

```text
Created: output/<script_name_slug>
```

---

## 8) Run for many scripts (batch mode)

Put all files inside `uploads/`, then run:

```bash
python main.py batch --input-dir "uploads"
```

This generates separate output folders for each script.

---

## 9) Where to find generated files

For each script, check:

```text
output/<script_slug>/
```

Important files:

- `storyboard.json`
- `storyboard.csv`
- `final_scene_manifest.json`
- `final_scene_manifest.csv`
- `canva_prompts.csv`
- `phase2_paragraph_prompts.csv`
- `book_timeline.json`
- `animator_instruction_packet.json`
- `compliance_report.json`
- `storyboard_preview.html`

---

## 10) Optional: run web UI

Start server:

```bash
uvicorn webapp:app --host 127.0.0.1 --port 8000 --reload
```

Open in browser:

```text
http://127.0.0.1:8000
```

Default login (change after first use):

- Username: `admin`
- Password: `admin12345`

---

## 11) Optional useful commands

Check active LLM config:

```bash
python main.py debug-llm
```

Run with academic sync file:

```bash
python main.py run --input "uploads/youtube.md" --academic-input "uploads/academic.md"
```

Generate draft images from storyboard:

```bash
python main.py generate-images --storyboard "output/<script_slug>/storyboard.json"
```

Make preview video:

```bash
python main.py make-video --storyboard "output/<script_slug>/storyboard.json"
```

Attach Canva exported images:

```bash
python main.py attach-canva-images --storyboard "output/<script_slug>/storyboard.json" --images-dir "output/<script_slug>/images"
```

---

## 12) Troubleshooting (common issues)

### Error: `ModuleNotFoundError: No module named 'typer'`

Run:

```bash
pip install -r requirements.txt
```

### Error: `XAI_API_KEY` missing

Set valid key in `.env`:

```dotenv
XAI_API_KEY=your_real_xai_api_key_here
```

### Error: input file not found

Make sure file exists and path is exact:

```bash
python main.py run --input "uploads/your_file.md"
```

### `python` command not found

Try:

```bash
python3 main.py run --input "uploads/your_file.md"
```

---

## Quick Start (copy-paste block)

Use this if you want the fastest setup from scratch:

```bash
cd /path/to/Phase2_client_updated_workflow
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and set XAI_API_KEY
python main.py run --input "uploads/methodological_epistemological_youtube.md"
```
