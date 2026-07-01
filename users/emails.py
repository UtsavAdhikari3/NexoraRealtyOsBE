import secrets

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import EmailOTP


OTP_EXPIRY_MINUTES = 10


def generate_otp_code():
    return "".join(
        secrets.choice("0123456789")
        for _ in range(6)
    )


def send_login_verification_otp(user):
    EmailOTP.objects.filter(
        user=user,
        purpose=EmailOTP.PURPOSE_LOGIN_VERIFICATION,
        is_used=False,
    ).update(
        is_used=True
    )

    otp_code = generate_otp_code()

    expires_at = timezone.now() + timezone.timedelta(
        minutes=OTP_EXPIRY_MINUTES
    )

    EmailOTP.create_otp(
        user=user,
        raw_code=otp_code,
        expires_at=expires_at,
        purpose=EmailOTP.PURPOSE_LOGIN_VERIFICATION,
    )

    subject = "Your Nexora RealtyOS login OTP"

    message = f"""Hi {user.full_name},

Your Nexora RealtyOS login verification code is:

{otp_code}

This code will expire in {OTP_EXPIRY_MINUTES} minutes.

If you did not request this, you can ignore this email.

Thank you,
Nexora RealtyOS
"""

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )