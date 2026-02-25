"""
Email AI Agent Tools using IMAP/SMTP.

Provides four tools for AI agents to interact with customer inboxes:
- EmailIngestTool: Monitor and fetch emails via IMAP IDLE
- EmailClassifyTool: Classify emails into folders via IMAP MOVE
- EmailDraftTool: Create draft replies via IMAP APPEND
- EmailSendTool: Send emails via SMTP

All tools require an email_connection_id parameter to identify which
email account credentials to use.
"""
import logging
import json
import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
from typing import Dict, Any, Optional
import os
import re

from src.ai.tools.base import Tool

logger = logging.getLogger(__name__)

# Try to import html2text for HTML sanitization
try:
    import html2text
    HTML2TEXT_AVAILABLE = True
except ImportError:
    HTML2TEXT_AVAILABLE = False
    logger.warning("html2text not installed, HTML emails will use basic fallback stripping")


def _sanitize_html(html_content: str) -> str:
    """Convert HTML email content to clean Markdown/plain text."""
    if HTML2TEXT_AVAILABLE:
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0  # Don't wrap lines
        return h.handle(html_content).strip()
    else:
        # Basic fallback: strip HTML tags
        clean = re.sub(r'<[^>]+>', '', html_content)
        clean = re.sub(r'\s+', ' ', clean)
        return clean.strip()


def _parse_email_body(msg: email.message.Message) -> str:
    """Extract and sanitize email body from MIME message."""
    body = ""
    
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            
            # Skip attachments
            if "attachment" in content_disposition:
                continue
            
            if content_type == "text/plain":
                charset = part.get_content_charset() or "utf-8"
                try:
                    body = part.get_payload(decode=True).decode(charset, errors="replace")
                except Exception:
                    body = str(part.get_payload(decode=True))
                break  # Prefer plain text
            elif content_type == "text/html" and not body:
                charset = part.get_content_charset() or "utf-8"
                try:
                    html = part.get_payload(decode=True).decode(charset, errors="replace")
                    body = _sanitize_html(html)
                except Exception:
                    body = str(part.get_payload(decode=True))
    else:
        content_type = msg.get_content_type()
        charset = msg.get_content_charset() or "utf-8"
        try:
            payload = msg.get_payload(decode=True).decode(charset, errors="replace")
        except Exception:
            payload = str(msg.get_payload(decode=True))
        
        if content_type == "text/html":
            body = _sanitize_html(payload)
        else:
            body = payload
    
    return body


def _get_imap_connection(imap_host: str, imap_port: int, email_address: str, password: str) -> imaplib.IMAP4_SSL:
    """Create and authenticate an IMAP connection."""
    conn = imaplib.IMAP4_SSL(imap_host, imap_port)
    conn.login(email_address, password)
    return conn


def _get_smtp_connection(smtp_host: str, smtp_port: int, email_address: str, password: str) -> smtplib.SMTP:
    """Create and authenticate an SMTP connection."""
    server = smtplib.SMTP(smtp_host, smtp_port)
    server.starttls()
    server.login(email_address, password)
    return server


