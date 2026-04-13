import logging

import dotenv
from django.conf import settings

from .client import AmoCRMWrapper

logger = logging.getLogger(__name__)

_client = None


def get_amocrm_client() -> AmoCRMWrapper:
    global _client
    if _client is None:
        cfg = settings.AMOCRM

        from integrations.models import AmoCRMToken

        db_token = AmoCRMToken.objects.filter(pk=1).first()

        if db_token:
            access_token = db_token.access_token
            refresh_token = db_token.refresh_token
            logger.info("AMO tokens loaded from database")
        else:
            # Первый запуск — читаем из env-файла и сохраняем в БД
            env_path = str(cfg["PATH_TO_ENV"])
            env_values = dotenv.dotenv_values(env_path)
            access_token = env_values.get("AMOCRM_ACCESS_TOKEN") or cfg.get("ACCESS_TOKEN")
            refresh_token = env_values.get("AMOCRM_REFRESH_TOKEN") or cfg.get("REFRESH_TOKEN")

            if access_token and refresh_token:
                AmoCRMToken.objects.create(
                    pk=1,
                    access_token=access_token,
                    refresh_token=refresh_token,
                )
                logger.info("AMO tokens seeded from env file into database")
            else:
                logger.warning("AMO tokens not found in env file or settings")

        _client = AmoCRMWrapper(
            amocrm_subdomain=cfg["SUBDOMAIN"],
            amocrm_client_id=cfg["CLIENT_ID"],
            amocrm_client_secret=cfg["CLIENT_SECRET"],
            amocrm_redirect_url=cfg["REDIRECT_URL"],
            amocrm_access_token=access_token,
            amocrm_refresh_token=refresh_token,
            amocrm_secret_code=cfg.get("SECRET_CODE"),
        )

    return _client
