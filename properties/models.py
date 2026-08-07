from django.db import models
import uuid
import builtins
from django.utils import timezone

from agencies.models import Agency
from users.models import AgencyUser


def generate_distribution_code():
    return uuid.uuid4().hex[:10]


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
        ("reserved", "Reserved"),
        ("under_negotiation", "Under Negotiation"),
        ("sold", "Sold"),
        ("rented", "Rented"),
        ("withdrawn", "Withdrawn"),
        ("hidden", "Hidden"),
        ("archived", "Archived"),
    ]

    AREA_UNITS = [
        ("aana", "Aana"),
        ("ropani", "Ropani"),
        ("paisa", "Paisa"),
        ("daam", "Daam"),
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
    PROVINCE_CHOICES = [
        ("Koshi", "Koshi Province"), ("Madhesh", "Madhesh Province"),
        ("Bagmati", "Bagmati Province"), ("Gandaki", "Gandaki Province"),
        ("Lumbini", "Lumbini Province"), ("Karnali", "Karnali Province"),
        ("Sudurpashchim", "Sudurpashchim Province"),
    ]
    province = models.CharField(max_length=100, choices=PROVINCE_CHOICES)
    district = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    municipality = models.CharField(max_length=150, blank=True)
    ward_number = models.CharField(max_length=20, blank=True)
    tole = models.CharField(max_length=150, blank=True)
    landmark = models.CharField(max_length=255, blank=True)

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

    land_area_sqft = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, editable=False, db_index=True
    )
    LAND_USE_CHOICES = [
        ("residential", "Residential"), ("commercial", "Commercial"),
        ("agricultural", "Agricultural"), ("plotting", "Plotting"),
        ("mixed_use", "Mixed Use"), ("industrial", "Industrial"),
    ]
    land_use_classification = models.CharField(max_length=30, choices=LAND_USE_CHOICES, blank=True)

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

    ROAD_TYPE_CHOICES = [
        ("blacktopped", "Blacktopped / Pitched"), ("concrete", "Concrete"),
        ("gravel", "Gravel"), ("unpaved", "Unpaved"), ("other", "Other"),
    ]
    road_type = models.CharField(max_length=30, choices=ROAD_TYPE_CHOICES, blank=True)
    mohada_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    pichhad_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    plot_dimension_unit = models.CharField(max_length=20, choices=ROAD_UNITS, default="ft")
    PLOT_SHAPE_CHOICES = [
        ("rectangular", "Rectangular"), ("square", "Square"), ("regular", "Regular"),
        ("irregular", "Irregular"), ("triangular", "Triangular"),
        ("corner", "Corner Plot"), ("other", "Other"),
    ]
    plot_shape = models.CharField(max_length=30, choices=PLOT_SHAPE_CHOICES, blank=True)
    has_water_supply = models.BooleanField(null=True, blank=True)
    has_electricity = models.BooleanField(null=True, blank=True)
    has_drainage = models.BooleanField(null=True, blank=True)
    has_sewage = models.BooleanField(null=True, blank=True)
    MAJOR_ROAD_TYPE_CHOICES = [
        ("ring_road", "Ring Road"), ("highway", "Highway"), ("main_road", "Major Road"),
    ]
    major_road_type = models.CharField(max_length=30, choices=MAJOR_ROAD_TYPE_CHOICES, blank=True)
    nearest_major_road = models.CharField(max_length=255, blank=True)
    major_road_distance_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    major_road_distance_unit = models.CharField(
        max_length=10, choices=[("m", "Meter"), ("km", "Kilometer")], default="m"
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

    availability_verified_at = models.DateTimeField(null=True, blank=True, db_index=True)
    listing_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    owner_confirmed_at = models.DateTimeField(null=True, blank=True)
    withdrawal_reason = models.TextField(blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    requires_republish_approval = models.BooleanField(default=False)
    REPUBLISH_APPROVAL_CHOICES = [
        ("not_required", "Not Required"), ("pending", "Pending"),
        ("approved", "Approved"), ("rejected", "Rejected"),
    ]
    republish_approval_status = models.CharField(
        max_length=20, choices=REPUBLISH_APPROVAL_CHOICES, default="not_required"
    )
    republish_requested_at = models.DateTimeField(null=True, blank=True)
    republish_requested_by = models.ForeignKey(
        AgencyUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="requested_property_republishes",
    )
    republish_approved_at = models.DateTimeField(null=True, blank=True)
    republish_approved_by = models.ForeignKey(
        AgencyUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="approved_property_republishes",
    )
    republish_rejection_reason = models.TextField(blank=True)

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
            models.Index(fields=["district", "municipality", "ward_number"]),
            models.Index(fields=["land_use_classification", "property_type"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["agency", "share_slug"], name="unique_agency_property_share_slug"),
        ]

    def save(self, *args, **kwargs):
        from .area import convert_area, rounded

        self.land_area_sqft = (
            rounded(convert_area(self.land_area_value, self.land_area_unit))
            if self.land_area_value is not None and self.land_area_unit else None
        )
        if not self.share_slug:
            from django.utils.text import slugify
            stem = slugify(self.title)[:140] or "listing"
            self.share_slug = f"{stem}-{uuid.uuid4().hex[:8]}"
        changed_fields = set(kwargs.get("update_fields") or [])
        changed_fields.add("land_area_sqft")

        publishable_statuses = {"available", "reserved", "under_negotiation"}
        if self.status not in publishable_statuses:
            self.is_published = False
            changed_fields.add("is_published")

        if self.status == "withdrawn" and self.withdrawn_at is None:
            self.withdrawn_at = timezone.now()
            changed_fields.add("withdrawn_at")
        elif self.status != "withdrawn" and self.withdrawn_at is not None:
            self.withdrawn_at = None
            changed_fields.add("withdrawn_at")

        if self.listing_expires_at and self.listing_expires_at <= timezone.now():
            self.is_published = False
            self.requires_republish_approval = True
            changed_fields.update({"is_published", "requires_republish_approval"})

        if self.requires_republish_approval:
            self.is_published = False
            changed_fields.add("is_published")

        if self.is_published and self.availability_verified_at is None:
            from datetime import timedelta
            self.availability_verified_at = timezone.now()
            self.listing_expires_at = self.availability_verified_at + timedelta(days=30)
            changed_fields.update({"availability_verified_at", "listing_expires_at"})

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


class PropertyVerification(models.Model):
    MILESTONES = [
        ("owner_identity_verified", "Owner identity verified"),
        ("ownership_document_received", "Ownership document received"),
        ("physically_inspected", "Agency physically inspected"),
        ("documents_reviewed", "Documents reviewed"),
        ("fully_verified", "Fully verified"),
    ]

    property = models.OneToOneField(Property, on_delete=models.CASCADE, related_name="verification")
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="property_verifications")
    owner_identity_verified = models.BooleanField(default=False)
    owner_identity_verified_at = models.DateTimeField(null=True, blank=True)
    ownership_document_received = models.BooleanField(default=False)
    ownership_document_received_at = models.DateTimeField(null=True, blank=True)
    physically_inspected = models.BooleanField(default=False)
    physically_inspected_at = models.DateTimeField(null=True, blank=True)
    documents_reviewed = models.BooleanField(default=False)
    documents_reviewed_at = models.DateTimeField(null=True, blank=True)
    fully_verified = models.BooleanField(default=False)
    fully_verified_at = models.DateTimeField(null=True, blank=True)
    inspection_notes = models.TextField(blank=True)
    review_notes = models.TextField(blank=True)
    updated_by = models.ForeignKey(
        AgencyUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="updated_property_verifications",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @builtins.property
    def verification_level(self):
        level = "unverified"
        for field, _ in self.MILESTONES:
            if getattr(self, field):
                level = field
            else:
                break
        return level

    @builtins.property
    def verification_level_display(self):
        return dict(self.MILESTONES).get(self.verification_level, "Not verified")


class PropertyVerificationDocument(models.Model):
    DOCUMENT_TYPES = [
        ("lalpurja", "Lalpurja"),
        ("owner_identity", "Owner citizenship or company registration"),
        ("napi_naksa", "Napi Naksa or trace map"),
        ("char_killa", "Char Killa"),
        ("malpot_receipt", "Malpot receipt"),
        ("property_tax_clearance", "Property-tax clearance"),
        ("building_map_approval", "Building map approval"),
        ("construction_completion", "Construction-completion certificate"),
        ("power_of_attorney", "Power of attorney"),
        ("marketing_authorization", "Agency marketing authorization"),
    ]
    STATUS_CHOICES = [
        ("missing", "Missing"), ("received", "Received"),
        ("under_review", "Under Review"), ("approved", "Approved"),
        ("rejected", "Rejected / Needs Correction"),
        ("not_applicable", "Not Applicable"),
    ]

    verification = models.ForeignKey(PropertyVerification, on_delete=models.CASCADE, related_name="documents")
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="property_verification_documents")
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="missing")
    file = models.FileField(upload_to="property_verification/", null=True, blank=True)
    external_url = models.URLField(blank=True)
    document_number = models.CharField(max_length=100, blank=True)
    issued_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        AgencyUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_property_documents",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["verification", "document_type"],
                name="unique_property_verification_document_type",
            )
        ]

    def __str__(self):
        return f"{self.verification.property.title} - {self.get_document_type_display()}"


