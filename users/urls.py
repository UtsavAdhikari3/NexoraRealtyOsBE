from django.urls import path
from .views import (
    RegisterView,
    LoginView,
    VerifyLoginOTPView,
    ResendLoginOTPView,
    ThrottledTokenRefreshView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
    LogoutView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("token/refresh/", ThrottledTokenRefreshView.as_view(), name="token_refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path(
        "password-reset/",
        PasswordResetRequestView.as_view(),
        name="password-reset",
    ),
    path(
        "password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path(
        "verify-login-otp/",
        VerifyLoginOTPView.as_view(),
        name="verify-login-otp"
    ),

    path(
        "resend-login-otp/",
        ResendLoginOTPView.as_view(),
        name="resend-login-otp"
    ),
]
