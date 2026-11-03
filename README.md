# HealthResearch AI – Public Health Research Assistant

HealthResearch AI is a personal portfolio project exploring how AI can support public health research. It helps users find scientific research papers, understand their key findings, check references, and prepare simple health-related content.

The project uses four connected AI-assisted steps to organize the research process, from finding papers to preparing a summary.

## Main Features

1. **Research Agent:** Searches for relevant scientific papers using PubMed and Europe PMC.
2. **Evidence Analysis Agent:** Helps summarize research findings, study limitations, and evidence gaps.
3. **Citation Verification Agent:** Checks references and examines whether claims and statistics are supported by the retrieved research.
4. **Health Education Agent:** Uses the reviewed research to prepare summaries, articles, social media posts, and video scripts.

## Technologies Used

- Python and FastAPI
- React and TypeScript
- SQLite
- PubMed API and Europe PMC API
- AI Agents and LLM Integration

## How It Works

1. Enter a public health research question.
2. The application searches scientific databases for relevant papers.
3. The research findings are organized and summarized.
4. References and claims are checked against available research information.
5. The application prepares health-related content based on the reviewed findings.

## Example Research Question

*Does regular physical activity reduce the risk of depression in adults?*

## Project Purpose

The purpose of this project is to explore the practical use of AI in public health research, scientific literature analysis, and health education.

## Limitations

- The analysis mainly uses research titles and abstracts rather than complete research papers.
- Citation checks help identify unsupported references and claims but cannot guarantee that every finding is correct.
- The application is designed for educational and research purposes, not medical diagnosis or treatment advice.

## Running the Project

1. Install Python 3.10+ and Node.js.
2. Open the project folder in VS Code.
3. Run `start.bat`.
4. Open the application in your browser at `http://localhost:5173`.
5. Try the sample research question.

See the project files for further setup instructions.
