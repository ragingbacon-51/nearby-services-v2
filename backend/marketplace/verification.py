import logging
import os
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    pass


def _call(method, url, headers, payload=None):
    try:
        response = requests.request(method, url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        logger.warning("Verification provider request failed: %s", url.split("/v")[0])
        raise ProviderError("Verification service unavailable. Please try again later.")
    if not isinstance(data, dict):
        raise ProviderError("Verification service returned an invalid response.")
    return data


def _sms_headers():
    key = os.environ.get("ESMS_API_KEY", "")
    if not key:
        raise ProviderError("Phone verification is not configured.")
    if key.startswith("esms_test_") and not settings.DEBUG:
        raise ProviderError("A test SMS key cannot be used outside development.")
    return {"Authorization": f"Bearer {key}"}


def start_phone(phone):
    app_id = os.environ.get("ESMS_VERIFY_APP_ID", "")
    if not app_id:
        raise ProviderError("Phone verification is not configured.")
    return _call("POST", "https://sms.esmsafrica.io/v1/verify/start", _sms_headers(),
                 {"to": phone, "app_id": app_id})


def check_phone(verification_id, code):
    return _call("POST", "https://sms.esmsafrica.io/v1/verify/check", _sms_headers(),
                 {"verification_id": verification_id, "code": code})


def _identity_headers():
    key = os.environ.get("DIDIT_API_KEY", "")
    if not key:
        raise ProviderError("Identity verification is not configured.")
    return {"x-api-key": key}


def start_identity(user):
    workflow = os.environ.get("DIDIT_WORKFLOW_ID", "")
    if not workflow:
        raise ProviderError("Identity verification is not configured.")
    return _call("POST", "https://verification.didit.me/v3/session/", _identity_headers(), {
        "workflow_id": workflow, "vendor_data": str(user.pk),
        "expected_details": {"first_name": user.first_name, "last_name": user.last_name},
    })


def identity_decision(session_id):
    return _call("GET", f"https://verification.didit.me/v3/session/{session_id}/decision/", _identity_headers())


def identity_approved(decision, user):
    if decision.get("status") != "Approved":
        return False
    for key in ("id_verifications", "liveness_checks", "face_matches", "database_validations"):
        checks = decision.get(key)
        if not isinstance(checks, list) or not checks or any(
            not isinstance(check, dict) or check.get("status") != "Approved" for check in checks
        ):
            return False
    for report in decision["database_validations"]:
        if report.get("issuing_state") != "KEN" or report.get("match_type") != "full_match" or report.get("errors"):
            continue
        results = report.get("validations")
        if not isinstance(results, list):
            continue
        for result in results:
            if not isinstance(result, dict):
                continue
            source = result.get("source_data")
            if not isinstance(source, dict):
                continue
            if (result.get("service_id") == "ken_national_id" and result.get("outcome_code") == "MATCH"
                    and str(source.get("first_name", "")).strip().casefold() == user.first_name.strip().casefold()
                    and str(source.get("last_name", "")).strip().casefold() == user.last_name.strip().casefold()):
                return True
    return False
