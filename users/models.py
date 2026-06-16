from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models


class AgencyUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")

        email = self.normalize_email(email)

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        return self.create_user(email, password, **extra_fields)


class AgencyUser(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    agency_name = models.CharField(max_length=255)
    agency_license_number = models.CharField(max_length=100, unique=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    objects = AgencyUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["agency_name", "agency_license_number"]

    def __str__(self):
        return self.agency_name