class PropertyHistory(models.Model):
    EVENT_TYPES = [
        ("created", "Created"), ("updated", "Updated"),
        ("status_changed", "Status Changed"), ("freshness_confirmed", "Freshness Confirmed"),
        ("expired", "Listing Expired"), ("republish_requested", "Republish Requested"),
        ("republish_approved", "Republish Approved"), ("republish_rejected", "Republish Rejected"),
        ("withdrawn", "Withdrawn"), ("duplicate_flagged", "Duplicate Flagged"),
        ("report_received", "Public Report Received"),
    ]
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="property_history")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="history")
    actor = models.ForeignKey(
        AgencyUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="property_history_events",
    )
    event_type = models.CharField(max_length=40, choices=EVENT_TYPES)
    summary = models.CharField(max_length=255)
    changes = models.JSONField(default=dict, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["property", "created_at"])]


class PropertyDuplicateFlag(models.Model):
    STATUS_CHOICES = [
        ("pending", "Needs Review"), ("confirmed", "Confirmed Duplicate"),
        ("dismissed", "Not a Duplicate"),
    ]
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="property_duplicate_flags")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="duplicate_flags")
    candidate = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="duplicate_candidates")
    score = models.PositiveSmallIntegerField(default=0)
    reasons = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    reviewed_by = models.ForeignKey(
        AgencyUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_property_duplicates",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-score", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["property", "candidate"], name="unique_property_duplicate_pair")
        ]