class EmailIngestTool(Tool):
    """
    Monitor and fetch new emails from an inbox via IMAP.
    
    Fetches the latest email(s), parses MIME content, and returns
    structured data (body, subject, sender, message-id) with 
    HTML sanitized to Markdown.
    """
    name = "email_ingest"
    description = (
        "Fetch and read the latest emails from an inbox. "
        "Input should be a JSON string with: "
        "'imap_host', 'imap_port' (default 993), 'email_address', 'password', "
        "'folder' (default 'INBOX'), 'count' (number of emails to fetch, default 5), "
        "and 'unread_only' (boolean, default true)."
    )

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "imap_host": {"type": "string", "description": "IMAP server hostname (e.g. imap.gmail.com)"},
                    "imap_port": {"type": "integer", "description": "IMAP port (default 993)"},
                    "email_address": {"type": "string", "description": "Email address to connect to"},
                    "password": {"type": "string", "description": "App password for authentication"},
                    "folder": {"type": "string", "description": "IMAP folder to read from (default: INBOX)"},
                    "count": {"type": "integer", "description": "Number of emails to fetch (default: 5)"},
                    "unread_only": {"type": "boolean", "description": "Only fetch unread emails (default: true)"}
                },
                "required": ["imap_host", "email_address", "password"]
            }
        }

    async def run(self, input_data: str) -> str:
        try:
            params = json.loads(input_data)
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON input"})

        imap_host = params.get("imap_host")
        imap_port = params.get("imap_port", 993)
        email_address = params.get("email_address")
        password = params.get("password")
        folder = params.get("folder", "INBOX")
        count = params.get("count", 5)
        unread_only = params.get("unread_only", True)
        
        if not all([imap_host, email_address, password]):
            return json.dumps({"error": "Missing required parameters: imap_host, email_address, password"})

        try:
            conn = _get_imap_connection(imap_host, imap_port, email_address, password)
            conn.select(folder)
            
            # Search for emails
            search_criteria = "UNSEEN" if unread_only else "ALL"
            status, message_ids = conn.search(None, search_criteria)
            
            if status != "OK":
                conn.logout()
                return json.dumps({"error": "Failed to search emails"})
            
            ids = message_ids[0].split()
            if not ids:
                conn.logout()
                return json.dumps({"emails": [], "count": 0, "message": "No emails found"})
            
            # Fetch latest N emails
            latest_ids = ids[-count:]
            emails = []
            
            for uid in reversed(latest_ids):
                status, msg_data = conn.fetch(uid, "(RFC822)")
                if status != "OK":
                    continue
                
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                
                # Parse body
                body = _parse_email_body(msg)
                
                # Truncate very long bodies for AI context
                if len(body) > 5000:
                    body = body[:5000] + "\n\n[... truncated for context window ...]"
                
                # Get attachment info (names only, not content)
                attachments = []
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get("Content-Disposition") and "attachment" in str(part.get("Content-Disposition", "")):
                            filename = part.get_filename() or "unnamed"
                            size = len(part.get_payload(decode=True) or b"")
                            attachments.append({"filename": filename, "size_bytes": size})
                
                emails.append({
                    "uid": uid.decode(),
                    "message_id": msg.get("Message-ID", ""),
                    "from": msg.get("From", ""),
                    "to": msg.get("To", ""),
                    "subject": msg.get("Subject", ""),
                    "date": msg.get("Date", ""),
                    "body": body,
                    "attachments": attachments
                })
            
            conn.logout()
            return json.dumps({"emails": emails, "count": len(emails)})

        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP error: {e}")
            return json.dumps({"error": f"IMAP connection failed: {str(e)}"})
        except Exception as e:
            logger.error(f"Email ingest error: {e}", exc_info=True)
            return json.dumps({"error": f"Email ingest failed: {str(e)}"})


