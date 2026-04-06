# Compliance Verifier

AI-powered compliance analysis tool that automatically verifies whether business processes comply with regulatory requirements using a multi-stage LLM pipeline.

## Tech Stack

- **Frontend**: Next.js 16, React 19, TypeScript, TailwindCSS, Radix UI, BPMN.js
- **Backend**: Flask (Python), LangChain + Azure OpenAI, Sentence Transformers, Pandas

## Getting Started

### Prerequisites

- Node.js 18+
- Python 3.10+
- Azure OpenAI API key

### Backend

```bash
pip install -r requirements.txt
# Create a .env with OPENAI_API_KEY=your-key
python backend/app.py
# Runs at http://localhost:5005
```

### Frontend

```bash
npm install
npm run dev
# Runs at http://localhost:3000
```

## How It Works

The compliance pipeline runs four stages:

| Stage | Name | Purpose |
|-------|------|---------|
| S1 | Classification | Classifies a a chunk contains a rule (obligation, prohibition, timeframe, etc.) |
| S2 | Relevance Filtering | Filters rules relevant to the process using embeddings + LLM |
| S3 | Dual-Run Analysis | Two independent LLM evaluations with strictness-based resolution |
| S4 | Ambiguity Detection | Identifies ambiguous terms that require assumptions |

Results are categorized as **COMPLIANT**, **NON-COMPLIANT**, or **NO EVIDENCE**.

## Features

- **Multi-stage compliance pipeline** with dual-run analysis and strictness resolution
- **Embedding pre-filtering** (all-MiniLM-L6-v2) to speed up relevance checks
- **Flexible input**: hardcoded process templates, free-text entry, or BPMN file upload
- **Regulation management**: upload PDF, DOCX or enter text directly
- **Interactive results UI**: segment table with category filtering, inline ambiguity indicators, process text highlighting, regulation chunk viewer with ambiguous term highlighting
- **BPMN visualization** with element highlighting linked to compliance findings
- **Short reasoning**
- **Analysis history** persisted as Excel files in `backend/history/`
- **Streaming progress** via server-sent events during analysis

## Project Structure

```
cv10/
├── app/                          # Next.js pages & API routes
│   └── api/                      # Proxy routes to Flask backend
├── backend/
│   ├── app.py                    # Flask API server
│   ├── functions_pipeline_v8.py  # Compliance pipeline (S1-S4)
│   ├── prompts/                  # LLM prompt templates (1-4)
│   └── history/                  # Saved analysis results (.xlsx)
├── components/
│   ├── document-reviewer.tsx     # Main app container & state
│   ├── document-selector.tsx     # Process/regulation selection
│   ├── segment-table.tsx         # Compliance results table
│   ├── text-viewer.tsx           # Process text with highlighting
│   ├── chunk-viewer.tsx          # Regulation chunks display
│   ├── bpmn-viewer.tsx           # BPMN diagram viewer
│   ├── manage-documents.tsx      # Upload/manage regulations
│   └── history-view.tsx          # Past analyses browser
├── lib/
│   ├── types.ts                  # TypeScript interfaces
│   └── utils.ts                  # Helpers
├── requirements.txt              # Python dependencies
└── package.json                  # Node dependencies
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Azure OpenAI API key |
| `FLASK_BACKEND_URL` | Backend URL (default: `http://localhost:5005`) |
