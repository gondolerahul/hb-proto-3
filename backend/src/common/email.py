import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import logging

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "localhost")
        self.smtp_port = int(os.getenv("SMTP_PORT", "1025"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.smtp_from = os.getenv("SMTP_FROM_EMAIL", "noreply@hirebuddha.com")

    def send_email(self, to_email: str, subject: str, body: str):
        try:
            msg = MIMEMultipart()
            msg["From"] = self.smtp_from
            msg["To"] = to_email
            msg["Subject"] = subject

            msg.attach(MIMEText(body, "html"))

            # Connect to server
            if self.smtp_user and self.smtp_password:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)

            server.send_message(msg)
            server.quit()
            logger.info(f"Email sent to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False

    def send_verification_email(self, to_email: str, token: str):
        subject = "Verify your HireBuddha account"
        # In a real app, this would be a link to the frontend verify page
        verification_link = f"{os.getenv('FRONTEND_URL', 'http://localhost:5173')}/verify-email?token={token}"
        
        body = f"""
        <html>
            <body>
                <h1>Welcome to HireBuddha!</h1>
                <p>Please click the link below to verify your email address:</p>
                <a href="{verification_link}">Verify Email</a>
                <p>If you didn't request this, please ignore this email.</p>
            </body>
        </html>
        """
        return self.send_email(to_email, subject, body)

    def send_dunning_email(self, to_email: str, invoice_id: str, amount: str, attempt: int = 1):
        subject = f"Payment Failed - Action Required (Attempt {attempt})"
        
        urgency_message = ""
        if attempt == 1:
            urgency_message = "We noticed that your recent payment failed. Please update your payment method to continue using HireBuddha."
        elif attempt == 2:
            urgency_message = "This is the second attempt to collect payment. Please update your payment method immediately to avoid service interruption."
        else:
            urgency_message = "URGENT: Multiple payment attempts have failed. Your account may be suspended if payment is not received soon."
        
        body = f"""
        <html>
            <body>
                <h1>Payment Failed</h1>
                <p>{urgency_message}</p>
                <p><strong>Invoice ID:</strong> {invoice_id}</p>
                <p><strong>Amount Due:</strong> ${amount}</p>
                <p>Please log in to your account to update your payment method:</p>
                <a href="{os.getenv('FRONTEND_URL', 'http://localhost:5173')}/billing">Update Payment Method</a>
                <p>If you have any questions, please contact our support team.</p>
            </body>
        </html>
        """
        return self.send_email(to_email, subject, body)

email_service = EmailService()
