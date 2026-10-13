"""Constants for the Longmont Utility integration."""

from decimal import Decimal

DOMAIN = "longmont_utility"
INTEGRATION_VERSION = "0.2.0"
PORTAL_BASE_URL = "https://myutilityaccount.longmontcolorado.gov"
PORTAL_TIME_ZONE = "America/Denver"
INTERVALS_PER_ORDINARY_DAY = 96
TOTAL_TOLERANCE_KWH = Decimal("0.001")

CONF_ACCOUNT_REF = "account_ref"
CONF_METER_REF = "meter_ref"
CONF_STATISTIC_SUFFIX = "statistic_suffix"
CONF_BILLING_CYCLE_START_DAY = "billing_cycle_start_day"
DEFAULT_BILLING_CYCLE_START_DAY = 1

SOURCE_STORE_VERSION = 1
INITIAL_IMPORT_DAYS = 90
REFRESH_DAYS = 7
