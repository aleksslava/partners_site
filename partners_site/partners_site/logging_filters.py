import logging
import re

from django.core.exceptions import DisallowedHost


class CleanDisallowedHostFilter(logging.Filter):
    invalid_host_pattern = re.compile(r"Invalid HTTP_HOST header: '([^']+)'")

    def filter(self, record):
        if record.name != "django.security.DisallowedHost":
            return True

        if not self._is_disallowed_host(record):
            return True

        host = self._extract_host(record.getMessage())
        record.levelno = logging.WARNING
        record.levelname = "WARNING"
        record.msg = "Rejected request with invalid HTTP_HOST header: %s"
        record.args = (host or "unknown",)
        record.exc_info = None
        record.exc_text = None
        return True

    def _is_disallowed_host(self, record):
        if not record.exc_info:
            return True

        if not isinstance(record.exc_info, tuple) or len(record.exc_info) < 2:
            return True

        return isinstance(record.exc_info[1], DisallowedHost)

    def _extract_host(self, message):
        match = self.invalid_host_pattern.search(message)
        if not match:
            return None

        return match.group(1)
