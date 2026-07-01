from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    RegisterView,
    LoginView,
    VerifyLoginOTPView,
    ResendLoginOTPView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
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