class PropertyListingReminder(models.Model):
    REMINDER_TYPES = [
        ("seven_days", "7 Days Before Expiry"), ("three_days", "3 Days Before Expiry"),
        ("one_day", "1 Day Before Expiry"), ("expired", "Expired"),
    ]
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="freshness_reminders")
    expiry_at = models.DateTimeField()
    reminder_type = models.CharField(max_length=20, choices=REMINDER_TYPES)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["property", "expiry_at", "reminder_type"],
                name="unique_property_expiry_reminder",
            )
        ]


class PropertyEvent(models.Model):
    EVENT_VIEW = "view"
    EVENT_WHATSAPP_CLICK = "whatsapp_click"
    EVENT_VIBER_CLICK = "viber_click"
    EVENT_CALL_CLICK = "call_click"
    EVENT_INQUIRY = "inquiry"
    EVENT_SITE_VISIT_REQUEST = "site_visit_request"
    EVENT_DISTRIBUTION_CLICK = "distribution_click"

    EVENT_TYPE_CHOICES = [
        (EVENT_VIEW, "Property View"),
        (EVENT_WHATSAPP_CLICK, "WhatsApp Click"),
        (EVENT_VIBER_CLICK, "Viber Click"),
        (EVENT_CALL_CLICK, "Call Click"),
        (EVENT_INQUIRY, "Inquiry"),
        (EVENT_SITE_VISIT_REQUEST, "Site Visit Request"),
        (EVENT_DISTRIBUTION_CLICK, "Distribution Link Click"),
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


class PropertyDistributionLink(models.Model):
    agency = models.ForeignKey(
        Agency, on_delete=models.CASCADE, related_name="property_distribution_links"
    )
    property = models.ForeignKey(
        Property, on_delete=models.CASCADE, related_name="distribution_links"
    )
    code = models.CharField(
        max_length=16, unique=True, default=generate_distribution_code, editable=False
    )
    label = models.CharField(max_length=120, blank=True)
    source = models.CharField(max_length=100)
    medium = models.CharField(max_length=100, default="social")
    campaign = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    click_count = models.PositiveIntegerField(default=0)
    last_clicked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        AgencyUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_property_distribution_links",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["agency", "property", "source"]),
            models.Index(fields=["code", "is_active"]),
        ]

    def __str__(self):
        return f"{self.property.title} - {self.source}"


AREA_UNIT_CHOICES = Property.AREA_UNITS
