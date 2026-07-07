from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .services import is_recaptcha_configured


try:
    from django_recaptcha.fields import ReCaptchaField
    from django_recaptcha.widgets import ReCaptchaV2Checkbox
except ImportError:  # pragma: no cover - keeps startup safe if dependency is absent.
    ReCaptchaField = None
    ReCaptchaV2Checkbox = None


class AdaptiveCaptchaAuthenticationForm(AuthenticationForm):
    """
    AuthenticationForm with an optional server-validated reCAPTCHA challenge.
    """

    captcha_unavailable_message = (
        'CAPTCHA verification is not configured. Please contact an administrator.'
    )

    def __init__(self, request=None, *args, require_captcha=False, **kwargs):
        self.require_captcha = bool(require_captcha and is_recaptcha_configured())
        super().__init__(request, *args, **kwargs)

        if not self.require_captcha:
            return

        if ReCaptchaField is None or ReCaptchaV2Checkbox is None:
            self.fields['captcha'] = forms.CharField(
                required=False,
                widget=forms.HiddenInput,
            )
            return

        self.fields['captcha'] = ReCaptchaField(
            label='',
            widget=ReCaptchaV2Checkbox(
                attrs={
                    'data-theme': 'light',
                    'data-size': 'normal',
                }
            ),
            error_messages={
                'required': 'Please complete the CAPTCHA verification.',
                'captcha_invalid': 'CAPTCHA verification failed. Please try again.',
            },
        )

    def clean(self):
        if self.require_captcha and self.errors.get('captcha'):
            return self.cleaned_data
        return super().clean()

    def get_captcha_error_message(self):
        if not self.require_captcha:
            return None

        errors = self.errors.get('captcha')
        if errors:
            return errors[0]

        for error in self.non_field_errors():
            if 'CAPTCHA' in str(error):
                return str(error)
        return None
