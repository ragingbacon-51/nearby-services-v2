import base64
import os
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
from django.conf import settings


class MpesaError(Exception):
    pass


def configuration():
    if not settings.DEBUG or os.environ.get("MPESA_SANDBOX_ENABLED") != "1":
        raise MpesaError("M-Pesa sandbox checkout is disabled.")
    names = ("MPESA_CONSUMER_KEY", "MPESA_CONSUMER_SECRET", "MPESA_SHORTCODE", "MPESA_PASSKEY", "MPESA_CALLBACK_URL")
    values = {name: os.environ.get(name, "") for name in names}
    if not all(values.values()):
        raise MpesaError("M-Pesa sandbox credentials and callback URL are not configured.")
    url = urlparse(values["MPESA_CALLBACK_URL"])
    if url.scheme != "https" or not url.hostname or url.hostname in ("localhost", "127.0.0.1", "::1"):
        raise MpesaError("M-Pesa requires a public HTTPS callback URL.")
    return values


def _request(method, url, **kwargs):
    try:
        response = requests.request(method, url, timeout=15, **kwargs)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise MpesaError("M-Pesa sandbox request failed or timed out.") from exc
    if not isinstance(data, dict):
        raise MpesaError("M-Pesa sandbox returned an invalid response.")
    return data


def _credentials(config):
    timestamp = datetime.now(ZoneInfo("Africa/Nairobi")).strftime("%Y%m%d%H%M%S")
    raw = config["MPESA_SHORTCODE"] + config["MPESA_PASSKEY"] + timestamp
    password = base64.b64encode(raw.encode("utf-8")).decode("ascii")
    return timestamp, password


def _token(config):
    data = _request("GET", "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials",
                    auth=(config["MPESA_CONSUMER_KEY"], config["MPESA_CONSUMER_SECRET"]))
    token = data.get("access_token")
    if not isinstance(token, str) or not token:
        raise MpesaError("M-Pesa sandbox returned an invalid access token.")
    return token


def start_checkout(config, amount, phone, booking_id):
    timestamp, password = _credentials(config)
    return _request("POST", "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
                    headers={"Authorization": f"Bearer {_token(config)}"},
                    json={"BusinessShortCode": config["MPESA_SHORTCODE"], "Password": password,
                          "Timestamp": timestamp, "TransactionType": "CustomerPayBillOnline",
                          "Amount": amount, "PartyA": phone, "PartyB": config["MPESA_SHORTCODE"],
                          "PhoneNumber": phone, "CallBackURL": config["MPESA_CALLBACK_URL"],
                          "AccountReference": f"BOOK{booking_id}", "TransactionDesc": "Sandbox service payment"})


def query_checkout(config, checkout_id):
    timestamp, password = _credentials(config)
    return _request("POST", "https://sandbox.safaricom.co.ke/mpesa/stkpushquery/v1/query",
                    headers={"Authorization": f"Bearer {_token(config)}"},
                    json={"BusinessShortCode": config["MPESA_SHORTCODE"], "Password": password,
                          "Timestamp": timestamp, "CheckoutRequestID": checkout_id})
