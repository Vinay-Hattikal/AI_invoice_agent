import os
import csv
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from models import InvoiceExtraction
from notifier import send_slack_notification

logger = logging.getLogger("router")

# Define output file paths in the sample_output/ directory
OUTPUT_DIR = Path("sample_output")
CSV_PATH = OUTPUT_DIR / "processed_invoices.csv"
HUMAN_REVIEW_PATH = OUTPUT_DIR / "human_review.log"
ROUTING_LOG_PATH = OUTPUT_DIR / "routing_log.json"

def init_output_files():
    """Ensure sample_output/ directory and log files exist with correct headers."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Initialize CSV header if not exists
    if not CSV_PATH.exists():
        with open(CSV_PATH, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "event_id", 
                "timestamp", 
                "vendor_name", 
                "invoice_number", 
                "date", 
                "total_amount", 
                "document_type", 
                "attachment_file"
            ])
            
    # Initialize Human Review log if not exists
    if not HUMAN_REVIEW_PATH.exists():
        with open(HUMAN_REVIEW_PATH, mode="w", encoding="utf-8") as f:
            f.write(f"=== HUMAN REVIEW LOG (Initialized: {datetime.now().isoformat()}) ===\n")


def route_document(event: Dict[str, Any], extraction: InvoiceExtraction, file_path: Path, success: bool, force_route_to: Optional[str] = None, force_status: Optional[str] = None) -> Dict[str, Any]:
    """
    Applies the routing rules based on total amount and document classification,
    supporting manual human override targets.
    
    Rules:
      - If force_route_to is 'human_review_log' OR extraction failed OR classified as 'unknown':
        Write to human_review.log.
      - If force_route_to is 'slack_notification' OR (not forced and total_amount > Rs. 50,000):
        Trigger Slack channel notification.
      - If force_route_to is 'processed_invoices_csv' OR (not forced and total_amount <= Rs. 50,000):
        Append a row to local CSV file.
        
    Returns:
        Dict[str, Any]: A dictionary outlining routing outcome details.
    """
    init_output_files()
    
    event_id = event.get("event_id", "unknown_evt")
    received_at = event.get("received_at", datetime.now().isoformat())
    filename = file_path.name

    outcome = {
        "event_id": event_id,
        "filename": filename,
        "document_type": extraction.document_type,
        "total_amount": extraction.total_amount,
        "status": "success" if success else "failed",
        "routed_to": "",
        "reason": extraction.reasoning
    }

    # Case 1: Human review forced, extraction failed, or classified as 'unknown'
    if force_route_to == "human_review_log" or not success or extraction.document_type == "unknown":
        outcome["status"] = "failed" if not success else "partial"
        outcome["routed_to"] = "human_review_log"
        
        # Log to human review file
        log_entry = (
            f"[{datetime.now().isoformat()}] [EVENT: {event_id}] [FILE: {filename}]\n"
            f"Reason for review: {extraction.reasoning or 'Extraction failed or document classified as unknown'}\n"
            f"Draft Data: Vendor={extraction.vendor_name}, Inv#={extraction.invoice_number}, Total={extraction.total_amount}\n"
            f"--------------------------------------------------------------------------------\n"
        )
        with open(HUMAN_REVIEW_PATH, mode="a", encoding="utf-8") as f:
            f.write(log_entry)
            
        logger.info(f"Routed event {event_id} ({filename}) to HUMAN REVIEW log.")
        return outcome

    # Case 2: Document classified as invoice or credit note
    total = extraction.total_amount
    check_total = total if total is not None else 0.0

    # Determine destination
    destination = force_route_to
    if not destination or destination == "auto":
        destination = "slack_notification" if check_total > 50000.0 else "processed_invoices_csv"

    # Rule: Slack Routing
    if destination == "slack_notification":
        outcome["routed_to"] = "slack_notification"
        slack_success = send_slack_notification(
            vendor_name=extraction.vendor_name,
            invoice_number=extraction.invoice_number,
            total_amount=check_total,
            date=extraction.date,
            reasoning=extraction.reasoning
        )
        if not slack_success:
            outcome["status"] = "partial"
            outcome["reason"] = f"Slack webhook post failed. {extraction.reasoning}"
            logger.warning(f"Event {event_id} routed to Slack but webhook call failed.")
        else:
            logger.info(f"Routed event {event_id} ({filename}) to SLACK (Total: Rs. {check_total:,.2f}).")

    # Rule: CSV Sheets Routing
    else:
        outcome["routed_to"] = "processed_invoices_csv"
        try:
            with open(CSV_PATH, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    event_id,
                    received_at,
                    extraction.vendor_name or "",
                    extraction.invoice_number or "",
                    extraction.date or "",
                    check_total,
                    extraction.document_type,
                    filename
                ])
            logger.info(f"Routed event {event_id} ({filename}) to CSV (Total: Rs. {check_total:,.2f}).")
        except Exception as e:
            logger.exception(f"Failed to append event {event_id} to CSV file.")
            outcome["status"] = "partial"
            outcome["reason"] = f"Failed writing to CSV. {str(e)}"
            outcome["routed_to"] = "processed_invoices_csv (failed write)"

    if force_status:
        outcome["status"] = force_status

    return outcome


def append_to_global_routing_log(outcome: Dict[str, Any]):
    """Appends/updates the operational routing run log json."""
    init_output_files()
    
    routing_logs = []
    if ROUTING_LOG_PATH.exists() and ROUTING_LOG_PATH.stat().st_size > 0:
        try:
            with open(ROUTING_LOG_PATH, "r", encoding="utf-8") as f:
                routing_logs = json.load(f)
        except Exception:
            logger.warning("Routing log was corrupted, rewriting.")
            routing_logs = []

    # Update or append
    existing_idx = next((i for i, log in enumerate(routing_logs) if log["event_id"] == outcome["event_id"]), None)
    if existing_idx is not None:
        routing_logs[existing_idx] = outcome
    else:
        routing_logs.append(outcome)

    with open(ROUTING_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(routing_logs, f, indent=2)
