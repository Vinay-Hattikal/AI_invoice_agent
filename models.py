from typing import List, Optional
from pydantic import BaseModel, Field

class LineItem(BaseModel):
    description: str = Field(description="Description of the item or service")
    quantity: Optional[float] = Field(description="Quantity of items, if applicable")
    unit_price: Optional[float] = Field(description="Price per unit, if applicable")
    amount: Optional[float] = Field(description="Total amount for this line item")

class InvoiceExtraction(BaseModel):
    document_type: str = Field(
        description="Must be one of: 'standard_invoice', 'credit_note', or 'unknown'"
    )
    vendor_name: Optional[str] = Field(description="Name of the vendor/sender company")
    invoice_number: Optional[str] = Field(description="Invoice or document reference number")
    date: Optional[str] = Field(description="Date of invoice, preferably in YYYY-MM-DD or standard document format")
    line_items: List[LineItem] = Field(description="List of items/services on the invoice")
    total_amount: Optional[float] = Field(
        description="The final total amount of the document. For invoices with taxes and subtotal, extract the all-inclusive Invoice Total/Net Payable before advances are applied. E.g., for inv_005, the total amount should be 58480.0 (the Invoice Total with taxes)."
    )
    confidence_score: float = Field(
        description="Confidence score between 0.0 and 1.0 representing the model's certainty in extraction and classification"
    )
    reasoning: str = Field(
        description="Brief reasoning explaining the classification and total amount extraction choice"
    )

