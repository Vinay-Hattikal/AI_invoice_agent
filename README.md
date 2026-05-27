# AI Automation Document Pipeline - Take-Home Assignment

An end-to-end AI agent pipeline designed for the logistics operations team to ingest, parse, classify, extract, and conditionally route vendor emails and invoice attachments.

## Video Walkthrough
[REQUIRED Walkthrough Video (OBS/Loom) - Click here to watch](https://loom.com/share/placeholder_link_for_submission)
*(Please replace this placeholder with your actual Loom/screen-recording link for submission.)*

---

## Setup & Run Instructions

### 1. Requirements
- Windows OS (with PowerShell/Cmd)
- Python 3.10 or higher installed and in system PATH

### 2. Fast Setup (One-Command)
Double-click the **`run_pipeline.bat`** script in the project root directory. This automated script will:
1. Initialize a Python virtual environment (`venv`) if not already present.
2. Update pip and install dependencies from `requirements.txt`.
3. Load the payload and process the 10 sample files in sequence.

### 3. Manual Installation
Alternatively, run these commands in your shell:
```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate

# Install requirements
pip install -r requirements.txt

# Run the pipeline
python pipeline.py
```

### 4. Configuration (`.env`)
Provide credentials in `.env` (a `.env` template is provided as `.env.example`):
```ini
OPENROUTER_API_KEY=sk-or-v1-...
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
RESEND_API_KEY=re_...
EMAIL_SENDER=onboarding@resend.dev
```

---

## Design Decisions & Technical Architecture

1. **Multimodal OpenRouter Extraction**: The pipeline is fully integrated with OpenRouter.
   - **PDFs**: Text is extracted dynamically using the pure-Python `pypdf` library and parsed.
   - **Images (JPG/PNG)**: Files are base64-encoded and sent as visual payloads using OpenRouter's vision message format.
   - **Model Rotation Fallback**: The agent sequentially tries `google/gemini-2.5-flash`, then `google/gemini-2.5-pro` and `openai/gpt-4o-mini` to handle model timeouts or quota restrictions.
2. **Schema Enforcement (Pydantic + JSON Mode)**: We use OpenRouter's JSON response formatting (`response_format={"type": "json_object"}`) coupled with Pydantic model validation (`models.py`) to guarantee type safety and JSON format conformance.
3. **Ambiguous Invoice (`inv_005.pdf`) Handling**:
   - *Observation*: Has Subtotal (Rs. 49,560), Invoice Total with GST (Rs. 58,480), and Net Payable after Rs. 10,000 advance (Rs. 48,480).
   - *Decision*: We extract **Rs. 58,480** (GST-inclusive Invoice Total) as the primary `total_amount` for routing.
   - *Rationale*: Operations and approval limits (> Rs. 50,000 threshold) are based on the complete transaction value/liability. Advances are payment settlement items and do not change the invoice value or tax liability.
4. **Conditional Routing**:
   - **Total > Rs. 50,000**: Dispatches a rich Slack Block Kit notification to the manager channel.
   - **Total <= Rs. 50,000**: Logs a structured row in `sample_output/processed_invoices.csv`.
   - **Unknown / Failed (e.g., `inv_010.pdf`)**: Appends details to `sample_output/human_review.log` with a descriptive reason.
5. **Acknowledgment & Resend API**: Sends automated acknowledgement emails to vendors via the Resend API. If a vendor email is unverified (Resend free sandbox limit), it gracefully redirects the email to `delivered@resend.dev` (standard sandbox inbox) or falls back to a clean mock console print, ensuring pipeline continuity.
6. **Graceful Degradation & Retry**: Implements `tenacity` retries with exponential backoff for rate limits (429) or transient errors. Bad/corrupt files return an `unknown` class extraction safely, preventing pipeline crashes.

---

## Output Logs Location
- Extractions: Individual JSON extractions are saved in `sample_output/` as `<filename>_extracted.json`.
- Spreadsheet Fallback: `sample_output/processed_invoices.csv`.
- Human Intervention Queue: `sample_output/human_review.log`.
- Running Log: `sample_output/routing_log.json`.