class EmailClassifyTool(Tool):
    """
    Classify emails by moving them to AI-created IMAP folders.
    Reflects classification directly in the user's email client.
    """
    name = "email_classify"
    description = (
        "Classify an email by moving it to an AI-created folder. "
        "Input should be a JSON string with: "
        "'imap_host', 'imap_port', 'email_address', 'password', "
        "'uid' (email UID to classify), 'category' (e.g. 'Refunds', 'Sales'), "
        "and optionally 'source_folder' (default: 'INBOX')."
    )

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "imap_host": {"type": "string"},
                    "imap_port": {"type": "integer"},
                    "email_address": {"type": "string"},
                    "password": {"type": "string"},
                    "uid": {"type": "string", "description": "Email UID to classify"},
                    "category": {"type": "string", "description": "Category name (e.g. 'Refunds', 'Sales')"},
                    "source_folder": {"type": "string", "description": "Source folder (default: INBOX)"}
                },
                "required": ["imap_host", "email_address", "password", "uid", "category"]
            }
        }

    async def run(self, input_data: str) -> str:
        try:
            params = json.loads(input_data)
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON input"})

        imap_host = params.get("imap_host")
        imap_port = params.get("imap_port", 993)
        email_address = params.get("email_address")
        password = params.get("password")
        uid = params.get("uid")
        category = params.get("category")
        source_folder = params.get("source_folder", "INBOX")
        
        if not all([imap_host, email_address, password, uid, category]):
            return json.dumps({"error": "Missing required parameters"})

        try:
            conn = _get_imap_connection(imap_host, imap_port, email_address, password)
            
            # Determine folder prefix based on provider
            folder_prefix = ""
            if "gmail" in imap_host.lower():
                folder_prefix = "[Gmail]/"
            
            target_folder = f"{folder_prefix}AI-Classified/{category}"
            
            # Check if target folder exists, create if not
            status, folder_list = conn.list('', target_folder)
            if status != "OK" or not folder_list or folder_list[0] is None:
                logger.info(f"Creating IMAP folder: {target_folder}")
                conn.create(target_folder)
                conn.subscribe(target_folder)
            
            # Select source folder
            conn.select(source_folder)
            
            # Copy email to target folder
            status, _ = conn.copy(uid, target_folder)
            if status != "OK":
                conn.logout()
                return json.dumps({"error": f"Failed to copy email to {target_folder}"})
            
            # Mark original as deleted and expunge
            conn.store(uid, "+FLAGS", "\\Deleted")
            conn.expunge()
            
            conn.logout()
            return json.dumps({
                "success": True,
                "uid": uid,
                "moved_to": target_folder,
                "category": category
            })

        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP classify error: {e}")
            return json.dumps({"error": f"Email classification failed: {str(e)}"})
        except Exception as e:
            logger.error(f"Email classify error: {e}", exc_info=True)
            return json.dumps({"error": f"Classification failed: {str(e)}"})


class EmailDraftTool(Tool):
    """
    Create draft email replies directly in the user's Drafts folder.
    Maintains thread context via In-Reply-To and References headers.
    """
    name = "email_draft"
    description = (
        "Create a draft reply to an email in the user's Drafts folder. "
        "Input should be a JSON string with: "
        "'imap_host', 'imap_port', 'email_address', 'password', "
        "'original_message_id' (Message-ID of the email being replied to), "
        "'draft_body' (the reply text), 'to' (recipient email), "
        "and 'subject' (email subject, usually 'Re: ...')."
    )

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "imap_host": {"type": "string"},
                    "imap_port": {"type": "integer"},
                    "email_address": {"type": "string"},
                    "password": {"type": "string"},
                    "original_message_id": {"type": "string", "description": "Message-ID of the email being replied to"},
                    "draft_body": {"type": "string", "description": "Body text for the draft reply"},
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject (usually 'Re: original subject')"}
                },
                "required": ["imap_host", "email_address", "password", "original_message_id", "draft_body", "to", "subject"]
            }
        }

    async def run(self, input_data: str) -> str:
        try:
            params = json.loads(input_data)
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON input"})

        imap_host = params.get("imap_host")
        imap_port = params.get("imap_port", 993)
        email_address = params.get("email_address")
        password = params.get("password")
        original_message_id = params.get("original_message_id")
        draft_body = params.get("draft_body")
        to_addr = params.get("to")
        subject = params.get("subject")
        
        if not all([imap_host, email_address, password, original_message_id, draft_body, to_addr, subject]):
            return json.dumps({"error": "Missing required parameters"})

        try:
            conn = _get_imap_connection(imap_host, imap_port, email_address, password)
            
            # Construct MIME message
            msg = MIMEMultipart("alternative")
            msg["From"] = email_address
            msg["To"] = to_addr
            msg["Subject"] = subject
            msg["Date"] = formatdate(localtime=True)
            msg["Message-ID"] = make_msgid()
            
            # Thread headers - CRUCIAL for maintaining conversation thread
            msg["In-Reply-To"] = original_message_id
            msg["References"] = original_message_id
            
            # Add body (plain text + HTML)
            plain_part = MIMEText(draft_body, "plain", "utf-8")
            html_body = draft_body.replace("\n", "<br>")
            html_part = MIMEText(f"<html><body>{html_body}</body></html>", "html", "utf-8")
            
            msg.attach(plain_part)
            msg.attach(html_part)
            
            # Determine drafts folder
            if "gmail" in imap_host.lower():
                drafts_folder = "[Gmail]/Drafts"
            elif "outlook" in imap_host.lower() or "office365" in imap_host.lower():
                drafts_folder = "Drafts"
            else:
                drafts_folder = "Drafts"
            
            # Append to drafts folder
            status, _ = conn.append(
                drafts_folder,
                "\\Draft",
                None,
                msg.as_bytes()
            )
            
            conn.logout()
            
            if status != "OK":
                return json.dumps({"error": f"Failed to save draft to {drafts_folder}"})
            
            return json.dumps({
                "success": True,
                "draft_saved_to": drafts_folder,
                "to": to_addr,
                "subject": subject,
                "in_reply_to": original_message_id
            })

        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP draft error: {e}")
            return json.dumps({"error": f"Draft creation failed: {str(e)}"})
        except Exception as e:
            logger.error(f"Email draft error: {e}", exc_info=True)
            return json.dumps({"error": f"Draft creation failed: {str(e)}"})


