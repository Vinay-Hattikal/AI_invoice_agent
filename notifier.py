import os
import json
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger("notifier")

def send_slack_notification(vendor_name: str, invoice_number: str, total_amount: float, date: str, reasoning: str) -> bool:
    """
    Sends a formatted high-value invoice notification to Slack.
    Uses the SLACK_WEBHOOK_URL environment variable. Fallbacks to mock console logging if not set.
    """
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    
    # Formatted Slack Message using Block Kit for visual excellence
    slack_payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🚨 High-Value Invoice Alert (> Rs. 50,000)",
                    "emoji": True
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Vendor:*\n{vendor_name or 'N/A'}"},
                    {"type": "mrkdwn", "text": f"*Invoice #:*\n{invoice_number or 'N/A'}"},
                    {"type": "mrkdwn", "text": f"*Total Amount:*\nRs. {total_amount:,.2f}"},
                    {"type": "mrkdwn", "text": f"*Invoice Date:*\n{date or 'N/A'}"}
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Reasoning & Context:*\n{reasoning}"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "⚡ _This message was auto-routed by the AI Operations Agent_"
                    }
                ]
            }
        ]
    }

    if not webhook_url or "your_slack_webhook" in webhook_url:
        logger.info("[MOCK SLACK] Slack Webhook URL not configured. Mocking payload:")
        print(f"\n=== [MOCK SLACK CHANNEL NOTIFICATION] ===")
        print(json.dumps(slack_payload, indent=2))
        print("==========================================\n")
        return True

    def _post_slack():
        try:
            response = requests.post(webhook_url, json=slack_payload, headers={"Content-Type": "application/json"}, timeout=10)
            if response.status_code == 200:
                logger.info("Successfully posted high-value invoice alert to Slack.")
            else:
                logger.error(f"Failed to post to Slack. Status: {response.status_code}, Response: {response.text}")
                # Fallback to console print
                print(f"\n--- [SLACK WEBHOOK ERROR - FALLBACK LOG] ---")
                print(f"Vendor: {vendor_name}, Invoice: {invoice_number}, Total: {total_amount}")
                print("--------------------------------------------\n")
        except Exception:
            logger.exception("Exception occurred while posting to Slack webhook.")

    import threading
    threading.Thread(target=_post_slack, daemon=True).start()
    return True


