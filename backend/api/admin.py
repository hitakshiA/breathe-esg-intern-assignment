from django.contrib import admin

from .models import (
    Activity,
    ActivityEmission,
    AuditLog,
    EmissionFactor,
    EnergyAttributeCertificate,
    Facility,
    IngestionBatch,
    Organization,
    RawRow,
    Review,
    User,
)

for m in [Organization, User, Facility, IngestionBatch, RawRow, Activity,
          ActivityEmission, EmissionFactor, EnergyAttributeCertificate,
          Review, AuditLog]:
    try:
        admin.site.register(m)
    except admin.sites.AlreadyRegistered:
        pass
