import os
import json
import logging
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional, List

from fastapi import FastAPI, File, UploadFile, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

# Configure logging to console and server.log
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] server: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("server.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("server")

# Ensure dependencies path is resolved
sys.path.append(str(Path(__file__).parent.absolute()))
from models import InvoiceExtraction
from document_processor import process_document
from router import route_document, append_to_global_routing_log, ROUTING_LOG_PATH, OUTPUT_DIR, CSV_PATH
from notifier import send_email_acknowledgement

PORT = 8000

app = FastAPI(title="AI Operations Automation Agent API")

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serves static assets
@app.get("/")
def serve_index():
    return FileResponse("index.html")

@app.get("/index.css")
def serve_css():
    return FileResponse("index.css")

@app.get("/index.js")
def serve_js():
    return FileResponse("index.js")

@app.get("/api/logs")
def get_logs():
    """Returns the content of routing_log.json."""
    if not ROUTING_LOG_PATH.exists() or ROUTING_LOG_PATH.stat().st_size == 0:
        return []
    try:
        with open(ROUTING_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading routing log: {str(e)}")
        return JSONResponse(status_code=500, content={"error": "Failed to parse routing log JSON"})

@app.get("/api/export/processed")
def export_processed_csv():
    """Returns the processed_invoices.csv file directly."""
    if not CSV_PATH.exists():
        from router import init_output_files
        init_output_files()
    
    return FileResponse(
        CSV_PATH,
        media_type="text/csv",
        filename=f"processed_invoices_under_50k_{datetime.now().strftime('%Y-%m-%d')}.csv"
    )

@app.get("/api/extractions")
def get_extractions():
    """Lists files in the sample_documents folder available for simulation."""
    docs_dir = Path("sample_documents")
    if not docs_dir.exists():
        return []
    
    files = []
    for p in docs_dir.iterdir():
        if p.is_file() and p.suffix.lower() in [".pdf", ".jpg", ".jpeg", ".png"]:
            if p.name != "webhook_payload.json":
                files.append({
                    "filename": p.name,
                    "size_bytes": p.stat().st_size,
                    "extension": p.suffix.lower()
                })
    files.sort(key=lambda x: x["filename"])
    return files

@app.get("/api/extraction/{filename}")
def get_single_extraction(filename: str):
    """Reads the individual JSON extraction file from output folder."""
    safe_name = Path(filename).name
    stem = Path(safe_name).stem
    extraction_path = OUTPUT_DIR / f"{stem}_extracted.json"
    
    if not extraction_path.exists():
        return JSONResponse(status_code=404, content={"error": "Extraction file not found"})

    try:
        with open(extraction_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read extraction JSON for {safe_name}: {str(e)}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/review/{filename}")
def get_review_data(filename: str):
    """Returns outcome, extraction, and event for review/re-routing."""
    safe_name = Path(filename).name
    stem = Path(safe_name).stem
    extraction_path = OUTPUT_DIR / f"{stem}_extracted.json"
    
    # Find outcome from routing_log.json
    outcome = None
    if ROUTING_LOG_PATH.exists() and ROUTING_LOG_PATH.stat().st_size > 0:
        try:
            with open(ROUTING_LOG_PATH, "r", encoding="utf-8") as f:
                logs = json.load(f)
                for log in logs:
                    if log.get("filename") == safe_name:
                        outcome = log
                        break
        except Exception as e:
            logger.error(f"Error reading routing log: {str(e)}")
            
    if not outcome:
        outcome = {
            "event_id": f"evt_rev_{int(time.time())}",
            "filename": safe_name,
            "document_type": "unknown",
            "total_amount": None,
            "status": "failed",
            "routed_to": "unknown",
            "reason": "Log entry not found"
        }
        
    # Fetch extraction
    extraction = None
    if extraction_path.exists():
        try:
            with open(extraction_path, "r", encoding="utf-8") as f:
                extraction = json.load(f)
        except Exception as e:
            logger.error(f"Error reading extraction file: {str(e)}")
            
    if not extraction:
        extraction = {
            "document_type": "unknown",
            "vendor_name": None,
            "invoice_number": None,
            "date": None,
            "line_items": [],
            "total_amount": None,
            "confidence_score": 0.0,
            "reasoning": "Extraction file not found"
        }
        
    # Find or mock event
    event = None
    payload_path = Path("sample_documents/webhook_payload.json")
    if payload_path.exists():
        try:
            with open(payload_path, "r", encoding="utf-8") as f:
                payload_data = json.load(f)
                for ev in payload_data.get("events", []):
                    if ev.get("attachment", {}).get("filename") == safe_name:
                        event = ev
                        break
        except Exception as e:
            logger.error(f"Failed to load webhook payload: {str(e)}")
            
    if not event:
        event = {
            "event_id": outcome.get("event_id"),
            "received_at": datetime.now().isoformat(),
            "from": "manual_review@acme.com",
            "subject": f"Manual Review: {safe_name}",
            "attachment": {
                "filename": safe_name,
                "content_type": "application/pdf" if safe_name.endswith(".pdf") else "image/jpeg"
            }
        }
        
    return {
        "outcome": outcome,
        "extraction": extraction,
        "event": event
    }

class ProcessRequest(BaseModel):
    filename: str

@app.post("/api/process")
def process_document_endpoint(payload: ProcessRequest):
    """Triggers document processing, routing, and notifications live."""
    filename = payload.filename
    try:
        # Sanitize filename
        filename = Path(filename).name
        file_path = Path("sample_documents") / filename

        if not file_path.exists():
            return JSONResponse(status_code=404, content={"error": f"File '{filename}' does not exist in sample_documents"})

        # Search webhook_payload.json for email context
        event = None
        payload_path = Path("sample_documents/webhook_payload.json")
        if payload_path.exists():
            try:
                with open(payload_path, "r", encoding="utf-8") as f:
                    payload_data = json.load(f)
                    for ev in payload_data.get("events", []):
                        if ev.get("attachment", {}).get("filename") == filename:
                            event = ev
                            break
            except Exception as e:
                logger.error(f"Failed to load webhook payload: {str(e)}")

        if not event:
            event = {
                "event_id": f"evt_sim_{int(time.time())}",
                "received_at": datetime.now().isoformat(),
                "from": "simulated_sender@vendor.com",
                "subject": f"Simulated Ingest: {filename}",
                "attachment": {
                    "filename": filename,
                    "content_type": "application/pdf" if filename.endswith(".pdf") else "image/jpeg"
                }
            }

        logger.info(f"API Triggered processing for file: {filename}")
        
        # Step 1: Processing
        extraction, parse_success = process_document(file_path)

        # Step 2: Save individual JSON
        extraction_out_path = OUTPUT_DIR / f"{Path(filename).stem}_extracted.json"
        try:
            with open(extraction_out_path, "w", encoding="utf-8") as f:
                json.dump(extraction.model_dump(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write single extraction file: {str(e)}")

        # Step 3: Routing
        routing_outcome = route_document(event, extraction, file_path, parse_success)

        # Step 4: Save to global run log
        append_to_global_routing_log(routing_outcome)

        # Step 5: Send email acknowledgement
        email_status = routing_outcome["status"]

        send_email_acknowledgement(
            vendor_email=event.get("from", "vendor@example.com"),
            vendor_name=extraction.vendor_name,
            invoice_number=extraction.invoice_number,
            total_amount=extraction.total_amount,
            date=extraction.date,
            outcome_status=email_status,
            reason=extraction.reasoning
        )

        return {
            "outcome": routing_outcome,
            "extraction": extraction.model_dump(),
            "event": event
        }

    except Exception as e:
        logger.exception("Exception occurred in API process handler")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Processes file uploads and saves files to sample_documents/."""
    try:
        filename = Path(file.filename).name
        save_path = Path("sample_documents") / filename
        content = await file.read()
        save_path.write_bytes(content)
        logger.info(f"File uploaded and saved to {save_path.resolve()}")

        return {
            "success": True,
            "filename": filename,
            "size_bytes": len(content)
        }
    except Exception as e:
        logger.exception("Exception occurred in API upload handler")
        return JSONResponse(status_code=500, content={"error": str(e)})

class ManualRouteRequest(BaseModel):
    filename: str
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    total_amount: Optional[Any] = None
    document_type: str
    event: Optional[Dict[str, Any]] = None
    route_to: str = "auto"
    status: Optional[str] = None

@app.post("/api/manual_route")
def process_manual_route(payload: ManualRouteRequest):
    """Handles manually adjusted document routing from the human-in-the-loop dashboard form."""
    try:
        filename = payload.filename
        vendor_name = payload.vendor_name
        invoice_number = payload.invoice_number
        total_amount = payload.total_amount
        document_type = payload.document_type
        event = payload.event
        route_to = payload.route_to
        status = payload.status

        # Sanitize filename
        filename = Path(filename).name
        file_path = Path("sample_documents") / filename

        if not event:
            event = {
                "event_id": f"evt_man_{int(time.time())}",
                "received_at": datetime.now().isoformat(),
                "from": "manual_review@acme.com",
                "subject": f"Manual Override: {filename}",
                "attachment": {
                    "filename": filename,
                    "content_type": "application/pdf" if filename.endswith(".pdf") else "image/jpeg"
                }
            }

        # Parse total amount to float
        try:
            total_amount = float(total_amount) if total_amount is not None else None
        except ValueError:
            return JSONResponse(status_code=400, content={"error": "Invalid total amount format"})

        # Construct an InvoiceExtraction model
        reasoning = f"Manually verified and corrected by operator (overrode AI suggestion)."
        extraction = InvoiceExtraction(
            document_type=document_type,
            vendor_name=vendor_name,
            invoice_number=invoice_number,
            date=datetime.now().strftime("%Y-%m-%d"),
            line_items=[],
            total_amount=total_amount,
            confidence_score=1.0,
            reasoning=reasoning
        )

        # Save the manual extraction JSON as individual file
        extraction_out_path = OUTPUT_DIR / f"{Path(filename).stem}_extracted.json"
        try:
            with open(extraction_out_path, "w", encoding="utf-8") as f:
                json.dump(extraction.model_dump(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write manual extraction JSON: {str(e)}")

        # Map route_to to router identifiers
        force_route_to = None
        if route_to == "slack":
            force_route_to = "slack_notification"
        elif route_to == "csv":
            force_route_to = "processed_invoices_csv"
        elif route_to == "human":
            force_route_to = "human_review_log"

        # Route it (success=True because it's human validated)
        routing_success = (document_type != "unknown" and route_to != "human")
        routing_outcome = route_document(event, extraction, file_path, routing_success, force_route_to=force_route_to, force_status=status)

        # Save to global run log
        append_to_global_routing_log(routing_outcome)

        # Send acknowledgement email
        email_status = routing_outcome["status"]
        send_email_acknowledgement(
            vendor_email=event.get("from", "vendor@example.com"),
            vendor_name=extraction.vendor_name,
            invoice_number=extraction.invoice_number,
            total_amount=extraction.total_amount,
            date=extraction.date,
            outcome_status=email_status,
            reason=extraction.reasoning
        )

        return {
            "success": True,
            "outcome": routing_outcome,
            "extraction": extraction.model_dump(),
            "event": event
        }

    except Exception as e:
        logger.exception("Exception occurred in manual route handler")
        return JSONResponse(status_code=500, content={"error": str(e)})

def run():
    # Load dotenv to configure API keys for processing calls
    from dotenv import load_dotenv
    load_dotenv()
    
    logger.info(f"Dashboard Web Server running at http://localhost:{PORT}")
    logger.info("Press Ctrl+C to terminate the server.")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")

if __name__ == "__main__":
    run()
