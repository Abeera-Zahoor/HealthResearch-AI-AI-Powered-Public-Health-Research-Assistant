# HealthResearch AI — Multi-Agent Public Health Research Assistant

A full-stack portfolio project. You ask a health research question; four connected agents find **real papers**, analyse the evidence, **verify the citations**, and write a summary, article, social posts or video script — flagging anything that cannot be verified.

**Stack:** React + TypeScript + Vite · Python FastAPI + Pydantic · SQLite · PubMed + Europe PMC APIs · configurable LLM (optional).

## The four agents

| # | Agent | What it does |
|---|-------|--------------|
| 1 | **Research Agent** | Searches PubMed (E-utilities) and Europe PMC, merges duplicates, ranks results, builds links from real PMIDs/DOIs. The LLM (if enabled) only helps write search queries; it never supplies papers. |
| 2 | **Evidence Analysis Agent** | Summarises findings, evidence gaps, limitations and study-design mix. Gaps and limitations that can be computed (no RCTs, missing abstracts, preprints...) are computed in code. |
| 3 | **Citation Verification Agent** | Checks each reference (metadata, retraction, preprint, **cross-check in a second database**) and each claim (must cite a retrieved paper, share wording with its abstract, and every statistic must literally appear in the source). An LLM "judge" must give a **verbatim quote** that code then finds in the abstract. |
| 4 | **Health Education Agent** | Writes the chosen output from **verified findings only**, then re-checks the text: unknown citations are removed, invented statistics are flagged. If nothing was verified it writes nothing. |

**No LLM key? It still works.** With `LLM_PROVIDER=none` (the default) findings are the authors' own conclusion sentences copied from abstracts, and output is assembled from templates. Add a key for synthesis and audience-tailored writing.

## Quick start (Windows)

1. Install **Python 3.10+** (tick *"Add python.exe to PATH"*) from python.org and **Node.js LTS** from nodejs.org.
2. Open this folder in VS Code (File > Open Folder).
3. Double-click **`start.bat`** (or run it in the VS Code terminal). The first run creates the Python environment, installs packages, creates `backend\.env`, then opens two windows (backend + frontend) and your browser at <http://localhost:5173>.
4. Click **Use sample question**, then **Run research workflow**.

Sample question: *Does regular physical activity reduce the risk of depression in adults?*

### Or with two terminals

```powershell
# Terminal 1 - backend
cd backend
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:create_app --factory --port 8000

# Terminal 2 - frontend
cd frontend
npm install
npm run dev
```
If PowerShell blocks `activate`, run `.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --port 8000` instead.

## API keys and costs

| Service | Key needed? | Cost |
|---------|-------------|------|
| PubMed (NCBI) | No (optional `NCBI_API_KEY` raises the rate limit) | Free |
| Europe PMC | No | Free |
| LLM provider | Only for AI writing/synthesis | Your provider's pricing; some have free tiers, and a local Ollama server is free |

Edit **`backend/.env`** (copied from `backend/.env.example`):

```ini
# Anthropic
LLM_PROVIDER=anthropic
LLM_API_KEY=your-key
LLM_MODEL=            # blank = default; check your provider's current model names

# OpenAI
LLM_PROVIDER=openai
LLM_API_KEY=your-key

# Any OpenAI-compatible service (Groq, OpenRouter, Gemini's compatible endpoint, Ollama)
LLM_PROVIDER=openai
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=your-model-name
```
Restart the backend after editing `.env`. Keys live **only** in `backend/.env` (git-ignored) and are never sent to the browser; the frontend only talks to `/api/*`.

## Tests

Run `run_tests.bat`, or `cd backend && .venv\Scripts\python -m pytest` and `cd frontend && npm test`.

Backend tests run fully offline (mock PubMed/Europe PMC servers and a scripted fake LLM; all fixture papers are clearly fake and live only in `backend/tests`). They cover API parsing, retries, merging/ranking, claim checks, hallucination catching, the whole four-agent pipeline, the LLM client and the database.

### What has and has not been verified

This project was built in a sandbox that blocked PyPI, npm and the live PubMed/Europe PMC servers. So:

- **Run and passing there:** 60 backend tests (agents, API clients, pipeline, DB, LLM client); 9 frontend unit tests (through a minimal test shim); strict `tsc` on the non-React TypeScript; the complete React app bundled and exercised in real Chromium (validation, live progress, all four tabs, history open/delete, markdown download, mobile layout) against a stand-in server running the **real pipeline**.
- **Written but NOT executed there:** the FastAPI layer (`app/main.py`) and its 2 API tests; `npm install`, `vite build`, `vitest` and full `tsc` on the React components; `start.bat`; real PubMed/Europe PMC calls (parsers are tested on realistic fixtures, not live responses); real LLM providers (request shapes tested with mocks).

Please run `run_tests.bat` on your machine first; failures will point at the exact file.

## Project structure

```
start.bat / run_tests.bat      one-click start and test scripts
backend/
  .env.example                 copy to .env (never commit .env)
  app/
    main.py                    FastAPI routes
    pipeline.py                connects the four agents, saves progress
    agents/                    research, analysis, citation, education
    apis/                      pubmed.py, europepmc.py, http.py
    db/                        SQLite storage (history)
    llm.py                     OpenAI-compatible + Anthropic client
    verification.py            deterministic claim / number / quote checks
    schemas.py  config.py  ...
  tests/                       pytest suite
frontend/src/                  React app (components/, lib/, api.ts)
```

API: `GET /api/health`, `POST /api/research`, `GET /api/research`, `GET /api/research/{id}`, `DELETE /api/research/{id}` (interactive docs at <http://127.0.0.1:8000/docs>).

## Limitations

- Analysis uses titles and abstracts only, not full texts; it is a rapid search, not a systematic review.
- Verification catches invented sources, numbers and quotes; it **cannot prove a claim is true**. "Strength" labels reflect study design, not quality appraisal.
- Output is educational, not medical advice. Always read the linked sources.

## Troubleshooting

- **Python not found:** reinstall Python with *Add to PATH*, then reopen the terminal.
- **Port 8000/5173 in use:** close old backend/frontend windows.
- **"Backend offline" pill:** check the backend window for errors.
- **Could not reach PubMed or Europe PMC:** check internet, firewall or VPN.
- **LLM errors:** the run falls back to extractive mode and says why; check `LLM_API_KEY` / `LLM_MODEL`.
- Changed `requirements.txt`? Delete `backend\.venv\.deps-installed` and rerun `start.bat`.
