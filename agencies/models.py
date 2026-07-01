from django.db import models
from django.utils import timezone


class Agency(models.Model):
    PAYMENT_UNPAID = "unpaid"
    PAYMENT_PENDING = "pending"
    PAYMENT_PAID = "paid"
    PAYMENT_EXPIRED = "expired"
    PAYMENT_CANCELLED = "cancelled"

    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_UNPAID, "Unpaid"),
        (PAYMENT_PENDING, "Pending"),
        (PAYMENT_PAID, "Paid"),
        (PAYMENT_EXPIRED, "Expired"),
        (PAYMENT_CANCELLED, "Cancelled"),
    ]

    name = models.CharField(max_length=255)
    license_number = models.CharField(max_length=100, unique=True)

    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)

    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default=PAYMENT_UNPAID
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def mark_paid(self):
        self.payment_status = self.PAYMENT_PAID
        self.paid_at = timezone.now()
        self.save(
            update_fields=[
                "payment_status",
                "paid_at",
            ]
        )

    def __str__(self):
        return self.name