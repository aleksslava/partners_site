from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import User


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username", "first_name", "last_name", "email", "phone",
            "role", "partner_status", "partner_discount", "bonuses",
            "total_buyout", "buyout_per_quater",
            "amo_id_customer", "telegram_id", "amo_id_contact",
        )


class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"