def send_email_acknowledgement(vendor_email: str, vendor_name: str, invoice_number: str, total_amount: Optional[float], date: str, outcome_status: str, reason: str = "") -> bool:
    """
    Sends an acknowledgement email to the vendor.
    Uses the Resend API using the RESEND_API_KEY environment variable.
    Fallbacks to console logging if the API key is missing or Resend rejects the request.
    """
    resend_key = os.getenv("RESEND_API_KEY")
    sender_email = os.getenv("EMAIL_SENDER", "onboarding@resend.dev")

    # Construct clean email contents
    subject = f"Acknowledgement: Invoice Processing Status [{outcome_status.upper()}]"
    
    amount_str = f"Rs. {total_amount:,.2f}" if total_amount is not None else "N/A"
    
    html_content = f"""
    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
        <h2 style="color: #2b6cb0; border-bottom: 2px solid #2b6cb0; padding-bottom: 10px;">Document Processing Notification</h2>
        <p>Dear Valued Vendor Team,</p>
        <p>This is an automated notification regarding the invoice/document received from your address.</p>
        
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
            <tr style="background-color: #f7fafc;">
                <td style="padding: 10px; border: 1px solid #edf2f7; font-weight: bold;">Vendor Name</td>
                <td style="padding: 10px; border: 1px solid #edf2f7;">{vendor_name or 'Unknown/Unclear'}</td>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #edf2f7; font-weight: bold;">Invoice Number</td>
                <td style="padding: 10px; border: 1px solid #edf2f7;">{invoice_number or 'N/A'}</td>
            </tr>
            <tr style="background-color: #f7fafc;">
                <td style="padding: 10px; border: 1px solid #edf2f7; font-weight: bold;">Date</td>
                <td style="padding: 10px; border: 1px solid #edf2f7;">{date or 'N/A'}</td>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #edf2f7; font-weight: bold;">Total Amount</td>
                <td style="padding: 10px; border: 1px solid #edf2f7;">{amount_str}</td>
            </tr>
            <tr style="background-color: #f7fafc;">
                <td style="padding: 10px; border: 1px solid #edf2f7; font-weight: bold;">Outcome Status</td>
                <td style="padding: 10px; border: 1px solid #edf2f7; font-weight: bold; color: {'#38a169' if outcome_status == 'success' else '#dd6b20' if outcome_status == 'partial' else '#e53e3e'};">{outcome_status.upper()}</td>
            </tr>
        </table>
        
        {f'<div style="background-color: #fffaf0; border-left: 4px solid #dd6b20; padding: 10px; margin-bottom: 20px; font-size: 0.9em; color: #7b341e;"><strong>Details:</strong> {reason}</div>' if reason else ''}
        
        <p style="margin-top: 30px;">If this document was flagged as <strong>FAILED</strong> or <strong>PARTIAL</strong>, our team will review the document manually. No further action is required from your side at this moment.</p>
        
        <hr style="border: 0; border-top: 1px solid #edf2f7; margin: 30px 0;" />
        <p style="font-size: 0.8em; color: #a0aec0; text-align: center;">This is an automated operational response. Please do not reply directly to this email.</p>
    </div>
    """

    # If key is missing or is placeholder, mock it
    if not resend_key or "your_resend_api" in resend_key:
        logger.info("[MOCK EMAIL] Resend API key not configured. Logging mock email acknowledgement:")
        _print_mock_email(vendor_email, sender_email, subject, html_content)
        return True

    def _post_email():
        try:
            # Resend API endpoint
            url = "https://api.resend.com/emails"
            headers = {
                "Authorization": f"Bearer {resend_key}",
                "Content-Type": "application/json"
            }
            
            # Note: Resend Free tier sandbox only allows sending to the registered account email.
            # We will attempt sending to the actual vendor email. If Resend returns 400 (unverified recipient),
            # we will retry sending to the verified email 'onboarding@resend.dev' or print to logs.
            payload = {
                "from": f"AI Ops Agent <{sender_email}>",
                "to": [vendor_email],
                "subject": subject,
                "html": html_content
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 200 or response.status_code == 201:
                logger.info(f"Acknowledgement email successfully sent via Resend to {vendor_email}.")
                return
            elif response.status_code == 403 or response.status_code == 400:
                # Resend sandbox limit: send to onboarding@resend.dev instead or mock
                logger.warning(f"Resend rejected sending to {vendor_email} (likely sandbox unverified domain error {response.status_code}). Retrying sending to verified onboarding address...")
                
                # Change to onboarding email (Resend's default test recipient)
                payload["to"] = ["delivered@resend.dev"] # or onboarding@resend.dev
                payload["subject"] = f"[Redirected Sandbox Test] {subject}"
                
                retry_resp = requests.post(url, json=payload, headers=headers, timeout=10)
                if retry_resp.status_code in [200, 201]:
                    logger.info("Successfully sent sandbox redirected email to Resend verification inbox.")
                    return
                
            logger.error(f"Resend email API failed with status {response.status_code}: {response.text}")
            logger.info("Falling back to mock email logging...")
            _print_mock_email(vendor_email, sender_email, subject, html_content)
            
        except Exception:
            logger.exception("Failed to send email via Resend.")
            _print_mock_email(vendor_email, sender_email, subject, html_content)

    import threading
    threading.Thread(target=_post_email, daemon=True).start()
    return True

def _print_mock_email(to_email: str, from_email: str, subject: str, html_body: str):
    """Helper to display visual mockup of the acknowledgement email in the terminal."""
    print(f"\n==================================================")
    print(f"[MOCK EMAIL SENT TO VENDOR]")

    print(f"From:    {from_email}")
    print(f"To:      {to_email}")
    print(f"Subject: {subject}")
    print(f"--------------------------------------------------")
    # Strip HTML tags for clean console display
    import re
    text_body = re.sub('<[^<]+?>', '', html_body).replace('\n\n', '\n').strip()
    # Simple clean up of spacing
    lines = [line.strip() for line in text_body.split('\n') if line.strip()]
    print("\n".join(lines[:15])) # print first 15 lines of content
    if len(lines) > 15:
        print("... [Truncated for console readability] ...")
    print(f"==================================================\n")
