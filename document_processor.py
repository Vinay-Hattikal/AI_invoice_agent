import os
import logging
import base64
from pathlib import Path
from typing import Tuple, Dict, Any, Union
import pypdf
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from models import InvoiceExtraction

logger = logging.getLogger("document_processor")

# Global variable to cache the last successful model for fast subsequent pipeline executions
_preferred_model = None

# System prompt outlining required schema structure and extraction instructions
SYSTEM_PROMPT = """
You are an expert AI Document Processor on an operations team.
Analyze the document details (either provided as extracted text or an image attachment) and return a JSON object strictly matching this schema:

{
  "document_type": "Must be one of: 'standard_invoice', 'credit_note', or 'unknown'",
  "vendor_name": "Name of the vendor/sender company or null",
  "invoice_number": "Invoice or document reference number or null",
  "date": "Date of invoice (preferably in YYYY-MM-DD format) or null",
  "line_items": [
    {
      "description": "Description of the item or service",
      "quantity": number or null,
      "unit_price": number or null,
      "amount": number or null
    }
  ],
  "total_amount": number (float) or null,
  "confidence_score": number (float between 0.0 and 1.0 representing certainty),
  "reasoning": "Brief explanation of the classification and total amount extraction choice"
}

CRITICAL RULES:
1. Classify the document as 'standard_invoice', 'credit_note', or 'unknown'.
   - Use 'unknown' if it is not an invoice or credit note, if it is blank, or if critical info (like the total or vendor name) is missing/unreadable.
2. For total_amount, extract the all-inclusive GST-inclusive total invoice amount (before advance payments are deducted).
   - E.g., for Kalyan Electrical Works (inv_005), the subtotal is 49,560, Invoice Total is 58,480, and Net Payable is 48,480. Extract the Invoice Total of 58480.0.
3. Your response must be valid JSON matching the schema fields exactly.
"""

_openrouter_client = None

def setup_openrouter():
    """Configure and return the OpenRouter client using the env key."""
    global _openrouter_client
    if _openrouter_client is not None:
        return _openrouter_client
        
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not set in the environment variables.")
    
    # OpenRouter API behaves identically to OpenAI API when using this base URL
    _openrouter_client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "AI Operations Automation Agent"
        }
    )
    return _openrouter_client

def _should_retry_exception(exception: Exception) -> bool:
    """Filter to prevent retrying on rate limits (429), authentication (401), billing (402), or model issues (404) to enable instant fallback."""
    err_str = str(exception).lower()
    if any(keyword in err_str for keyword in ["429", "401", "404", "402", "payment", "credit", "insufficient", "balance", "billing", "rate_limit", "quota", "unauthorized"]):
        return False
    return True

@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=0.5, min=1, max=3),
    retry=retry_if_exception(_should_retry_exception),
    reraise=True
)
def _call_openrouter_with_retry(client, model_name: str, messages: list) -> str:
    """Invokes OpenRouter chat completions API with JSON response formatting."""
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.1,
        timeout=30
    )
    return response.choices[0].message.content

def create_unknown_extraction(reasoning: str, confidence_score: float = 0.0) -> InvoiceExtraction:
    """Helper to create a fully-compliant InvoiceExtraction schema instance for unknown/failed cases."""
    return InvoiceExtraction(
        document_type="unknown",
        vendor_name=None,
        invoice_number=None,
        date=None,
        line_items=[],
        total_amount=None,
        confidence_score=confidence_score,
        reasoning=reasoning
    )

def process_document(file_path: Union[str, Path]) -> Tuple[InvoiceExtraction, bool]:
    """
    Parses a PDF or image file and extracts structured information using OpenRouter API.
    
    Returns:
        Tuple[InvoiceExtraction, bool]: The extracted data and a boolean indicating if processing was successful.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        return create_unknown_extraction(f"File not found on disk: {file_path.name}"), False

    # Check for empty/zero-byte files
    if file_path.stat().st_size == 0:
        logger.error(f"File is empty: {file_path}")
        return create_unknown_extraction(f"Attachment file is blank or has 0 bytes: {file_path.name}"), False

    try:
        client = setup_openrouter()
    except Exception as e:
        logger.exception("Failed to initialize OpenRouter API client.")
        return create_unknown_extraction(f"OpenRouter client initialization failed: {str(e)}"), False

    suffix = file_path.suffix.lower()
    messages = []

    try:
        # Case A: PDF Document (Extract text content and send as standard prompt)
        if suffix == ".pdf":
            reader = pypdf.PdfReader(file_path)
            extracted_text = ""
            for page in reader.pages:
                extracted_text += page.extract_text() or ""
                
            # Fallback if PDF has no extractable text layer (is scanned)
            if not extracted_text.strip():
                logger.warning(f"PDF {file_path.name} contains no text layer.")
                return create_unknown_extraction(f"Scanned PDF lacks extractable text layer: {file_path.name}"), False

            messages = [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": f"Document Text:\n{extracted_text}"
                }
            ]
            
        # Case B: Image Document (Send image as base64 message block)
        elif suffix in [".jpg", ".jpeg", ".png"]:
            img_bytes = file_path.read_bytes()
            base64_img = base64.b64encode(img_bytes).decode("utf-8")
            mime_type = "image/jpeg" if suffix in [".jpg", ".jpeg"] else "image/png"
            
            messages = [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract attributes from this invoice image."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_img}"
                            }
                        }
                    ]
                }
            ]
        else:
            logger.error(f"Unsupported file format: {suffix}")
            return create_unknown_extraction(f"Unsupported file format: {suffix}"), False
            
    except Exception as e:
        logger.exception(f"Failed to read/parse attachment file: {file_path.name}")
        return create_unknown_extraction(f"Unreadable attachment file: {str(e)}"), False

    # Execute model call with model fallback rotation on OpenRouter
    global _preferred_model
    models_to_try = [
        "google/gemini-2.5-flash",
        "google/gemini-2.5-pro",
        "openai/gpt-4o-mini"
    ]
    
    # Reorder models_to_try so that the last successful model is attempted first
    if _preferred_model and _preferred_model in models_to_try:
        models_to_try.remove(_preferred_model)
        models_to_try.insert(0, _preferred_model)
        
    last_error = None
    response_text = None

    for model_name in models_to_try:
        try:
            logger.info(f"Attempting OpenRouter field extraction using model: {model_name}")
            response_text = _call_openrouter_with_retry(client, model_name, messages)
            if response_text:
                # Successfully received response, save this as the preferred model
                _preferred_model = model_name
                break
        except Exception as e:
            logger.warning(f"Model {model_name} failed on OpenRouter: {str(e)}")
            last_error = e
            continue

    if response_text is None:
        logger.error(f"All OpenRouter models failed for file {file_path.name}. Last error: {str(last_error)}")
        return create_unknown_extraction(f"All OpenRouter models exhausted. Last error: {str(last_error)}"), False

    try:
        # Validate and instantiate the Pydantic model
        extracted_data = InvoiceExtraction.model_validate_json(response_text)
        return extracted_data, True
    except Exception as e:
        logger.exception(f"Failed to validate JSON response from OpenRouter: {response_text}")
        return create_unknown_extraction(f"OpenRouter response validation error: {str(e)}. Raw output: {response_text}"), False
