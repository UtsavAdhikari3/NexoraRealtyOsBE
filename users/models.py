from django.contrib.auth.models import (
    AbstractBaseUser,
    PermissionsMixin,
    BaseUserManager
)
from django.db import models

from agencies.models import Agency
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone

class AgencyUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")

        email = self.normalize_email(email)

        user = self.model(
            email=email,
            **extra_fields
        )

        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_email_verified", True)
        extra_fields.setdefault("role", "super_admin")
        extra_fields.setdefault("agency", None)

        return self.create_user(
            email,
            password,
            **extra_fields
        )


class AgencyUser(AbstractBaseUser, PermissionsMixin):
    ROLE_SUPER_ADMIN = "super_admin"
    ROLE_AGENCY_OWNER = "agency_owner"
    ROLE_AGENCY_MANAGER = "agency_manager"
    ROLE_AGENT = "agent"

    ROLE_CHOICES = [
        (ROLE_SUPER_ADMIN, "Super Admin"),
        (ROLE_AGENCY_OWNER, "Agency Owner"),
        (ROLE_AGENCY_MANAGER, "Agency Manager"),
        (ROLE_AGENT, "Agent"),
    ]

    email = models.EmailField(unique=True)

    agency = models.ForeignKey(
        Agency,
        on_delete=models.CASCADE,
        related_name="users",
        null=True,
        blank=True
    )

    full_name = models.CharField(max_length=255)

    role = models.CharField(
        max_length=50,
        choices=ROLE_CHOICES,
        default=ROLE_AGENCY_OWNER
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    objects = AgencyUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    def __str__(self):
        return self.email
    

class EmailOTP(models.Model):
    PURPOSE_LOGIN_VERIFICATION = "login_verification"

    PURPOSE_CHOICES = [
        (PURPOSE_LOGIN_VERIFICATION, "Login Verification"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_otps"
    )

    code_hash = models.CharField(max_length=255)

    purpose = models.CharField(
        max_length=50,
        choices=PURPOSE_CHOICES,
        default=PURPOSE_LOGIN_VERIFICATION
    )

    expires_at = models.DateTimeField()

    attempts = models.PositiveIntegerField(default=0)

    is_used = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def is_expired(self):
        return timezone.now() > self.expires_at

    def check_code(self, raw_code):
        return check_password(raw_code, self.code_hash)

    @classmethod
    def create_otp(cls, user, raw_code, expires_at, purpose=PURPOSE_LOGIN_VERIFICATION):
        return cls.objects.create(
            user=user,
            code_hash=make_password(raw_code),
            purpose=purpose,
            expires_at=expires_at,
        )

    def __str__(self):
        return f"{self.user.email} - {self.purpose}"