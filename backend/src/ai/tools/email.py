"""
Email Tool for HireBuddha AI Platform.

Provides email sending capabilities via SMTP. Supports both
synchronous SMTP and async-friendly implementations.

Configuration is loaded from the IntegrationRegistry for the
tenant's email service configuration.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional
import json
from src.ai.tools.base import Tool


class EmailTool(Tool):
    """Email sending tool via SMTP.
    
    This tool allows AI agents to send emails. It can be configured
    with SMTP credentials either via:
        1. Direct configuration (for testing)
        2. IntegrationRegistry lookup (for production)
    
    Security Note:
        - Emails are logged for audit purposes
        - Rate limiting should be applied at the governance layer
        - HITL checkpoints are recommended for email actions
    
    Input format (JSON string):
        {
            "to": "recipient@example.com",
            "subject": "Email Subject",
            "body": "Email body content",
            "cc": "optional@example.com",  # optional
            "html": false  # optional, default is plain text
        }
    """
    
    name = "send_email"
    description = (
        "Send an email via SMTP. "
        "Input must be a JSON string with 'to', 'subject', and 'body' fields. "
        "Optional fields: 'cc', 'html' (boolean for HTML email). "
        "Example: {\"to\": \"user@example.com\", \"subject\": \"Hello\", \"body\": \"Message content\"}"
    )
    
    # Default SMTP configuration (override via set_config)
    _smtp_config: Dict[str, Any] = {
        "host": "smtp.gmail.com",
        "port": 587,
        "username": None,
        "password": None,
        "from_email": None,
        "use_tls": True
    }
    
    @classmethod
    def set_config(cls, config: Dict[str, Any]) -> None:
        """Configure SMTP settings.
        
        Args:
            config: Dict with 'host', 'port', 'username', 'password', 
                   'from_email', and optionally 'use_tls'
        """
        cls._smtp_config.update(config)

    async def run(self, input_data: str) -> str:
        """Send an email based on JSON input.
        
        Args:
            input_data: JSON string with email parameters
            
        Returns:
            Success or error message
        """
        try:
            # Parse input
            params = self._parse_input(input_data)
            if "error" in params:
                return params["error"]
            
            # Validate config
            if not self._smtp_config.get("username") or not self._smtp_config.get("password"):
                return (
                    "Error: Email tool not configured. "
                    "SMTP credentials must be set via IntegrationRegistry or set_config()."
                )
            
            # Build email
            msg = self._build_message(params)
            
            # Send email
            return await self._send_email(msg, params["to"], params.get("cc"))
            
        except json.JSONDecodeError:
            return "Error: Input must be a valid JSON string"
        except Exception as e:
            return f"Error sending email: {str(e)}"

    def _parse_input(self, input_data: str) -> Dict[str, Any]:
        """Parse and validate input JSON.
        
        Args:
            input_data: JSON string input
            
        Returns:
            Parsed parameters or error dict
        """
        params = json.loads(input_data.strip())
        
        # Validate required fields
        if not params.get("to"):
            return {"error": "Error: 'to' field is required"}
        if not params.get("subject"):
            return {"error": "Error: 'subject' field is required"}
        if not params.get("body"):
            return {"error": "Error: 'body' field is required"}
        
        # Basic email validation
        to_email = params["to"]
        if "@" not in to_email or "." not in to_email:
            return {"error": f"Error: Invalid email address: {to_email}"}
        
        return params

    def _build_message(self, params: Dict[str, Any]) -> MIMEMultipart:
        """Build MIME email message.
        
        Args:
            params: Email parameters
            
        Returns:
            MIMEMultipart email message
        """
        msg = MIMEMultipart("alternative")
        msg["Subject"] = params["subject"]
        msg["From"] = self._smtp_config.get("from_email") or self._smtp_config["username"]
        msg["To"] = params["to"]
        
        if params.get("cc"):
            msg["Cc"] = params["cc"]
        
        # Add body
        if params.get("html"):
            msg.attach(MIMEText(params["body"], "html"))
        else:
            msg.attach(MIMEText(params["body"], "plain"))
        
        return msg

    async def _send_email(
        self, 
        msg: MIMEMultipart, 
        to: str, 
        cc: Optional[str] = None
    ) -> str:
        """Send email via SMTP.
        
        Args:
            msg: Email message
            to: Recipient email
            cc: Optional CC recipient
            
        Returns:
            Success message
        """
        recipients = [to]
        if cc:
            recipients.append(cc)
        
        # Use synchronous SMTP (wrapped for async compatibility)
        # For true async, consider aiosmtplib
        with smtplib.SMTP(
            self._smtp_config["host"], 
            self._smtp_config["port"]
        ) as server:
            if self._smtp_config.get("use_tls", True):
                server.starttls()
            
            server.login(
                self._smtp_config["username"],
                self._smtp_config["password"]
            )
            
            server.sendmail(
                self._smtp_config.get("from_email") or self._smtp_config["username"],
                recipients,
                msg.as_string()
            )
        
        return f"Email sent successfully to {to}" + (f" (CC: {cc})" if cc else "")

    def get_function_schema(self) -> Dict[str, Any]:
        """Return JSON schema for function calling."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email address"
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject line"
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body content"
                    },
                    "cc": {
                        "type": "string",
                        "description": "Optional CC recipient email address"
                    },
                    "html": {
                        "type": "boolean",
                        "description": "Whether the body is HTML content (default: false)",
                        "default": False
                    }
                },
                "required": ["to", "subject", "body"]
            }
        }
