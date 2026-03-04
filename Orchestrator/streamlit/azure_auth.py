"""
SPM Dashboard — Azure AD SSO via MSAL

Legge la configurazione da variabili d'ambiente:
  AZURE_TENANT_ID     — tenant ID (es. fae8df93-...)
  AZURE_CLIENT_ID     — client ID dell'app registration SPM
  AZURE_CLIENT_SECRET — client secret
  AZURE_REDIRECT_URI  — URI di redirect registrato (es. http://10.172.2.22:8501)
"""

import os
from dotenv import load_dotenv
import msal

load_dotenv()

TENANT_ID    = os.environ.get("AZURE_TENANT_ID", "")
CLIENT_ID    = os.environ.get("AZURE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET", "")
REDIRECT_URI = os.environ.get("AZURE_REDIRECT_URI", "http://10.172.2.22:8501")

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES    = ["User.Read"]


def is_configured() -> bool:
    return bool(TENANT_ID and CLIENT_ID and CLIENT_SECRET)


def _build_app() -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
    )


def get_auth_url() -> str:
    """Genera URL di login Microsoft."""
    return _build_app().get_authorization_request_url(
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )


def exchange_code(code: str) -> dict:
    """
    Scambia il codice di autorizzazione con i token.
    Ritorna il result MSAL (contiene 'access_token' se OK, 'error' se fallisce).
    """
    return _build_app().acquire_token_by_authorization_code(
        code,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )


def get_user_info(result: dict) -> dict:
    """
    Estrae le info utente dall'id_token_claims.
    Ritorna {upn, display_name}.
    """
    claims = result.get("id_token_claims") or {}
    return {
        "upn":          claims.get("preferred_username") or claims.get("upn", ""),
        "display_name": claims.get("name", ""),
    }
