from decimal import Decimal
from django.db import models
from core.models import InternalSection


class City(models.Model):

    """Configurable City master for pilgrims, tour operators, and venues."""
    name = models.CharField(max_length=100, unique=True, db_index=True)
    province = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = 'City'
        verbose_name_plural = 'Cities'

    def __str__(self):
        return self.name


class CeremonyVenue(models.Model):
    """Configurable ceremonial venues for Ceremony Fund."""
    code = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=150)
    city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True, blank=True, related_name='venues')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = 'Ceremony Venue'
        verbose_name_plural = 'Ceremony Venues'

    def __str__(self):
        return f"{self.name} ({self.code})"


class CeremonyEvent(models.Model):
    """Specific event with year distinction for Ceremony Fund (e.g. Pak Day Ceremony 2026)."""
    account = models.ForeignKey('core.Account', on_delete=models.PROTECT, related_name='ceremony_events', null=True, blank=True)
    event_year = models.CharField(max_length=10, help_text="e.g. 2026", db_index=True)
    name = models.CharField(max_length=150)
    major_head = models.ForeignKey('core.MajorHead', on_delete=models.SET_NULL, null=True, blank=True, related_name='ceremony_events')
    venue = models.ForeignKey(CeremonyVenue, on_delete=models.SET_NULL, null=True, blank=True, related_name='events')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        ordering = ['-event_year', 'name']
        verbose_name = 'Ceremony Event'
        verbose_name_plural = 'Ceremony Events'

    def __str__(self):
        return f"{self.name} {self.event_year}"


class Cohort(models.Model):
    """Cohort tag for Corporate Haj (HJC) & Umra (UMC) operations."""
    class CohortType(models.TextChoices):
        HAJ = 'HAJ', 'Hajj Cohort (HJC)'
        UMRA = 'UMRA', 'Umrah Cohort (UMC)'

    account = models.ForeignKey('core.Account', on_delete=models.PROTECT, related_name='cohorts')
    cohort_type = models.CharField(max_length=10, choices=CohortType.choices, default=CohortType.HAJ, db_index=True)
    code = models.CharField(max_length=50, unique=True, help_text="e.g. HJC-2026 or UMC-01 (2025-26)", db_index=True)
    title = models.CharField(max_length=150, help_text="e.g. Hajj Cohort 2026")
    cycle_label = models.CharField(max_length=50, blank=True, help_text="e.g. 2026 for Haj or 2025-26 for Umra")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['-code']
        verbose_name = 'Cohort (HJC / UMC)'
        verbose_name_plural = 'Cohorts (HJC / UMC)'

    def __str__(self):
        return f"{self.code} - {self.title}"


