from django.db import models
import uuid
from django.utils import timezone

from agencies.models import Agency
from users.models import AgencyUser


class Property(models.Model):
    PROPERTY_TYPES = [
        ("house", "House"),
        ("land", "Land"),
        ("apartment", "Apartment"),
        ("flat", "Flat"),
        ("commercial", "Commercial"),
        ("office_space", "Office Space"),
    ]

    PURPOSES = [
        ("sale", "Sale"),
        ("rent", "Rent"),
        ("lease", "Lease"),
    ]

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("available", "Available"),
        ("under_negotiation", "Under Negotiation"),
        ("sold", "Sold"),
        ("rented", "Rented"),
        ("hidden", "Hidden"),
        ("archived", "Archived"),
    ]

    AREA_UNITS = [
        ("aana", "Aana"),
        ("ropani", "Ropani"),
        ("kattha", "Kattha"),
        ("dhur", "Dhur"),
        ("bigha","Bigha"),
        ("sqft", "Square Feet"),
        ("sqm", "Square Meter"),
    ]

    ROAD_UNITS = [
        ("ft", "Feet"),
        ("m", "Meter"),
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
        blank=True,
        related_name="assigned_properties"
    )

    # Step 1: Basic Info
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

    currency = models.CharField(
        max_length=10,
        default="NPR"
    )

    # Step 2: Location
    province = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    city = models.CharField(max_length=100)

    neighbourhood = models.CharField(
        max_length=255,
        blank=True
    )

    address = models.TextField(blank=True)

    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True
    )

    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True
    )

    # Step 3: Property Details
    bedrooms = models.PositiveIntegerField(default=0)
    bathrooms = models.PositiveIntegerField(default=0)
    floors = models.PositiveIntegerField(default=0)

    land_area_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    land_area_unit = models.CharField(
        max_length=20,
        choices=AREA_UNITS,
        blank=True
    )

    built_up_area_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    built_up_area_unit = models.CharField(
        max_length=20,
        choices=AREA_UNITS,
        default="sqft"
    )

    road_access_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    road_access_unit = models.CharField(
        max_length=20,
        choices=ROAD_UNITS,
        default="ft"
    )

    # Example:
    # ["24_7_water", "electricity", "car_parking"]
    amenities = models.JSONField(
        default=list,
        blank=True
    )

    # Step 4: Media Related
    virtual_tour_url = models.URLField(
        blank=True
    )
    video_tour_url = models.URLField(blank=True)

    # Step 5: Description
    short_description = models.CharField(
        max_length=255,
        blank=True
    )

    description = models.TextField(blank=True)
    custom_data = models.JSONField(default=dict, blank=True)
    seo_title = models.CharField(max_length=70, blank=True)
    seo_description = models.CharField(max_length=180, blank=True)
    share_slug = models.SlugField(max_length=180, blank=True)

    # Step 6: Publish
    status = models.CharField(
        max_length=50,
        choices=STATUS_CHOICES,
        default="draft"
    )
    FURNISHING_UNFURNISHED = "unfurnished"
    FURNISHING_SEMI = "semi_furnished"
    FURNISHING_FULL = "fully_furnished"

    FURNISHING_STATUS_CHOICES = [
        (FURNISHING_UNFURNISHED, "Unfurnished"),
        (FURNISHING_SEMI, "Semi-Furnished"),
        (FURNISHING_FULL, "Fully Furnished"),
    ]

    FACING_NORTH = "north"
    FACING_SOUTH = "south"
    FACING_EAST = "east"
    FACING_WEST = "west"
    FACING_NORTH_EAST = "north_east"
    FACING_NORTH_WEST = "north_west"
    FACING_SOUTH_EAST = "south_east"
    FACING_SOUTH_WEST = "south_west"

    FACING_DIRECTION_CHOICES = [
        (FACING_NORTH, "North"),
        (FACING_SOUTH, "South"),
        (FACING_EAST, "East"),
        (FACING_WEST, "West"),
        (FACING_NORTH_EAST, "North-East"),
        (FACING_NORTH_WEST, "North-West"),
        (FACING_SOUTH_EAST, "South-East"),
        (FACING_SOUTH_WEST, "South-West"),
    ]
    year_built = models.PositiveIntegerField(
        null=True,
        blank=True
    )

    parking_spaces = models.PositiveIntegerField(
        null=True,
        blank=True
    )

    parking_type = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    furnishing_status = models.CharField(
        max_length=30,
        choices=FURNISHING_STATUS_CHOICES,
        blank=True,
        null=True
    )

    facing_direction = models.CharField(
        max_length=30,
        choices=FACING_DIRECTION_CHOICES,
        blank=True,
        null=True
    )
    is_published = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False)

    published_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        indexes = [
            models.Index(fields=["agency", "is_published", "status"]),
            models.Index(fields=["agency", "property_type", "purpose"]),
            models.Index(fields=["agency", "assigned_agent", "status"]),
            models.Index(fields=["city", "district"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["agency", "share_slug"], name="unique_agency_property_share_slug"),
        ]

    def save(self, *args, **kwargs):
        if not self.share_slug:
            from django.utils.text import slugify
            stem = slugify(self.title)[:140] or "listing"
            self.share_slug = f"{stem}-{uuid.uuid4().hex[:8]}"
        changed_fields = set(kwargs.get("update_fields") or [])

        if self.status != "available":
            self.is_published = False
            changed_fields.add("is_published")

        if self.is_published and self.published_at is None:
            self.published_at = timezone.now()
            changed_fields.add("published_at")

        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = changed_fields

        super().save(*args, **kwargs)


class PropertyMedia(models.Model):
    MEDIA_TYPES = [
        ("image", "Image"),
        ("video", "Video"),
        ("reel", "Reel"),
        ("brochure", "Brochure"),
        ("floor_plan", "Floor Plan"),
        ("document", "Document"),
    ]

    agency = models.ForeignKey(
        Agency,
        on_delete=models.CASCADE,
        related_name="property_media"
    )

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="media"
    )

    media_type = models.CharField(
        max_length=50,
        choices=MEDIA_TYPES,
        default="image"
    )

    file = models.FileField(
        upload_to="property_media/",
        null=True,
        blank=True
    )

    external_url = models.URLField(
        blank=True
    )

    thumbnail = models.ImageField(
        upload_to="property_media/thumbnails/",
        null=True,
        blank=True
    )

    title = models.CharField(max_length=255, blank=True)
    caption = models.TextField(blank=True)

    sort_order = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False)

    uploaded_by = models.ForeignKey(
        AgencyUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_property_media"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.property.title} - {self.media_type}"


class PropertyEvent(models.Model):
    EVENT_VIEW = "view"
    EVENT_WHATSAPP_CLICK = "whatsapp_click"
    EVENT_VIBER_CLICK = "viber_click"
    EVENT_CALL_CLICK = "call_click"
    EVENT_INQUIRY = "inquiry"
    EVENT_SITE_VISIT_REQUEST = "site_visit_request"

    EVENT_TYPE_CHOICES = [
        (EVENT_VIEW, "Property View"),
        (EVENT_WHATSAPP_CLICK, "WhatsApp Click"),
        (EVENT_VIBER_CLICK, "Viber Click"),
        (EVENT_CALL_CLICK, "Call Click"),
        (EVENT_INQUIRY, "Inquiry"),
        (EVENT_SITE_VISIT_REQUEST, "Site Visit Request"),
    ]

    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="property_events")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="events")
    lead = models.ForeignKey(
        "leads.Lead",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="property_events",
    )
    event_type = models.CharField(max_length=40, choices=EVENT_TYPE_CHOICES)
    visitor_id = models.CharField(max_length=100, blank=True)
    referrer = models.URLField(max_length=1000, blank=True)
    utm_source = models.CharField(max_length=100, blank=True)
    utm_medium = models.CharField(max_length=100, blank=True)
    utm_campaign = models.CharField(max_length=150, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["agency", "event_type", "created_at"]),
            models.Index(fields=["property", "event_type", "created_at"]),
        ]


AREA_UNIT_CHOICES = Property.AREA_UNITS
