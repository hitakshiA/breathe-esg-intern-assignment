from __future__ import annotations

import csv
from collections import defaultdict
from decimal import Decimal

from django.db.models import Q, Sum
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from . import audit
from .ingest import ingest_file
from .models import (
    Activity,
    AuditLog,
    EmissionFactor,
    Facility,
    IngestionBatch,
    Review,
)
from .serializers import (
    ActivityDetailSerializer,
    ActivityListSerializer,
    AuditLogSerializer,
    EmissionFactorSerializer,
    FacilitySerializer,
    IngestionBatchSerializer,
    ReviewActionSerializer,
    UserSerializer,
)


# ── public health check ─────────────────────────────────────────────────────
class HealthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"status": "ok", "service": "breathe-esg-api"})


class TokenView(TokenObtainPairView):
    permission_classes = [AllowAny]


# ── auth-required views ─────────────────────────────────────────────────────
class _OrgScopedMixin:
    """Restrict all querysets to the current user's organization."""

    org_field = "organization"

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return qs.none()
        if user.organization is None and not user.is_superuser:
            return qs.none()
        if user.is_superuser and user.organization is None:
            return qs  # admin sees all
        return qs.filter(**{self.org_field: user.organization})


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class FacilityViewSet(_OrgScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = FacilitySerializer
    queryset = Facility.objects.all()


class FactorViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EmissionFactorSerializer
    queryset = EmissionFactor.objects.all()
    permission_classes = [IsAuthenticated]


class BatchViewSet(_OrgScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = IngestionBatchSerializer
    queryset = IngestionBatch.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        st = self.request.query_params.get("source_type")
        if st:
            qs = qs.filter(source_type=st)
        return qs


from pathlib import Path

from rest_framework.parsers import FormParser, MultiPartParser


class SampleCSVView(APIView):
    """Public endpoint: anyone can grab the bundled sample CSVs to try the upload flow."""
    permission_classes = [AllowAny]
    authentication_classes = []

    SAMPLES = {
        "sap_fuel": ("sap_fuel_extract.csv", "SAP MB51 fuel & procurement extract (German locale)"),
        "utility_electricity": ("utility_electricity_export.csv", "US utility portal export (PG&E / ConEd shape)"),
        "travel": ("concur_expense_extract.csv", "Concur expense report extract"),
    }

    def get(self, request, source_type: str):
        meta = self.SAMPLES.get(source_type)
        if not meta:
            return Response({"detail": "Unknown source_type."}, status=404)
        name, _label = meta
        candidates = [Path("/app/samples") / name, Path(__file__).resolve().parent.parent.parent.parent / "samples" / name]
        for path in candidates:
            if path.exists():
                resp = HttpResponse(path.read_bytes(), content_type="text/csv")
                resp["Content-Disposition"] = f'attachment; filename="{name}"'
                return resp
        return Response({"detail": "Sample file not found on server."}, status=404)


class SampleListView(APIView):
    """Public catalogue of sample CSVs available for the demo."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response([
            {"source_type": k, "filename": v[0], "label": v[1]}
            for k, v in SampleCSVView.SAMPLES.items()
        ])


class UploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        user = request.user
        if not user.organization:
            return Response({"detail": "User has no organization."},
                            status=status.HTTP_400_BAD_REQUEST)
        source_type = request.data.get("source_type")
        file_obj = request.FILES.get("file")
        if not source_type or not file_obj:
            return Response({"detail": "source_type and file are required."},
                            status=status.HTTP_400_BAD_REQUEST)
        if source_type not in dict(IngestionBatch.SOURCE_CHOICES):
            return Response({"detail": f"Unknown source_type '{source_type}'."},
                            status=status.HTTP_400_BAD_REQUEST)
        # Hard-fail PDFs (per TRADEOFFS.md)
        if file_obj.name.lower().endswith(".pdf"):
            return Response({
                "detail": "PDF ingestion is not supported in V1. "
                          "Please export the portal CSV. See TRADEOFFS.md.",
            }, status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)

        batch = ingest_file(user.organization, source_type, file_obj, file_obj.name, user)
        return Response(IngestionBatchSerializer(batch).data, status=status.HTTP_201_CREATED)


class ActivityViewSet(_OrgScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Activity.objects.all().select_related("facility", "raw_row__batch").prefetch_related("emissions__factor", "reviews")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ActivityDetailSerializer
        return ActivityListSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if status_param := params.get("review_status"):
            qs = qs.filter(review_status=status_param)
        if scope := params.get("scope"):
            qs = qs.filter(scope=scope)
        if facility := params.get("facility"):
            qs = qs.filter(facility_id=facility)
        if ptype := params.get("activity_type"):
            qs = qs.filter(activity_type=ptype)
        if params.get("suspicious") in {"1", "true", "True"}:
            qs = qs.filter(~Q(flags=[]))
        return qs

    @action(detail=True, methods=["post"], url_path="review")
    def review(self, request, pk=None):
        activity = self.get_object()
        ser = ReviewActionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        action_name = ser.validated_data["action"]
        comment = ser.validated_data.get("comment", "")

        if action_name == Review.ACTION_REJECT and not comment.strip():
            return Response({"detail": "Reject requires a comment."},
                            status=status.HTTP_400_BAD_REQUEST)
        before = {"review_status": activity.review_status}
        if action_name == Review.ACTION_APPROVE:
            activity.review_status = Activity.REVIEW_APPROVED
        elif action_name == Review.ACTION_REJECT:
            activity.review_status = Activity.REVIEW_REJECTED
        else:
            activity.review_status = Activity.REVIEW_PENDING
        activity.save(update_fields=["review_status", "updated_at"])
        Review.objects.create(
            activity=activity, reviewer=request.user,
            action=action_name, comment=comment,
        )
        audit.record(activity.organization, activity, f"review.{action_name}",
                     before=before, after={"review_status": activity.review_status})
        return Response(ActivityDetailSerializer(activity).data)


class SummaryView(APIView):
    """Aggregated emissions for the dashboard."""

    def get(self, request):
        user = request.user
        org = user.organization
        if not org:
            return Response({"detail": "No organization."}, status=400)

        ps = request.query_params.get("period_start")
        pe = request.query_params.get("period_end")

        activities = Activity.objects.filter(organization=org, review_status=Activity.REVIEW_APPROVED)
        if ps:
            activities = activities.filter(period_start__gte=ps)
        if pe:
            activities = activities.filter(period_end__lte=pe)

        # Aggregate per scope and per method
        by_scope = defaultdict(lambda: Decimal("0"))
        by_facility = defaultdict(lambda: Decimal("0"))
        by_quality = defaultdict(lambda: Decimal("0"))
        scope2_location = Decimal("0")
        scope2_market = Decimal("0")
        scope2_market_pending = 0

        for a in activities.prefetch_related("emissions"):
            # Use location_based for scope 2 totals to avoid double-counting
            primary = a.emissions.filter(
                method__in=["location_based", "activity_based"]
            ).first()
            if primary and primary.co2e_kg:
                by_scope[a.scope] += primary.co2e_kg
                fac = a.facility.name if a.facility else "Unassigned"
                by_facility[fac] += primary.co2e_kg
                by_quality[a.data_quality_tier] += primary.co2e_kg
            if a.scope == "2":
                loc = a.emissions.filter(method="location_based").first()
                mkt = a.emissions.filter(method="market_based").first()
                if loc and loc.co2e_kg:
                    scope2_location += loc.co2e_kg
                if mkt and mkt.co2e_kg:
                    scope2_market += mkt.co2e_kg
                else:
                    scope2_market_pending += 1

        return Response({
            "totals_kg": {
                "scope_1": by_scope["1"],
                "scope_2_location": scope2_location,
                "scope_2_market": scope2_market if scope2_market > 0 else None,
                "scope_2_market_pending_rows": scope2_market_pending,
                "scope_3_cat_6": by_scope["3"],
                "total": sum(by_scope.values()),
            },
            "by_facility": [
                {"facility": k, "co2e_kg": v}
                for k, v in sorted(by_facility.items(), key=lambda x: -x[1])
            ],
            "by_quality_tier": {str(k): v for k, v in by_quality.items()},
            "approved_count": activities.count(),
            "period": {"start": ps, "end": pe},
        })


class AuditorBundleCSV(APIView):
    """One-click CSV export with full provenance — the auditor's deliverable."""

    def get(self, request):
        org = request.user.organization
        if not org:
            return Response({"detail": "No organization."}, status=400)
        activities = (
            Activity.objects.filter(organization=org)
            .select_related("facility", "raw_row__batch")
            .prefetch_related("emissions__factor", "reviews__reviewer")
            .order_by("scope", "period_start")
        )
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="auditor_bundle.csv"'
        w = csv.writer(resp)
        w.writerow([
            "activity_id", "scope", "scope3_category", "activity_type",
            "facility", "period_start", "period_end",
            "quantity_original", "unit_original",
            "quantity_normalized", "unit_normalized",
            "method", "factor_value_snapshot", "factor_source_snapshot",
            "rf_multiplier_snapshot", "co2e_kg",
            "data_quality_tier", "review_status",
            "reviewed_by", "reviewed_at", "review_comment",
            "raw_row_id", "raw_row_sha256",
            "ingestion_batch_id", "source_file", "source_file_sha256",
        ])
        for a in activities:
            review = a.reviews.order_by("-created_at").first()
            for em in a.emissions.all():
                w.writerow([
                    a.id, a.scope, a.scope3_category, a.activity_type,
                    a.facility.name if a.facility else "",
                    a.period_start, a.period_end,
                    a.quantity_original, a.unit_original,
                    a.quantity_normalized, a.unit_normalized,
                    em.method, em.factor_value_snapshot, em.factor_source_snapshot,
                    em.rf_multiplier_snapshot or "",
                    em.co2e_kg or "",
                    a.data_quality_tier, a.review_status,
                    review.reviewer.username if review and review.reviewer else "",
                    review.created_at.isoformat() if review else "",
                    review.comment if review else "",
                    a.raw_row.id, a.raw_row.row_sha256,
                    a.raw_row.batch.id, a.raw_row.batch.file_name, a.raw_row.batch.file_sha256,
                ])
        return resp


class AuditLogView(_OrgScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    queryset = AuditLog.objects.all().select_related("user")
