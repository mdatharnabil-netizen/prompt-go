"""
Easy Press - Stage 1 starter
Answers customer messages on a Facebook Page using the shop's own info.

Setup:
  pip install flask requests anthropic
  Set these environment variables (never put secrets in the code):
    ANTHROPIC_API_KEY   your Claude API key
    PAGE_ACCESS_TOKEN   from your Meta app (Messenger > Generate token)
    VERIFY_TOKEN        any secret word you choose (also enter it in Meta webhook setup)
    APP_SECRET          Meta app secret (used to check messages really come from Meta)
  Run:  python app.py   (use a tunnel like ngrok to give Meta a public https URL)
"""
import hashlib
import hmac
import os

import anthropic
import requests
from flask import Flask, request

app = Flask(__name__)
client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY

PAGE_ACCESS_TOKEN = os.environ["PAGE_ACCESS_TOKEN"]
VERIFY_TOKEN = os.environ["VERIFY_TOKEN"]
APP_SECRET = os.environ["APP_SECRET"]
MODEL = "claude-sonnet-5-5"  # change if needed
GRAPH_URL = "https://graph.facebook.com/v21.0/me/messages"  # check Meta docs for the latest version

# ---- Shop data: replace with a real shop's info (later: load from a database) ----
SHOP = {
    "name": "Demo Shop",
    "products": [
        {"name": "Cotton T-shirt", "price": "450 BDT", "sizes": "M, L, XL", "stock": "in stock"},
        {"name": "Denim Jacket", "price": "1800 BDT", "sizes": "L, XL", "stock": "out of stock"},
    ],
    "delivery": "Dhaka: 60 BDT, 1-2 days. Outside Dhaka: 120 BDT, 3-5 days.",
    "returns": "Exchange within 3 days if the product is unused.",
    "payment": "bKash or Nagad. Customer sends the transaction ID; the owner confirms.",
}

SYSTEM_PROMPT = f"""You are the customer assistant for {SHOP['name']} on Facebook Messenger.
Reply in the same language the customer uses (Bangla, English, or a mix). Be short, friendly, clear.

Use ONLY this shop information. Never invent prices, stock, or policies:
Products: {SHOP['products']}
Delivery: {SHOP['delivery']}
Returns: {SHOP['returns']}
Payment: {SHOP['payment']}

To take an order, ask for these one at a time: product, size, quantity, name, phone, full address.
When you have everything, repeat the order as a summary and ask the customer to confirm.
Never say a payment is confirmed. Say the owner will confirm it.

If you are not sure, or the customer has a complaint, refund request, custom order, or is angry,
start your reply with [HANDOFF] and tell them the owner will reply soon."""

# Simple in-memory chat history per customer (use a database in the real version)
history = {}


def ask_claude(sender_id, text):
    msgs = history.setdefault(sender_id, [])
    msgs.append({"role": "user", "content": text})
    del msgs[:-12]  # keep the last 12 messages
    resp = client.messages.create(
        model=MODEL, max_tokens=500, system=SYSTEM_PROMPT, messages=msgs
    )
    reply = resp.content[0].text
    msgs.append({"role": "assistant", "content": reply})
    return reply


def send_message(recipient_id, text):
    requests.post(
        GRAPH_URL,
        params={"access_token": PAGE_ACCESS_TOKEN},
        json={"recipient": {"id": recipient_id}, "message": {"text": text}, "messaging_type": "RESPONSE"},
        timeout=15,
    )


def notify_owner(sender_id, text):
    # Stage 1: just print. Later: email / Telegram / Messenger notification to the owner.
    print(f"[OWNER ALERT] Customer {sender_id} needs you: {text}")


def valid_signature(req):
    sig = req.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(APP_SECRET.encode(), req.get_data(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


@app.get("/webhook")
def verify():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge", ""), 200
    return "Forbidden", 403


@app.post("/webhook")
def receive():
    if not valid_signature(request):
        return "Bad signature", 403
    data = request.get_json(silent=True) or {}
    for entry in data.get("entry", []):
        for event in entry.get("messaging", []):
            msg = event.get("message", {})
            sender = event.get("sender", {}).get("id")
            if not sender or msg.get("is_echo"):
                continue
            text = msg.get("text")
            if not text:
                # Images/screenshots come in Stage 4
                send_message(sender, "Thanks! The owner will check your image and reply soon.")
                continue
            reply = ask_claude(sender, text)
            if reply.startswith("[HANDOFF]"):
                notify_owner(sender, text)
                reply = reply.replace("[HANDOFF]", "").strip()
            send_message(sender, reply)
    return "ok", 200


if __name__ == "__main__":
    app.run(port=5000)
