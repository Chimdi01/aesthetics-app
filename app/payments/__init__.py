"""
Provider-agnostic payments: Stripe Connect (UK/Europe now, US and parts
of South America eventually) and Flutterwave (Africa) sit behind this
package rather than being called directly from routers — see CLAUDE.md's
Payments convention. Nothing in here calls a real processor SDK yet
(see app/payments/payment_provider.py's module docstring for why); this
is the skeleton — models, the provider-selection config, and a webhook
receipt endpoint that deliberately refuses to process anything until a
real signing secret exists — ready to wire up once it does.
"""
