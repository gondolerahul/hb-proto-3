# Document Factory Engine — Design Document

## Overview

The Document Factory Engine is a hierarchical agentic system that converts
open-source Claude Skills knowledge into model-agnostic autonomous agents.
Each agent specializes in a single document type (DOCX, PPTX, XLSX, PDF)
and contains the full domain expertise distilled from the original skill
definitions — embedded directly into system prompts and behavioral constraints
so any LLM backend can execute them.

## Tools Used

| Tool | Purpose |
|------|---------|
| `sandbox_code` | Python/Node.js code execution (openpyxl, pandas, docx-js, PptxGenJS, reportlab) |
| `terminal` | Shell commands (unpack/pack scripts, pandoc, LibreOffice, pdftoppm) |

## Entity Hierarchy (~50 entities)

```
PROCESS: 📄 Document Factory Engine
├── AGENT: 📝 DOCX Document Agent
│   ├── SKILL: DOCX Creator
│   │   └── ACTION: Generate DOCX (docx-js)                [sandbox_code]
│   ├── SKILL: DOCX Editor
│   │   ├── ACTION: Unpack DOCX                             [terminal]
│   │   ├── ACTION: Edit DOCX XML                           [sandbox_code]
│   │   └── ACTION: Pack DOCX                               [terminal]
│   ├── SKILL: DOCX Reader
│   │   └── ACTION: Extract DOCX Content                    [terminal]
│   └── SKILL: DOCX Validator
│       └── ACTION: Validate DOCX                           [terminal]
├── AGENT: 📊 PPTX Presentation Agent
│   ├── SKILL: PPTX Creator (from scratch)
│   │   └── ACTION: Generate PPTX (PptxGenJS)              [sandbox_code]
│   ├── SKILL: PPTX Template Editor
│   │   ├── ACTION: Analyze Template                        [terminal]
│   │   ├── ACTION: Unpack PPTX                             [terminal]
│   │   ├── ACTION: Manipulate Slides                       [sandbox_code]
│   │   └── ACTION: Pack PPTX                               [terminal]
│   ├── SKILL: PPTX Reader
│   │   └── ACTION: Extract PPTX Content                    [terminal]
│   └── SKILL: PPTX Visual QA
│       ├── ACTION: Convert Slides to Images                [terminal]
│       └── ACTION: Visual Inspection                       [sandbox_code]
├── AGENT: 📈 XLSX Spreadsheet Agent
│   ├── SKILL: XLSX Creator
│   │   └── ACTION: Generate XLSX (openpyxl)                [sandbox_code]
│   ├── SKILL: XLSX Editor
│   │   └── ACTION: Edit XLSX (openpyxl)                    [sandbox_code]
│   ├── SKILL: XLSX Data Analyzer
│   │   └── ACTION: Analyze Data (pandas)                   [sandbox_code]
│   ├── SKILL: XLSX Formula Engine
│   │   ├── ACTION: Recalculate Formulas                    [terminal]
│   │   └── ACTION: Verify & Fix Errors                     [sandbox_code]
│   └── SKILL: XLSX Financial Formatter
│       └── ACTION: Apply Financial Standards               [sandbox_code]
├── AGENT: 📕 PDF Document Agent
│   ├── SKILL: PDF Creator
│   │   └── ACTION: Generate PDF (reportlab)                [sandbox_code]
│   ├── SKILL: PDF Manipulator
│   │   ├── ACTION: Merge/Split PDFs                        [sandbox_code]
│   │   └── ACTION: Rotate/Crop Pages                       [sandbox_code]
│   ├── SKILL: PDF Reader
│   │   ├── ACTION: Extract Text                            [sandbox_code]
│   │   └── ACTION: Extract Tables                          [sandbox_code]
│   ├── SKILL: PDF Form Filler
│   │   ├── ACTION: Detect Form Fields                      [terminal]
│   │   └── ACTION: Fill Form                               [terminal]
│   └── SKILL: PDF Security
│       └── ACTION: Encrypt/Decrypt PDF                     [sandbox_code]
└── AGENT: ✅ Document QA & Delivery
    └── SKILL: Document QA Pipeline
        ├── ACTION: Content Validation                      [sandbox_code]
        └── ACTION: Archive & Deliver                       [terminal]
```

## Execution Flow

1. **Request Analysis**: Process analyzes user request to determine document type(s) needed
2. **Dynamic Routing**: Invokes only the relevant document agent(s)
3. **Agent Orchestration**: Each agent decides which skills to invoke based on the task
4. **QA & Delivery**: Validates generated documents and archives outputs

## Setup

```bash
# Create all entities
python create_doc_entities.py

# Trigger an execution
python trigger_doc_execution.py

# Trigger with custom request
python trigger_doc_execution.py --request "Create a quarterly sales report as PPTX"

# Cleanup and recreate
python create_doc_entities.py --cleanup
```

## Files

| File | Purpose |
|------|---------|
| `config.py` | API client, auth, and shared configuration |
| `actions_docx.py` | DOCX ACTION entity definitions |
| `actions_pptx.py` | PPTX ACTION entity definitions |
| `actions_xlsx.py` | XLSX ACTION entity definitions |
| `actions_pdf.py` | PDF ACTION entity definitions |
| `actions_qa.py` | QA & Delivery ACTION entity definitions |
| `skills.py` | All SKILL entity definitions |
| `agents.py` | All AGENT entity definitions |
| `create_doc_entities.py` | Main setup script — creates all entities and links hierarchy |
| `trigger_doc_execution.py` | Trigger script — fires document generation with sample request |
| `scripts/` | Helper scripts bundled from Claude Skills (docx, pptx, xlsx, pdf) |
| `entity_ids.json` | Generated — maps entity keys to UUIDs (created by setup) |
