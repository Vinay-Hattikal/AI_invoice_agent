import os
import json
import logging
import sys
import time
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
from datetime import datetime
from typing import Any


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
from router import route_document, append_to_global_routing_log, ROUTING_LOG_PATH, OUTPUT_DIR
from notifier import send_email_acknowledgement

PORT = 8000

def parse_multipart(body: bytes, boundary: bytes):
    """Parses multipart/form-data body to extract filename and bytes without external libraries."""
    parts = body.split(b'--' + boundary)
    for part in parts:
        if b'Content-Disposition' in part and b'filename=' in part:
            header_end = part.find(b'\r\n\r\n')
            if header_end != -1:
                headers = part[:header_end]
                file_bytes = part[header_end+4:]
                
                # Clean trailing boundary formatting
                if file_bytes.endswith(b'\r\n'):
                    file_bytes = file_bytes[:-2]
                if file_bytes.endswith(b'\r\n--'):
                    file_bytes = file_bytes[:-4]
                if file_bytes.endswith(b'--\r\n'):
                    file_bytes = file_bytes[:-4]
                
                # Extract filename
                filename_idx = headers.find(b'filename=')
                if filename_idx != -1:
                    filename_val = headers[filename_idx+9:]
                    quote = filename_val[0:1]
                    if quote in [b'"', b"'"]:
                        end_quote = filename_val.find(quote, 1)
                        filename = filename_val[1:end_quote].decode('utf-8')
                    else:
                        end_space = filename_val.find(b'\r')
                        filename = filename_val[:end_space].decode('utf-8')
                    return filename, file_bytes
    return None, None

class DashboardAPIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Override to log via python logging rather than writing raw stderr
        logger.info("%s - - %s" % (self.address_string(), format%args))

    def serve_file(self, filename: str, content_type: str):
        file_path = Path(filename)
        if not file_path.exists():
            self.send_error(404, f"File {filename} not found")
            return
        
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        
        # Read and serve the file
        self.wfile.write(file_path.read_bytes())

    def get_logs(self):
        """Returns the content of routing_log.json."""
        if not ROUTING_LOG_PATH.exists() or ROUTING_LOG_PATH.stat().st_size == 0:
            self.send_json_response([])
            return

        try:
            with open(ROUTING_LOG_PATH, "r", encoding="utf-8") as f:
                logs = json.load(f)
            self.send_json_response(logs)
        except Exception as e:
            logger.error(f"Error loading routing log: {str(e)}")
            self.send_json_response({"error": "Failed to parse routing log JSON"}, status=500)

    def get_extractions(self):
        """Lists files in the sample_documents folder available for simulation."""
        docs_dir = Path("sample_documents")
        if not docs_dir.exists():
            self.send_json_response([])
            return
        
        # Get all PDFs and JPGs
        files = []
        for p in docs_dir.iterdir():
            if p.is_file() and p.suffix.lower() in [".pdf", ".jpg", ".jpeg", ".png"]:
                if p.name != "webhook_payload.json":
                    files.append({
                        "filename": p.name,
                        "size_bytes": p.stat().st_size,
                        "extension": p.suffix.lower()
                    })
        # Sort files by name
        files.sort(key=lambda x: x["filename"])
        self.send_json_response(files)

    def get_single_extraction(self, filename: str):
        """Reads the individual JSON extraction file from output folder."""
        # Sanitize filename
        safe_name = Path(filename).name
        stem = Path(safe_name).stem
        extraction_path = OUTPUT_DIR / f"{stem}_extracted.json"
        
        if not extraction_path.exists():
            self.send_json_response({"error": "Extraction file not found"}, status=404)
            return

        try:
            with open(extraction_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.send_json_response(data)
        except Exception as e:
            logger.error(f"Failed to read extraction JSON for {safe_name}: {str(e)}")
            self.send_json_response({"error": str(e)}, status=500)

    def get_review_data(self, filename: str):
        """Returns outcome, extraction, and event for review/re-routing."""
        # Sanitize filename
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
            
        self.send_json_response({
            "outcome": outcome,
            "extraction": extraction,
            "event": event
        })

    def process_document_request(self):
        """Triggers document processing, routing, and notifications live."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self.send_json_response({"error": "Missing post body"}, status=400)
                return

            post_data = self.rfile.read(content_length)
            body = json.loads(post_data.decode("utf-8"))
            filename = body.get("filename")

            if not filename:
                self.send_json_response({"error": "Missing 'filename' parameter in request"}, status=400)
                return

            # Sanitize filename
            filename = Path(filename).name
            file_path = Path("sample_documents") / filename

            if not file_path.exists():
                self.send_json_response({"error": f"File '{filename}' does not exist in sample_documents"}, status=404)
                return

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
            email_status = "success"
            if routing_outcome["status"] == "failed":
                email_status = "failed"
            elif routing_outcome["status"] == "partial" or extraction.document_type == "unknown":
                email_status = "partial"

            send_email_acknowledgement(
                vendor_email=event.get("from", "vendor@example.com"),
                vendor_name=extraction.vendor_name,
                invoice_number=extraction.invoice_number,
                total_amount=extraction.total_amount,
                date=extraction.date,
                outcome_status=email_status,
                reason=extraction.reasoning
            )

            # Return success response with details
            response_data = {
                "outcome": routing_outcome,
                "extraction": extraction.model_dump(),
                "event": event
            }
            self.send_json_response(response_data)

        except Exception as e:
            logger.exception("Exception occurred in API process handler")
            self.send_json_response({"error": str(e)}, status=500)

    def process_upload_request(self):
        """Processes multipart file uploads and saves files to sample_documents/."""
        try:
            content_type = self.headers.get("Content-Type")
            if not content_type or "multipart/form-data" not in content_type:
                self.send_json_response({"error": "Unsupported Content-Type. Must be multipart/form-data"}, status=400)
                return

            # Extract boundary
            boundary = None
            for param in content_type.split(";"):
                if "boundary=" in param:
                    boundary = param.split("=")[1].strip().encode('utf-8')
                    break
            
            if not boundary:
                self.send_json_response({"error": "Boundary not found in Content-Type"}, status=400)
                return

            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self.send_json_response({"error": "Missing post body"}, status=400)
                return

            post_data = self.rfile.read(content_length)
            
            filename, file_bytes = parse_multipart(post_data, boundary)
            if not filename or not file_bytes:
                self.send_json_response({"error": "Failed to parse file from multipart request"}, status=400)
                return

            # Save the file to sample_documents/ folder
            save_path = Path("sample_documents") / filename
            save_path.write_bytes(file_bytes)
            logger.info(f"File uploaded and saved to {save_path.resolve()}")

            self.send_json_response({
                "success": True,
                "filename": filename,
                "size_bytes": len(file_bytes)
            })

        except Exception as e:
            logger.exception("Exception occurred in API upload handler")
            self.send_json_response({"error": str(e)}, status=500)

    def process_manual_route(self):
        """Handles manually adjusted document routing from the human-in-the-loop dashboard form."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self.send_json_response({"error": "Missing post body"}, status=400)
                return

            post_data = self.rfile.read(content_length)
            body = json.loads(post_data.decode("utf-8"))
            
            filename = body.get("filename")
            vendor_name = body.get("vendor_name")
            invoice_number = body.get("invoice_number")
            total_amount = body.get("total_amount")
            document_type = body.get("document_type")
            event = body.get("event")
            route_to = body.get("route_to", "auto")
            status = body.get("status")

            if not filename:
                self.send_json_response({"error": "Missing 'filename' parameter in request"}, status=400)
                return

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
                self.send_json_response({"error": "Invalid total amount format"}, status=400)
                return

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

            self.send_json_response({
                "success": True,
                "outcome": routing_outcome,
                "extraction": extraction.model_dump(),
                "event": event
            })

        except Exception as e:
            logger.exception("Exception occurred in manual route handler")
            self.send_json_response({"error": str(e)}, status=500)

    def send_json_response(self, data: Any, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def do_OPTIONS(self):
        # Support CORS preflight
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        url_parsed = urllib.parse.urlparse(self.path)
        path = url_parsed.path
        
        if path == "/":
            self.serve_file("index.html", "text/html")
        elif path == "/index.css":
            self.serve_file("index.css", "text/css")
        elif path == "/index.js":
            self.serve_file("index.js", "application/javascript")
        elif path == "/api/logs":
            self.get_logs()
        elif path == "/api/extractions":
            self.get_extractions()
        elif path.startswith("/api/extraction/"):
            filename = path.replace("/api/extraction/", "")
            # Decode url encoded filename
            filename = urllib.parse.unquote(filename)
            self.get_single_extraction(filename)
        elif path.startswith("/api/review/"):
            filename = path.replace("/api/review/", "")
            # Decode url encoded filename
            filename = urllib.parse.unquote(filename)
            self.get_review_data(filename)
        else:
            self.send_error(404, "File Not Found")
            
    def do_POST(self):
        url_parsed = urllib.parse.urlparse(self.path)
        path = url_parsed.path
        if path == "/api/process":
            self.process_document_request()
        elif path == "/api/upload":
            self.process_upload_request()
        elif path == "/api/manual_route":
            self.process_manual_route()
        else:
            self.send_error(404, "Endpoint Not Found")

def run():
    # Load dotenv to configure API keys for processing calls
    from dotenv import load_dotenv
    load_dotenv()
    
    server_address = ("", PORT)
    httpd = HTTPServer(server_address, DashboardAPIHandler)
    logger.info(f"Dashboard Web Server running at http://localhost:{PORT}")
    logger.info("Press Ctrl+C to terminate the server.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server shutting down.")
        httpd.server_close()

if __name__ == "__main__":
    run()
