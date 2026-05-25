"""
Emission factor seed data.

Every value cites a real published source. Numbers should match the cited
document to 4 decimal places. If a future audit asks "where did 2.51233
come from", DEFRA's 2024 conversion factors workbook is the answer.

Conventions:
- factor_value stored CO2e per unit_input
- For aviation, factor_value is the published per-passenger-km value with
  RF separated into rf_multiplier_applied — we store both so disclosure is
  explicit. (DEFRA publishes "with RF" and "without RF" rows; we use the
  without-RF base and apply the 1.7× multiplier as a separate step.)
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

DEFRA_URL_2024 = "https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2024"
EPA_EGRID_URL = "https://www.epa.gov/egrid/summary-data"
IEA_URL = "https://www.iea.org/data-and-statistics/data-product/emissions-factors-2024"


# DEFRA 2024 — Fuels (kg CO2e/unit, full life-cycle WTW = scope 1 direct + WTT)
# Source: gov.uk "Conversion Factors 2024" workbook, Fuels tab.
DEFRA_2024_FUELS = [
    # (fuel_type,            unit, value (CO2e direct, no upstream))
    ("diesel_EN590",         "L",  Decimal("2.51233")),
    ("petrol",               "L",  Decimal("2.16846")),
    ("natural_gas",          "M3", Decimal("2.04428")),
    ("lpg",                  "KG", Decimal("1.55540")),
    ("biodiesel_B100",       "L",  Decimal("0.18708")),
    ("jet_fuel",             "L",  Decimal("2.54475")),
]


# EPA eGRID2022 Summary Table 1 — kg CO2e/kWh, derived from lb/MWh.
# Conversion: lb/MWh × 0.453592 / 1000 = kg/kWh (4 dp).
EPA_EGRID_2022 = [
    # (subregion, kg CO2e/kWh)
    ("AKGD", Decimal("0.4773")),
    ("AKMS", Decimal("0.2250")),
    ("AZNM", Decimal("0.3520")),
    ("CAMX", Decimal("0.2256")),
    ("ERCT", Decimal("0.3497")),
    ("FRCC", Decimal("0.3691")),
    ("HIMS", Decimal("0.5241")),
    ("HIOA", Decimal("0.7146")),
    ("MROE", Decimal("0.6711")),
    ("MROW", Decimal("0.4248")),
    ("NEWE", Decimal("0.2433")),
    ("NWPP", Decimal("0.2732")),
    ("NYCW", Decimal("0.4015")),
    ("NYLI", Decimal("0.5446")),
    ("NYUP", Decimal("0.1057")),
    ("PRMS", Decimal("0.7068")),
    ("RFCE", Decimal("0.3052")),
    ("RFCM", Decimal("0.5516")),
    ("RFCW", Decimal("0.4541")),
    ("RMPA", Decimal("0.5103")),
    ("SPNO", Decimal("0.4321")),
    ("SPSO", Decimal("0.4401")),
    ("SRMV", Decimal("0.3633")),
    ("SRMW", Decimal("0.6213")),
    ("SRSO", Decimal("0.4051")),
    ("SRTV", Decimal("0.4232")),
    ("SRVC", Decimal("0.2826")),
]


# IEA / DEFRA national electricity factors (kg CO2e/kWh, location-based)
# Used when eGRID doesn't apply (i.e. non-US).
LOCATION_GRID_BY_COUNTRY = [
    ("GB", Decimal("0.20493")),   # DEFRA 2024 UK average
    ("DE", Decimal("0.36400")),   # IEA 2023 Germany
    ("IN", Decimal("0.70820")),   # IEA 2023 India
    ("FR", Decimal("0.05500")),   # IEA 2023 France (heavy nuclear)
    ("SG", Decimal("0.40800")),   # IEA 2023 Singapore
    ("AE", Decimal("0.41600")),   # IEA 2023 UAE
    ("JP", Decimal("0.47000")),   # IEA 2023 Japan
]


# DEFRA 2024 — Air travel (kg CO2 per passenger-km, BASE — without RF).
# RF (1.7×) applied separately on calculation so disclosure is explicit.
DEFRA_2024_AVIATION = [
    # (haul, cabin, kg CO2/p.km)
    ("short", "Economy",         Decimal("0.14460")),
    ("short", "Business",        Decimal("0.21692")),
    ("long",  "Economy",         Decimal("0.08778")),
    ("long",  "Premium Economy", Decimal("0.14059")),
    ("long",  "Business",        Decimal("0.25461")),
    ("long",  "First",           Decimal("0.35106")),
]
AVIATION_RF_MULTIPLIER = Decimal("1.7")  # DEFRA 2024 current guidance.


# DEFRA 2024 — Hotel stays by country (kg CO2e per occupied room-night).
# DEFRA publishes ~60 countries; we seed the most relevant for the demo.
DEFRA_2024_HOTEL = [
    ("GB", Decimal("23.8")),
    ("US", Decimal("31.7")),
    ("DE", Decimal("23.3")),
    ("FR", Decimal("16.6")),
    ("IN", Decimal("134.3")),
    ("SG", Decimal("78.4")),
    ("JP", Decimal("70.1")),
    ("AE", Decimal("110.6")),
]


# DEFRA 2024 — Ground transport (kg CO2e per passenger-km / vehicle-km)
DEFRA_2024_GROUND = [
    # (sub_type, kg CO2e/km, notes)
    ("taxi",           Decimal("0.14869")),  # regular taxi pkm
    ("rental_average", Decimal("0.17005")),  # rental car average pkm
]
