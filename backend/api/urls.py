from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    ActivityViewSet,
    AuditLogView,
    AuditorBundleCSV,
    BatchViewSet,
    FacilityViewSet,
    FactorViewSet,
    HealthView,
    MeView,
    SampleCSVView,
    SampleListView,
    SummaryView,
    TokenView,
    UploadView,
)

router = DefaultRouter()
router.register("activities", ActivityViewSet, basename="activity")
router.register("batches", BatchViewSet, basename="batch")
router.register("facilities", FacilityViewSet, basename="facility")
router.register("factors", FactorViewSet, basename="factor")
router.register("audit-log", AuditLogView, basename="audit")

urlpatterns = [
    path("health/", HealthView.as_view()),
    path("auth/token/", TokenView.as_view()),
    path("auth/refresh/", TokenRefreshView.as_view()),
    path("me/", MeView.as_view()),
    path("ingestion/upload/", UploadView.as_view()),
    path("samples/", SampleListView.as_view()),
    path("samples/<str:source_type>/", SampleCSVView.as_view()),
    path("summary/", SummaryView.as_view()),
    path("export/auditor-bundle.csv", AuditorBundleCSV.as_view()),
    path("", include(router.urls)),
]
