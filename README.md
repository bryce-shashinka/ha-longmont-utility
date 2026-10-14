# Longmont Utility for Home Assistant

Unofficial Home Assistant integration for City of Longmont smart-meter
electricity consumption. It downloads the portal's daily CSV, preserves every
validated 15-minute reading locally, and imports hourly totals into Home
Assistant's Energy dashboard.

> [!CAUTION]
> This integration depends on an undocumented utility-portal workflow and may
> break when the City or its portal vendor changes the site. It is not produced,
> endorsed, or supported by the City of Longmont. Values are informational and
> are not billing-grade.

## Requirements

- Home Assistant 2026.9.1 or newer
- A City of Longmont utility portal guest account
- Exactly one electric meter per integration entry

Create a dedicated guest account in the utility portal and grant only **Smart
Meter → Electricity** permission. Do not use your primary portal credentials.
The guest portal's Home page may still reveal basic account information even
with this restricted permission, so protect the account normally.

## Installation

1. In HACS, open **Integrations**, choose the menu, then **Custom repositories**.
2. Add `https://github.com/bryce-shashinka/ha-longmont-utility` as an
   **Integration** repository.
3. Download **Longmont Utility** and restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration**, search for
   **Longmont Utility**, and enter the dedicated guest credentials.

Advanced users can alternatively copy `custom_components/longmont_utility`
into the same directory under their Home Assistant configuration and restart.

## Energy dashboard

After the first successful import, open **Settings → Dashboards → Energy** and
add the `Longmont electricity consumption` statistic as grid consumption. The
initial setup requests up to 90 complete local days. Later refreshes revisit
the seven most recent complete days once daily so portal corrections replace
previous values.

Home Assistant external long-term statistics are hourly, so four source
quarter-hours are summed for each Energy-dashboard point. The original decimal
values remain in an integration-owned, private `.storage` archive for the life
of the config entry. Raw CSV, cookies, credentials, and portal responses are not
stored there.

## Estimated cost

The integration also imports a `Longmont electricity cost` statistic in US
dollars. Select it as the grid consumption's cost ("Use an entity tracking the
total costs") in the Energy dashboard. Each quarter-hour is priced on the
City's residential (RE) schedule (2026 prices shown):

| Billing-cycle usage | Non-summer | Summer |
| --- | --- | --- |
| First 750 kWh | 10.57¢ | 11.64¢ |
| 751-1,500 kWh | 12.45¢ | 13.73¢ |
| Over 1,500 kWh | 16.18¢ | 17.83¢ |

Prices include the 8.64 percent franchise fee. The $17.50 monthly customer
charge is spread evenly over the hours of each billing cycle. Tiers reset at
the start of each billing cycle; set the cycle's start day under the
integration's **Configure** options. Use the first date of the period printed
on your bill: "Residential Energy Charges 08/19/26 to 09/18/26" means 19.

Summer pricing follows the City's "bills read June-September": a cycle is
summer when its last day (the read date) falls in June through September. With
a 19th start day, the cycles ending June 18 through September 18 are summer.

### Rate updates

Once a day the integration reads the City's
[residential rates page](https://longmontcolorado.gov/longmont-power-communications/rates-and-fees/residential-rates/),
strictly validates the RE table (three tiers, increasing boundaries and
prices, summer at or above non-summer, plausible ranges), and keeps the result
in a private `.storage` file. When the published prices change, the new
schedule takes effect from a date stated on the page or, when the page states
none, from the day it was first seen. The cost statistic is recalculated and a
repair notice says so. If the page cannot be read or validated for seven
consecutive days, a repair notice says costs are using the last known rates.
Built-in 2026 prices in `tariff.py` remain the fallback.

The diagnostic **Electricity rate** sensor shows the price of the next kWh at
the current billing-cycle position, with the tier, season, cycle dates,
cycle-to-date usage, full tier table, and when the rates were last checked.

This is an estimate, not a bill: actual cycle lengths, proration, and the
City's read dates differ.

## Expected behavior and limitations

- Utility data commonly trails real time by a day; this is not a live power
  monitor.
- Electricity consumption and an estimated RE-rate cost only. It does not
  import water, generation, or actual bills.
- Ordinary dates must contain 96 readings. DST transition dates are rejected
  rather than guessed because the export does not disambiguate them.
- Invalid or internally inconsistent rows are not imported.
- The portal's non-data `* Note:` footer is ignored; other malformed rows still
  fail validation and leave the prior archive unchanged.
- Expired credentials trigger Home Assistant's reauthentication flow.
- Portal outages preserve previously imported data and are retried later.

The three diagnostic sensors report the last successful update, latest utility
interval, and data age. Downloadable diagnostics omit credentials and all
portal account and meter identifiers.

## Removal and support

Removing the integration entry also deletes its retained 15-minute source
archive. Home Assistant may retain previously imported long-term statistics;
remove those through Home Assistant's statistics tools if desired.

Please report integration defects through the repository issue tracker. For
billing questions, account access, or incorrect official usage, contact City of
Longmont Utility Billing instead.

## Development

```bash
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/ruff check custom_components tests
.venv/bin/mypy
.venv/bin/python -m pytest tests -q
```

Synthetic fixtures are used throughout the test suite. Never add captured
portal pages, real exports, credentials, or private account identifiers.

## License

MIT
