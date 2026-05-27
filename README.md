# AI Document Automation Pipeline

An AI-powered invoice processing system that automatically reads vendor documents, extracts structured invoice data, applies routing rules, and handles failures gracefully.

## Video Walkthrough

Project Demo: https://drive.google.com/drive/folders/1Lr4AcQvKUOIQArrwC57-ypID35kfm_AU?usp=sharing

---

## Features

* Processes PDF and image invoices
* Extracts structured invoice fields using LLMs
* Validates outputs using Pydantic schemas
* Sends Slack alerts for invoices above ₹50,000
* Stores lower-value invoices in CSV
* Routes failed or unreadable files to a human review queue
* Handles malformed AI responses and API failures gracefully
* Uses model fallback rotation through OpenRouter

---

## Tech Stack

* Python 3
* FastAPI
* OpenRouter (Gemini Flash, Gemini Pro, GPT-4o-mini)
* Pydantic
* Slack Webhooks
* Resend API
* CSV Logging

---

## Project Structure

* `main.py` / `server.py` → FastAPI backend and API routes
* `pipeline.py` → Main workflow runner
* `document_processor.py` → AI extraction and validation
* `router.py` → Routing logic
* `notifier.py` → Slack and email notifications
* `models.py` → Pydantic schemas
* `sample_output/` → Logs and extracted outputs

---

## Routing Rules

* Invoice amount > ₹50,000 → Slack alert
* Invoice amount ≤ ₹50,000 → CSV logging
* Unknown or failed extraction → `human_review.log`

---

## Important Design Decision

Invoice `inv_005` contained multiple totals:

* subtotal,
* invoice total,
* and remaining payable amount after advance payment.

The pipeline intentionally uses the GST-inclusive invoice total instead of the remaining payable amount to ensure high-value invoices are routed correctly through the approval workflow.

---

## Setup

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Add `.env`

```env
OPENROUTER_API_KEY=your_key
SLACK_WEBHOOK_URL=your_webhook
RESEND_API_KEY=your_key
EMAIL_SENDER=your_email
```

### Run Pipeline

```bash
python pipeline.py
```

---

## Output Files

* `sample_output/processed_invoices.csv`
* `sample_output/human_review.log`
* `sample_output/routing_log.json`
* Extracted JSON files for each invoice

---

## Error Handling

The system gracefully handles:

* unreadable files
* invalid AI responses
* missing fields
* API failures
* model quota exhaustion

If extraction fails, the document is automatically routed to the human review queue instead of being dropped.

---

## Notes

* If API keys are missing, the system falls back to mock logging.
* OpenRouter model fallback is used to prevent failures during quota exhaustion.
* The project is organized into modular components for easier maintenance and debugging.