class EmailSendTool(Tool):
    """
    Send emails via SMTP using stored credentials.
    """
    name = "email_send"
    description = (
        "Send an email via SMTP. "
        "Input should be a JSON string with: "
        "'smtp_host', 'smtp_port' (default 587), 'email_address', 'password', "
        "'to' (recipient email), 'subject', and 'body'. "
        "Optionally 'cc' and 'bcc' (comma-separated email addresses)."
    )

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "smtp_host": {"type": "string", "description": "SMTP server hostname (e.g. smtp.gmail.com)"},
                    "smtp_port": {"type": "integer", "description": "SMTP port (default 587)"},
                    "email_address": {"type": "string", "description": "Sender email address"},
                    "password": {"type": "string", "description": "App password for SMTP authentication"},
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body text"},
                    "cc": {"type": "string", "description": "CC recipients (comma-separated)"},
                    "bcc": {"type": "string", "description": "BCC recipients (comma-separated)"}
                },
                "required": ["smtp_host", "email_address", "password", "to", "subject", "body"]
            }
        }

    async def run(self, input_data: str) -> str:
        try:
            params = json.loads(input_data)
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON input"})

        smtp_host = params.get("smtp_host")
        smtp_port = params.get("smtp_port", 587)
        email_address = params.get("email_address")
        password = params.get("password")
        to_addr = params.get("to")
        subject = params.get("subject")
        body = params.get("body")
        cc = params.get("cc", "")
        bcc = params.get("bcc", "")
        
        if not all([smtp_host, email_address, password, to_addr, subject, body]):
            return json.dumps({"error": "Missing required parameters"})

        try:
            # Construct message
            msg = MIMEMultipart("alternative")
            msg["From"] = email_address
            msg["To"] = to_addr
            msg["Subject"] = subject
            msg["Date"] = formatdate(localtime=True)
            msg["Message-ID"] = make_msgid()
            
            if cc:
                msg["Cc"] = cc
            
            # Add body
            plain_part = MIMEText(body, "plain", "utf-8")
            html_body = body.replace("\n", "<br>")
            html_part = MIMEText(f"<html><body>{html_body}</body></html>", "html", "utf-8")
            msg.attach(plain_part)
            msg.attach(html_part)
            
            # Build recipient list
            recipients = [to_addr]
            if cc:
                recipients.extend([a.strip() for a in cc.split(",")])
            if bcc:
                recipients.extend([a.strip() for a in bcc.split(",")])
            
            # Send via SMTP
            server = _get_smtp_connection(smtp_host, smtp_port, email_address, password)
            server.send_message(msg, from_addr=email_address, to_addrs=recipients)
            server.quit()
            
            logger.info(f"Email sent: {email_address} -> {to_addr}, subject: {subject}")
            
            return json.dumps({
                "success": True,
                "from": email_address,
                "to": to_addr,
                "subject": subject,
                "cc": cc,
                "message_id": msg["Message-ID"]
            })

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP auth error: {e}")
            return json.dumps({"error": "SMTP authentication failed. Check email/password (use App Password for Gmail)."})
        except Exception as e:
            logger.error(f"Email send error: {e}", exc_info=True)
            return json.dumps({"error": f"Email send failed: {str(e)}"})
