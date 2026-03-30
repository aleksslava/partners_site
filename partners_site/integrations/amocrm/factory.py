from django.conf import settings
from .client import AmoCRMWrapper

_client = None

def get_amocrm_client() -> AmoCRMWrapper:
    global _client
    if _client is None:
        cfg = settings.AMOCRM  # словарь/объект с параметрами
        _client = AmoCRMWrapper(
            path=cfg["PATH_TO_ENV"],
            amocrm_subdomain=cfg["SUBDOMAIN"],
            amocrm_client_id=cfg["CLIENT_ID"],
            amocrm_client_secret=cfg["CLIENT_SECRET"],
            amocrm_redirect_url=cfg["REDIRECT_URL"],
            amocrm_access_token=cfg.get("ACCESS_TOKEN"),
            amocrm_refresh_token=cfg.get("REFRESH_TOKEN"),
            amocrm_secret_code=cfg.get("SECRET_CODE"),
        )

    return _client
