from __future__ import annotations

import hashlib
import hmac
import os
import re

import phonenumbers


def normalize_identifier(identifier_type: str, identifier: str) -> str:
    value = identifier.strip()
    if identifier_type == "phone":
        try:
            parsed = phonenumbers.parse(value, "GB")
            if phonenumbers.is_possible_number(parsed):
                return phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.E164
                )
        except phonenumbers.NumberParseException:
            pass
        return re.sub(r"[^\d+]", "", value)
    value = value.lower()
    if identifier_type == "email":
        return value
    if identifier_type in ("github", "handle"):
        value = re.sub(r"^https?://", "", value)
        value = re.sub(r"^(www\.)?(github\.com/|x\.com/|twitter\.com/)", "", value)
        return value.lstrip("@").strip("/")
    return value


def identifier_hash(identifier_type: str, identifier: str) -> str:
    pepper = os.getenv("BLOCKLIST_PEPPER", "gatekeeper-dev-pepper-change-me")
    message = f"{identifier_type}:{normalize_identifier(identifier_type, identifier)}"
    return hmac.new(pepper.encode(), message.encode(), hashlib.sha256).hexdigest()