class CohortPackage(models.Model):
    """Dynamic Haj and Umra Package Master with sequential planning details and sharing rates."""
    class BoardingType(models.TextChoices):
        ROOM_ONLY = 'RO', 'Room Only'
        BED_AND_BREAKFAST = 'BB', 'Bed & Breakfast (B&B)'
        HALF_BOARD = 'HB', 'Half Board (Breakfast + Dinner)'
        FULL_BOARD = 'FB', 'Full Board (3 Meals)'

    class AccnType(models.TextChoices):
        HOTEL = 'HOTEL', 'Hotel'
        BUILDING = 'BUILDING', 'Building / Apartment'

    class MedinaTiming(models.TextChoices):
        BEFORE_MAKKAH = 'BEFORE', 'Medina 1st (Before Makkah)'
        AFTER_MAKKAH = 'AFTER', 'Medina 2nd (After Makkah)'

    class PackageType(models.TextChoices):
        HAJ = 'HAJ', 'Haj Package'
        UMRA = 'UMRA', 'Umra Package'

    class TransferMode(models.TextChoices):
        TRAIN = 'TRAIN', 'High-Speed Haramain Train'
        BUS = 'BUS', 'AC Luxury Bus'
        FLIGHT = 'FLIGHT', 'Domestic Flight'

    class FlightRoute(models.TextChoices):
        DIRECT = 'DIRECT', 'Direct Flight'
        CONNECTING = 'CONNECTING', 'Connecting Flight'

    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE, related_name='packages')
    package_type = models.CharField(max_length=10, choices=PackageType.choices, default=PackageType.HAJ, db_index=True)
    package_code = models.CharField(max_length=50, help_text="e.g. HJC-2027-ECO or UMC-01-STD", db_index=True)
    package_name = models.CharField(max_length=150, help_text="e.g. Economy Package, Economy Plus, Executive")
    total_days = models.PositiveIntegerField(default=40, help_text="Total duration in days")
    description = models.TextField(blank=True)

    # 1. Flight Details
    airline = models.CharField(max_length=100, blank=True, help_text="e.g. PIA, Saudia, Serene Air")
    flight_route = models.CharField(max_length=20, choices=FlightRoute.choices, default=FlightRoute.DIRECT)
    flight_origin = models.CharField(max_length=100, blank=True, default="Islamabad (ISB)")
    flight_destination = models.CharField(max_length=100, blank=True, default="Medina (MED) / Jeddah (JED)")

    # 2. Medina Stay Details
    medina_order = models.CharField(max_length=20, choices=MedinaTiming.choices, default=MedinaTiming.BEFORE_MAKKAH)
    medina_days = models.PositiveIntegerField(default=8, help_text="Number of days in Medina")
    medina_accn_type = models.CharField(max_length=20, choices=AccnType.choices, default=AccnType.HOTEL)
    medina_hotel_name = models.CharField(max_length=150, blank=True, help_text="e.g. Leader Al Muna Kareem")
    medina_boarding = models.CharField(max_length=10, choices=BoardingType.choices, default=BoardingType.BED_AND_BREAKFAST)

    # 3. Inter-City Transfer
    transfer_mode = models.CharField(max_length=20, choices=TransferMode.choices, default=TransferMode.TRAIN)

    # 4. Makkah Phase 1 (Main Stay / Initial Hotel)
    makkah_p1_days = models.PositiveIntegerField(default=7, help_text="Days in Makkah Phase 1")
    makkah_p1_accn_type = models.CharField(max_length=20, choices=AccnType.choices, default=AccnType.HOTEL)
    makkah_p1_hotel_name = models.CharField(max_length=150, blank=True, help_text="e.g. Swissotel Al Maqam")
    makkah_p1_boarding = models.CharField(max_length=10, choices=BoardingType.choices, default=BoardingType.BED_AND_BREAKFAST)

    # 5. Makkah Phase 2 (Pre/Post Haj Azizia Building Stay)
    makkah_p2_days = models.PositiveIntegerField(default=5, help_text="Days in Azizia Building (0 for Umra/Direct)")
    makkah_p2_accn_type = models.CharField(max_length=20, choices=AccnType.choices, default=AccnType.BUILDING)
    makkah_p2_building_name = models.CharField(max_length=150, blank=True, help_text="e.g. Azizia Building A-3")
    makkah_p2_boarding = models.CharField(max_length=10, choices=BoardingType.choices, default=BoardingType.FULL_BOARD)

    # 6. Mashair (Actual Haj Days - Mina, Arafat, Muzdalifah)
    mashair_days = models.PositiveIntegerField(default=5, help_text="Actual Haj days (typically 5 days)")
    mina_maktab = models.CharField(max_length=50, blank=True, default="Maktab A", help_text="e.g. Maktab A, Maktab B, VIP")
    mina_zone = models.CharField(max_length=50, blank=True, default="Zone 1", help_text="e.g. Zone 1, Zone 2, Zone 3")
    mashair_boarding = models.CharField(max_length=10, choices=BoardingType.choices, default=BoardingType.FULL_BOARD)
    arafat_details = models.CharField(max_length=200, blank=True, default="AC Marquees with Buffet / Box Meals")
    muzdalifah_details = models.CharField(max_length=200, blank=True, default="Open air night stay with packed snack/food box")

    # 7. Post-Haj Makkah Days
    post_haj_days = models.PositiveIntegerField(default=0, help_text="Post-Haj stay days in Makkah if applicable")

    # 8. Room Sharing Rates (Rate per Person in PKR)
    rate_double_sharing = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), help_text="Cost per person for 2 in room")
    rate_triple_sharing = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), help_text="Cost per person for 3 in room")
    rate_quad_sharing = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), help_text="Cost per person for 4+ in room")

    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['cohort', 'package_name']
        unique_together = [['cohort', 'package_code']]
        verbose_name = 'Cohort Package'
        verbose_name_plural = 'Cohort Packages'

    @property
    def is_umra(self):
        return self.package_type == self.PackageType.UMRA or (self.cohort and self.cohort.cohort_type == Cohort.CohortType.UMRA)

    def save(self, *args, **kwargs):
        # Auto-sync package_type with cohort if set to UMRA
        if self.cohort and self.cohort.cohort_type == Cohort.CohortType.UMRA:
            self.package_type = self.PackageType.UMRA
        elif self.cohort and self.cohort.cohort_type == Cohort.CohortType.HAJ:
            self.package_type = self.PackageType.HAJ

        # For Umra packages: simplify and zero out Mashair, Post-Haj, and Azizia stay
        if self.package_type == self.PackageType.UMRA:
            self.mashair_days = 0
            self.mina_maktab = ""
            self.mina_zone = ""
            self.arafat_details = ""
            self.muzdalifah_details = ""
            self.post_haj_days = 0
            self.makkah_p2_days = 0
            self.makkah_p2_building_name = ""

        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.get_package_type_display()}] {self.cohort.code} - {self.package_name} ({self.package_code})"


