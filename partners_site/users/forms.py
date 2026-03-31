from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from .models import User


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username", "first_name", "last_name", "email", "phone",
            "role", "customer",
            "telegram_id", "max_id", "amo_id_contact",
            "is_active", "is_staff",
        )


class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


class CabinetCredentialsForm(forms.Form):
    SYSTEM_USERNAME_PREFIXES = ("tg_", "max_", "amo_")

    new_username = forms.CharField(
        label="Новый логин",
        required=False,
        max_length=150,
    )
    current_password = forms.CharField(
        label="Текущий пароль",
        required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    new_password1 = forms.CharField(
        label="Новый пароль",
        required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    new_password2 = forms.CharField(
        label="Повторите пароль",
        required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, *args, user: User, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.username_validator = UnicodeUsernameValidator()
        self.can_change_username = self._is_system_username(user.username)

        if not self.can_change_username:
            self.fields["new_username"].disabled = True
            self.fields["new_username"].required = False
            self.fields["new_username"].initial = user.username

    def _is_system_username(self, username: str) -> bool:
        normalized = (username or "").lower()
        return normalized.startswith(self.SYSTEM_USERNAME_PREFIXES)

    def clean_new_username(self) -> str:
        value = (self.cleaned_data.get("new_username") or "").strip()

        if not self.can_change_username:
            return self.user.username

        if not value:
            return ""

        self.username_validator(value)

        exists = (
            User.objects
            .exclude(pk=self.user.pk)
            .filter(username=value)
            .exists()
        )
        if exists:
            raise ValidationError("Этот логин уже занят.")

        return value

    def clean(self):
        cleaned_data = super().clean()

        new_username = (cleaned_data.get("new_username") or "").strip()
        current_password = cleaned_data.get("current_password") or ""
        new_password1 = cleaned_data.get("new_password1") or ""
        new_password2 = cleaned_data.get("new_password2") or ""

        username_change_requested = self.can_change_username and bool(new_username) and new_username != self.user.username
        password_change_requested = bool(new_password1 or new_password2)

        if password_change_requested:
            if new_password1 != new_password2:
                self.add_error("new_password2", "Пароли не совпадают.")

            if self.user.has_usable_password():
                if not current_password:
                    self.add_error("current_password", "Введите текущий пароль.")
                elif not self.user.check_password(current_password):
                    self.add_error("current_password", "Текущий пароль введён неверно.")

            if new_password1:
                try:
                    password_validation.validate_password(new_password1, user=self.user)
                except ValidationError as exc:
                    self.add_error("new_password1", exc)

        if current_password and not password_change_requested:
            self.add_error("new_password1", "Введите новый пароль.")

        if not username_change_requested and not password_change_requested:
            raise ValidationError("Введите новый логин или пароль для обновления доступа.")

        cleaned_data["username_change_requested"] = username_change_requested
        cleaned_data["password_change_requested"] = password_change_requested and not self.errors
        return cleaned_data

    def save(self) -> tuple[bool, bool]:
        username_change_requested = bool(self.cleaned_data.get("username_change_requested"))
        password_change_requested = bool(self.cleaned_data.get("password_change_requested"))

        if username_change_requested:
            self.user.username = self.cleaned_data["new_username"]

        if password_change_requested:
            self.user.set_password(self.cleaned_data["new_password1"])

        if username_change_requested or password_change_requested:
            self.user.save()

        return username_change_requested, password_change_requested
