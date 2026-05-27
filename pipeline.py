import os
import json
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv
from document_processor import process_document
from router import route_document, append_to_global_routing_log, OUTPUT_DIR
from notifier import send_email_acknowledgement

# Configure logging to console and a file
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("pipeline_run.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("pipeline")

def run_pipeline(payload_path: str = "sample_documents/webhook_payload.json", docs_dir: str = "sample_documents"):
    """
    Main pipeline orchestrator.
    Loads environment variables, parses the webhook payload, and processes each document.
    """
    # Load environment variables from .env
    load_dotenv()
    
    logger.info("Starting AI automation pipeline...")
    logger.info(f"Loading webhook payload from: {payload_path}")
    
    payload_file = Path(payload_path)
    docs_directory = Path(docs_dir)
    
    # Check if payload_path is actually a single PDF or image file
    if payload_file.suffix.lower() in [".pdf", ".jpg", ".jpeg", ".png"]:
        logger.info(f"Detected single document execution mode for: {payload_file.name}")
        
        # If the file exists directly or in the docs directory, resolve it
        if not payload_file.exists():
            fallback_path = docs_directory / payload_file.name
            if fallback_path.exists():
                payload_file = fallback_path
            else:
                logger.error(f"File not found: {payload_file.name} in current directory or {docs_dir}")
                sys.exit(1)
        
        # Create a single mock event
        import time
        from datetime import datetime
        events = [{
            "event_id": f"evt_cli_{int(time.time())}",
            "received_at": datetime.now().isoformat(),
            "from": "cli_sender@vendor.com",
            "subject": f"CLI Ingest: {payload_file.name}",
            "attachment": {
                "filename": payload_file.name,
                "content_type": "application/pdf" if payload_file.suffix.lower() == ".pdf" else "image/jpeg"
            }
        }]
        # Set docs_directory to folder containing the file so it resolves properly
        docs_directory = payload_file.parent
    else:
        # Standard workflow: loading JSON webhook payload
        if not payload_file.exists():
            logger.error(f"Payload file not found: {payload_path}")
            sys.exit(1)
            
        try:
            with open(payload_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to parse payload JSON: {str(e)}")
            sys.exit(1)
            
        events = data.get("events", [])
    logger.info(f"Found {len(events)} events to process.")
    
    # Ensure the output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    processed_count = 0
    success_count = 0
    
    for event in events:
        event_id = event.get("event_id")
        sender = event.get("from", "unknown_sender")
        subject = event.get("subject", "No Subject")
        attachment = event.get("attachment", {})
        filename = attachment.get("filename")
        
        logger.info(f"--- Processing Event: {event_id} | Sender: {sender} | Attachment: {filename} ---")
        
        if not filename:
            logger.error(f"No attachment filename found for event {event_id}. Skipping.")
            continue
            
        # Resolve the local path of the file
        file_path = docs_directory / filename
        
        # 1. Parsing & Field Extraction via Gemini
        logger.info(f"Parsing and extracting fields from: {file_path}")
        extraction, parse_success = process_document(file_path)
        
        # 2. Save individual extraction JSON for grading/audit purposes
        extraction_out_path = OUTPUT_DIR / f"{Path(filename).stem}_extracted.json"
        try:
            with open(extraction_out_path, "w", encoding="utf-8") as f:
                # Convert Pydantic object to dict/JSON
                json.dump(extraction.model_dump(), f, indent=2)
            logger.info(f"Saved extraction JSON to: {extraction_out_path}")
        except Exception as e:
            logger.error(f"Failed to save extraction JSON: {str(e)}")

        # 3. Conditional Routing
        logger.info("Executing routing rules...")
        routing_outcome = route_document(event, extraction, file_path, parse_success)
        
        # 4. Save to global routing run log
        append_to_global_routing_log(routing_outcome)
        
        # 5. Send Acknowledgement back to Vendor
        logger.info(f"Sending acknowledgement email to {sender}...")
        
        # Determine status representation for vendor email
        email_status = "success"
        if routing_outcome["status"] == "failed":
            email_status = "failed"
        elif routing_outcome["status"] == "partial" or extraction.document_type == "unknown":
            email_status = "partial"
            
        send_email_acknowledgement(
            vendor_email=sender,
            vendor_name=extraction.vendor_name,
            invoice_number=extraction.invoice_number,
            total_amount=extraction.total_amount,
            date=extraction.date,
            outcome_status=email_status,
            reason=extraction.reasoning
        )
        
        processed_count += 1
        if routing_outcome["status"] == "success":
            success_count += 1
            
    logger.info("==================================================")
    logger.info("Pipeline run complete.")
    logger.info(f"Total documents processed: {processed_count}")
    logger.info(f"Successful extractions: {success_count}")
    logger.info(f"Output files stored in: {OUTPUT_DIR.resolve()}")
    logger.info("==================================================")

if __name__ == "__main__":
    payload = "sample_documents/webhook_payload.json"
    docs = "sample_documents"
    
    # Allow overriding payload and docs path via command arguments
    if len(sys.argv) > 1:
        payload = sys.argv[1]
    if len(sys.argv) > 2:
        docs = sys.argv[2]
        
    run_pipeline(payload, docs)
