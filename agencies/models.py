from django.db import models


class Agency(models.Model):
    name = models.CharField(max_length=255)
    license_number = models.CharField(max_length=100, unique=True)

    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name