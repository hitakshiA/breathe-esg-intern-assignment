from __future__ import annotations

from rest_framework import serializers

from .models import (
    Activity,
    ActivityEmission,
    AuditLog,
    EmissionFactor,
    Facility,
    IngestionBatch,
    Organization,
    RawRow,
    Review,
    User,
)


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name", "slug", "consolidation_approach",
                  "disclosure_framework", "created_at"]


class UserSerializer(serializers.ModelSerializer):
    organization = OrganizationSerializer(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "role", "organization"]


class FacilitySerializer(serializers.ModelSerializer):
    plant_codes = serializers.SerializerMethodField()

    class Meta:
        model = Facility
        fields = ["id", "name", "country_iso2", "region", "postal_code",
                  "egrid_subregion", "sap_plant_codes", "plant_codes"]

    def get_plant_codes(self, obj):
        return obj.plant_code_list()


class IngestionBatchSerializer(serializers.ModelSerializer):
    source_type_display = serializers.CharField(source="get_source_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    uploaded_by_username = serializers.CharField(source="uploaded_by.username", read_only=True, default="")

    class Meta:
        model = IngestionBatch
        fields = [
            "id", "source_type", "source_type_display",
            "file_name", "file_sha256",
            "uploaded_by_username", "uploaded_at",
            "status", "status_display",
            "row_count", "ok_count", "error_count", "duplicate_count",
            "error_summary",
        ]


class EmissionFactorSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmissionFactor
        fields = [
            "id", "source", "dataset_version_year", "activity_type",
            "fuel_or_energy_type", "region_code", "cabin_class", "haul_band",
            "valid_from", "valid_to",
            "factor_value", "unit_input", "unit_output",
            "rf_multiplier_applied", "gwp_basis", "source_url", "notes",
        ]


class ActivityEmissionSerializer(serializers.ModelSerializer):
    factor = EmissionFactorSerializer(read_only=True)
    method_display = serializers.CharField(source="get_method_display", read_only=True)

    class Meta:
        model = ActivityEmission
        fields = [
            "id", "method", "method_display",
            "factor",
            "factor_value_snapshot", "factor_source_snapshot",
            "rf_multiplier_snapshot",
            "co2e_kg", "note", "calculated_at",
        ]


class ReviewSerializer(serializers.ModelSerializer):
    reviewer_username = serializers.CharField(source="reviewer.username", read_only=True, default="")

    class Meta:
        model = Review
        fields = ["id", "action", "comment", "reviewer_username", "created_at"]


class ActivityListSerializer(serializers.ModelSerializer):
    activity_type_display = serializers.CharField(source="get_activity_type_display", read_only=True)
    scope_display = serializers.CharField(source="get_scope_display", read_only=True)
    facility_name = serializers.CharField(source="facility.name", read_only=True, default="")
    co2e_kg = serializers.SerializerMethodField()
    has_warnings = serializers.SerializerMethodField()

    class Meta:
        model = Activity
        fields = [
            "id", "activity_type", "activity_type_display",
            "scope", "scope_display", "scope3_category",
            "facility_name",
            "period_start", "period_end",
            "quantity_normalized", "unit_normalized",
            "fuel_or_energy_type", "cabin_class",
            "origin_iata", "destination_iata", "distance_km",
            "supplier_name", "description",
            "data_quality_tier", "review_status", "is_locked",
            "co2e_kg", "has_warnings",
        ]

    def get_co2e_kg(self, obj):
        # Prefer location_based for electricity; else activity_based.
        em = obj.emissions.filter(
            method__in=["location_based", "activity_based"]
        ).order_by("method").first()
        return em.co2e_kg if em else None

    def get_has_warnings(self, obj):
        return bool(obj.flags)


class ActivityDetailSerializer(ActivityListSerializer):
    raw_data = serializers.SerializerMethodField()
    emissions = ActivityEmissionSerializer(many=True, read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)
    flags = serializers.JSONField(read_only=True)
    raw_row_id = serializers.UUIDField(source="raw_row.id", read_only=True)
    batch_id = serializers.UUIDField(source="raw_row.batch.id", read_only=True)
    batch_file = serializers.CharField(source="raw_row.batch.file_name", read_only=True)

    class Meta(ActivityListSerializer.Meta):
        fields = ActivityListSerializer.Meta.fields + [
            "raw_row_id", "batch_id", "batch_file", "raw_data",
            "emissions", "reviews", "flags",
            "quantity_original", "unit_original",
        ]

    def get_raw_data(self, obj):
        return obj.raw_row.raw_data


class ReviewActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=[c[0] for c in Review.ACTION_CHOICES])
    comment = serializers.CharField(required=False, allow_blank=True, default="")


class AuditLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True, default="")

    class Meta:
        model = AuditLog
        fields = ["id", "username", "entity_type", "entity_id", "action",
                  "before", "after", "ip", "timestamp"]
