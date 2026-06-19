from django.db import models

from agencies.models import Agency
from users.models import AgencyUser


class Property(models.Model):

    PROPERTY_TYPES = [
        ("house", "House"),
        ("land", "Land"),
        ("apartment", "Apartment"),
        ("commercial", "Commercial"),
    ]

    PURPOSES = [
        ("sale", "Sale"),
        ("rent", "Rent"),
    ]

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("available", "Available"),
        ("sold", "Sold"),
        ("rented", "Rented"),
    ]

    agency = models.ForeignKey(
        Agency,
        on_delete=models.CASCADE,
        related_name="properties"
    )

    assigned_agent = models.ForeignKey(
        AgencyUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    title = models.CharField(max_length=255)

    property_type = models.CharField(
        max_length=50,
        choices=PROPERTY_TYPES
    )

    purpose = models.CharField(
        max_length=50,
        choices=PURPOSES
    )

    price = models.DecimalField(
        max_digits=15,
        decimal_places=2
    )

    province = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    city = models.CharField(max_length=100)

    address = models.TextField(blank=True)

    bedrooms = models.IntegerField(default=0)
    bathrooms = models.IntegerField(default=0)

    description = models.TextField(blank=True)

    status = models.CharField(
        max_length=50,
        choices=STATUS_CHOICES,
        default="draft"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title