import stripe
from src.common.config import settings
from fastapi import HTTPException

stripe.api_key = settings.STRIPE_SECRET_KEY

class StripeService:
    async def create_customer(self, email: str, name: str, tenant_id: str):
        try:
            customer = stripe.Customer.create(
                email=email,
                name=name,
                metadata={"tenant_id": tenant_id}
            )
            return customer
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=str(e))

    async def create_subscription(self, customer_id: str, price_id: str):
        try:
            subscription = stripe.Subscription.create(
                customer=customer_id,
                items=[{"price": price_id}],
                payment_behavior="default_incomplete",
                payment_settings={"save_default_payment_method": "on_subscription"},
                expand=["latest_invoice.payment_intent"],
            )
            return subscription
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=str(e))

    async def create_payment_intent(self, amount: int, currency: str, customer_id: str):
        try:
            intent = stripe.PaymentIntent.create(
                amount=amount,
                currency=currency,
                customer=customer_id,
                automatic_payment_methods={"enabled": True},
            )
            return intent
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=str(e))

    async def construct_event(self, payload: bytes, sig_header: str):
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
            return event
        except ValueError as e:
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.error.SignatureVerificationError as e:
            raise HTTPException(status_code=400, detail="Invalid signature")

stripe_service = StripeService()
