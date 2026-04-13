from django.db import models


class AmoCRMToken(models.Model):
    access_token = models.TextField()
    refresh_token = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AmoCRM токен"
        verbose_name_plural = "AmoCRM токены"

    def __str__(self):
        return f"AmoCRM токен (обновлён {self.updated_at})"
