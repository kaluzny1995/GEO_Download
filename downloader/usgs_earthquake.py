from __future__ import annotations

import datetime as dt
import re

from downloader.base import BaseDownloader
from reverse_geocode import stamp_geocode

# The place suffixes that answer the country without a geocode: the US state
# codes and full names plus the mapped country names of GEO_ETL's
# single_etl/usgs_earthquake_etl.py (US_STATE_CODES, US_STATE_FULL_NAMES,
# COUNTRY_CODE_MAP). Keep the two lists in sync — the ETL prefers the parsed
# suffix over the stamped answer, so a suffix missing here is geocoded for
# nothing, and a suffix missing there loses the geocode it used to make.
KNOWN_SUFFIXES: frozenset[str] = frozenset(
    (
        "AK",
        "AL",
        "AR",
        "AS",
        "AZ",
        "Afghanistan",
        "Alabama",
        "Alaska",
        "Albania",
        "Anguilla",
        "Argentina",
        "Arizona",
        "Arkansas",
        "Austria",
        "Azerbaijan",
        "Bhutan",
        "Bolivia",
        "CA",
        "CO",
        "CT",
        "California",
        "Canada",
        "Chile",
        "China",
        "Colombia",
        "Colorado",
        "Connecticut",
        "Costa Rica",
        "DC",
        "DE",
        "Delaware",
        "Dominican Republic",
        "Ecuador",
        "El Salvador",
        "Ethiopia",
        "FL",
        "Fiji",
        "Florida",
        "GA",
        "GU",
        "Georgia",
        "Greece",
        "Guam",
        "Guatemala",
        "HI",
        "Haiti",
        "Hawaii",
        "IA",
        "ID",
        "IL",
        "IN",
        "Idaho",
        "Illinois",
        "India",
        "Indiana",
        "Indonesia",
        "Iowa",
        "Iran",
        "Italy",
        "Japan",
        "Japan region",
        "KS",
        "KY",
        "Kansas",
        "Kazakhstan",
        "Kentucky",
        "LA",
        "Lebanon",
        "Libya",
        "Louisiana",
        "MA",
        "MD",
        "ME",
        "MI",
        "MN",
        "MO",
        "MP",
        "MS",
        "MT",
        "MX",
        "Maine",
        "Martinique",
        "Maryland",
        "Massachusetts",
        "Mexico",
        "Michigan",
        "Minnesota",
        "Mississippi",
        "Missouri",
        "Montana",
        "NC",
        "ND",
        "NE",
        "NH",
        "NJ",
        "NM",
        "NV",
        "NY",
        "Nebraska",
        "Nepal",
        "Nevada",
        "New Caledonia",
        "New Hampshire",
        "New Jersey",
        "New Mexico",
        "New York",
        "New Zealand",
        "North Carolina",
        "North Dakota",
        "Northern Mariana Islands",
        "OH",
        "OK",
        "OR",
        "Ohio",
        "Oklahoma",
        "Oregon",
        "PA",
        "PR",
        "Panama",
        "Papua New Guinea",
        "Pennsylvania",
        "Peru",
        "Philippines",
        "Puerto Rico",
        "RI",
        "Rhode Island",
        "Romania",
        "Russia",
        "SC",
        "SD",
        "Saint Eustatius and Saba",
        "Saint Helena",
        "Solomon Islands",
        "Somalia",
        "South Carolina",
        "South Dakota",
        "Spain",
        "Svalbard and Jan Mayen",
        "TN",
        "TX",
        "Taiwan",
        "Tajikistan",
        "Tennessee",
        "Texas",
        "Timor Leste",
        "Tonga",
        "Turkey",
        "U.S. Virgin Islands",
        "UT",
        "Utah",
        "VA",
        "VI",
        "VT",
        "Vanuatu",
        "Venezuela",
        "Vermont",
        "Virginia",
        "WA",
        "WI",
        "WV",
        "WY",
        "Wallis and Futuna",
        "Washington",
        "West Virginia",
        "Wisconsin",
        "Wyoming",
        "Yemen",
    )
)


def _place_suffix(place: str | None) -> str:
    """The token after the last ``,`` of *place* (trimmed), ``""`` when there is none.

    Mirrors ``_place_suffix`` in GEO_ETL's ``single_etl/usgs_earthquake_etl.py``:
    ``"CA"`` from ``9 km WSW of Idyllwild, CA``, ``"Chile"`` from an
    international place, ``""`` for a bare Flinn-Engdahl region.
    """
    match = re.search(r", ([^,]*)$", place or "")
    return match.group(1).strip() if match else ""


def _country_known(place: str | None) -> bool:
    """Whether the place suffix alone answers the country — those rows skip the geocode.

    Mirrors ``_country_known`` in GEO_ETL's ``single_etl/usgs_earthquake_etl.py``:
    a suffix in :data:`KNOWN_SUFFIXES` answers from the parsed text, anything
    else (including a missing suffix) needs the stamped reverse-geocode pair.
    """
    return _place_suffix(place) in KNOWN_SUFFIXES


class USGSEarthquakeDownloader(BaseDownloader):
    """Downloads earthquake data from the USGS FDSN Event Query API.

    Epicentres whose ``place`` suffix cannot answer the country are
    reverse-geocoded into ``geocode_country``/``geocode_state`` (shared lookup
    ``data/reverse_geocode.csv``) — the same ~93 remote oceanic events the ETL
    used to look up itself; rows with a US or mapped-country suffix are
    stamped with empty strings, which the ETL never reads because the parsed
    suffix wins.
    """

    __slots__ = ()

    def download_by_date_range(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """Download earthquake data for a specific date range."""
        start_str = self._format_date(start_date)
        end_str = self._format_date(end_date)

        url = f"{base_url}?format=csv&starttime={start_str}&endtime={end_str}"
        self.logger.info(f"Downloading earthquake data for period: {start_str} to {end_str}")

        records = self._download_csv(url)
        stamp_geocode(
            records,
            output=self.reverse_geocode_file,
            fetch_filter=lambda record: not _country_known(record.get("place")),
            logger=self.logger,
        )
        return records