class Pilgrim(models.Model):
    """Pilgrim registry for Corporate Provident Fund."""
    class SubFund(models.TextChoices):
        HAJ = 'HAJ', 'Haj'
        UMRA = 'UMRA', 'Umra'

    class SharingType(models.TextChoices):
        DOUBLE = 'DOUBLE', 'Double Sharing (2 In Room)'
        TRIPLE = 'TRIPLE', 'Triple Sharing (3 In Room)'
        QUAD = 'QUAD', 'Quad Sharing (4 In Room)'

    account = models.ForeignKey('core.Account', on_delete=models.PROTECT, related_name='pilgrims')
    cohort = models.ForeignKey(Cohort, on_delete=models.SET_NULL, null=True, blank=True, related_name='pilgrims')
    package = models.ForeignKey(CohortPackage, on_delete=models.SET_NULL, null=True, blank=True, related_name='pilgrims')
    sharing_type = models.CharField(max_length=15, choices=SharingType.choices, default=SharingType.QUAD, blank=True)
    family_members_count = models.PositiveIntegerField(default=1, help_text="No. of persons (Self + Family)")
    total_package_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

    employee_no = models.CharField(max_length=50, db_index=True, help_text="e.g. EMP-12345")
    name_and_designation = models.CharField(max_length=150)
    cnic = models.CharField(max_length=30, blank=True)
    passport_number = models.CharField(max_length=30, blank=True)
    city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True, blank=True, related_name='pilgrims')
    unit_or_formation = models.ForeignKey('core.Unit', on_delete=models.SET_NULL, null=True, blank=True, related_name='pilgrims')
    sub_fund = models.CharField(max_length=10, choices=SubFund.choices, default=SubFund.HAJ, db_index=True)
    contact_number = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name_and_designation']
        verbose_name = 'Pilgrim'
        verbose_name_plural = 'Pilgrims'

    def calculate_cost(self):
        """Auto-detect rate based on package, sharing type and number of persons."""
        if not self.package:
            return Decimal('0.00')
        persons = self.family_members_count or 1
        rate = Decimal('0.00')
        if self.sharing_type == self.SharingType.DOUBLE:
            rate = self.package.rate_double_sharing
        elif self.sharing_type == self.SharingType.TRIPLE:
            rate = self.package.rate_triple_sharing
        else:
            rate = self.package.rate_quad_sharing
        return (rate * Decimal(str(persons))).quantize(Decimal('0.01'))

    def save(self, *args, **kwargs):
        if not self.total_package_cost or self.total_package_cost == Decimal('0.00'):
            self.total_package_cost = self.calculate_cost()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee_no} {self.name_and_designation} [{self.get_sub_fund_display()}]"



class TourOperator(models.Model):
    """Tour Operator / Travel Agency registry for EWF packages."""
    account = models.ForeignKey('core.Account', on_delete=models.PROTECT, related_name='tour_operators')
    name = models.CharField(max_length=150, db_index=True)
    registration_number = models.CharField(max_length=100, blank=True, help_text="e.g. DTS / MoRA License No")
    city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True, blank=True, related_name='tour_operators')
    focal_person = models.CharField(max_length=100, blank=True)
    contact_number = models.CharField(max_length=50, blank=True)
    bank_iban = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Tour Operator'
        verbose_name_plural = 'Tour Operators'

    def __str__(self):
        return f"{self.name} ({self.city.name if self.city else 'Pakistan'})"



class UnitSectionResponsibility(models.Model):
    """Configurable relationship between Units and the Internal Sections managing them."""

    unit = models.ForeignKey('core.Unit', on_delete=models.PROTECT, related_name='section_responsibilities')
    section = models.ForeignKey(InternalSection, on_delete=models.PROTECT, related_name='unit_responsibilities')
    is_primary = models.BooleanField(default=False, help_text='Marks the normal/primary responsible section where one exists.')
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['unit__display_order', 'section__display_order', 'unit__name', 'section__name']
        constraints = [
            models.UniqueConstraint(fields=['unit', 'section'], name='unique_unit_section_responsibility')
        ]
        verbose_name = 'Unit / Section Responsibility'
        verbose_name_plural = 'Unit / Section Responsibilities'

    def __str__(self):
        primary = ' (Primary)' if self.is_primary else ''
        return f'{self.unit} -> {self.section}{primary}'


class TransactionOrganisationAllocation(models.Model):
    """Detailed organisational attribution for a transaction."""

    transaction = models.ForeignKey('core.Transaction', on_delete=models.CASCADE, related_name='organisation_allocations')
    unit = models.ForeignKey('core.Unit', on_delete=models.PROTECT, related_name='transaction_organisation_allocations', null=True, blank=True)
    internal_section = models.ForeignKey(InternalSection, on_delete=models.PROTECT, related_name='transaction_organisation_allocations', null=True, blank=True)
    allocated_amount = models.DecimalField(max_digits=18, decimal_places=2)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['transaction__transaction_date', 'transaction', 'unit', 'internal_section']
        verbose_name = 'Transaction Organisation Allocation'
        verbose_name_plural = 'Transaction Organisation Allocations'
        constraints = [
            models.CheckConstraint(condition=models.Q(allocated_amount__gt=0), name='transaction_org_alloc_amount_positive'),
            models.CheckConstraint(condition=models.Q(unit__isnull=False) | models.Q(internal_section__isnull=False), name='transaction_org_alloc_has_dimension'),
            models.UniqueConstraint(fields=['transaction', 'unit', 'internal_section'], name='unique_transaction_org_allocation')
        ]

    def __str__(self):
        return f'{self.transaction} -> {self.allocated_amount}'
