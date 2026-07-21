import base64
import datetime
import requests

from django.conf import settings


MPESA_ENV = getattr(settings, "MPESA_ENV", "sandbox")

BASE_URLS = {
    "sandbox": "https://sandbox.safaricom.co.ke",
    "production": "https://api.safaricom.co.ke",
}

OAUTH_URL = "/oauth/v1/generate?grant_type=client_credentials"
STK_PUSH_URL = "/mpesa/stkpush/v1/processrequest"
STK_QUERY_URL = "/mpesa/stkpushquery/v1/query"


def _base_url():
    return BASE_URLS.get(MPESA_ENV, BASE_URLS["sandbox"])


def get_access_token():
    """Retrieve OAuth access token from Daraja using consumer key/secret.

    Expects settings.MPESA_CONSUMER_KEY and settings.MPESA_CONSUMER_SECRET to be set.
    """
    key = getattr(settings, "MPESA_CONSUMER_KEY", None)
    secret = getattr(settings, "MPESA_CONSUMER_SECRET", None)
    if not key or not secret:
        raise RuntimeError("MPESA consumer key/secret not configured")
    url = _base_url() + OAUTH_URL
    r = requests.get(url, auth=(key, secret), timeout=10)
    r.raise_for_status()
    return r.json().get("access_token")


def stk_push(phone_number: str, amount: int, account_reference: str, transaction_desc: str = "Licence renewal", callback_url: str | None = None):
    """Initiate STK Push (Lipa Na M-Pesa Online).

    phone_number should be in format 2547XXXXXXXX or 07XXXXXXXX - function will normalize to 2547...
    Returns the raw Daraja response as dict.
    """
    token = get_access_token()
    url = _base_url() + STK_PUSH_URL
    shortcode = getattr(settings, "MPESA_SHORTCODE", None)
    passkey = getattr(settings, "MPESA_PASSKEY", None)
    if not shortcode or not passkey:
        raise RuntimeError("MPESA shortcode/passkey not configured")

    pn = phone_number.strip()
    if pn.startswith("0"):
        pn = "254" + pn[1:]
    elif pn.startswith("+"):
        pn = pn[1:]

    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(f"{shortcode}{passkey}{timestamp}".encode()).decode()

    payload = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": pn,
        "PartyB": shortcode,
        "PhoneNumber": pn,
        "CallBackURL": callback_url or getattr(settings, "MPESA_CALLBACK_URL", ""),
        "AccountReference": account_reference,
        "TransactionDesc": transaction_desc,
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.post(url, json=payload, headers=headers, timeout=10)
    if r.status_code != 200:
        raise RuntimeError(f"Daraja STK push failed ({r.status_code}): {r.text}")
    return r.json()


def stk_push_query(shortcode: str, password: str, timestamp: str, checkout_request_id: str):
    """Query the status of an STK Push transaction.

    Returns the raw Daraja response as dict.
    """
    token = get_access_token()
    url = _base_url() + STK_QUERY_URL
    payload = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "CheckoutRequestID": checkout_request_id,
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.post(url, json=payload, headers=headers, timeout=10)
    if r.status_code != 200:
        raise RuntimeError(f"Daraja STK query failed ({r.status_code}): {r.text}")
    return r.json()
