#!/usr/bin/env python3
"""Generate construction-industry leads in Bali from the Google Places API (New).

Searches Google Maps for businesses likely to need (or refer) villa /
hospitality construction work in Bali — villa operators, villa management
companies, property developers, real-estate agencies, boutique hotels &
resorts, architecture / interior design studios, and property investment
firms — then writes a deduplicated CSV of leads with name, phone, address,
website, rating, and category.

API budget: every HTTP request to Google counts as one call. The script
hard-aborts once --max-calls is reached (default 1000) and stops early as
soon as --target unique leads (default 1000) are collected.

Usage:
    export GOOGLE_MAPS_API_KEY=AIza...
    python3 generate_leads.py                 # full run
    python3 generate_leads.py --dry-run       # print query plan, no API calls
    python3 generate_leads.py --target 200 --max-calls 100

Note on data use: per the Google Maps Platform Terms of Service, Places
content other than place IDs should not be cached for more than 30 days.
Treat the generated CSV as a working outreach list, not a permanent database.
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

FIELD_MASK = ",".join(
    [
        "nextPageToken",
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.internationalPhoneNumber",
        "places.nationalPhoneNumber",
        "places.websiteUri",
        "places.rating",
        "places.userRatingCount",
        "places.types",
        "places.primaryType",
        "places.googleMapsUri",
        "places.businessStatus",
        "places.location",
    ]
)

# Rectangle around Bali (incl. Nusa Penida / Lembongan) so results outside
# the island are rejected server-side even if a query matches elsewhere.
BALI_RECTANGLE = {
    "rectangle": {
        "low": {"latitude": -8.92, "longitude": 114.42},
        "high": {"latitude": -8.04, "longitude": 115.75},
    }
}

# Areas with the highest villa / hospitality construction activity, roughly
# ordered by market activity so the most productive queries run first.
AREAS = [
    "Canggu", "Berawa", "Pererenan", "Seminyak", "Umalas", "Kerobokan",
    "Ubud", "Uluwatu", "Bingin", "Ungasan", "Jimbaran", "Nusa Dua",
    "Sanur", "Kuta", "Legian", "Denpasar", "Tabanan", "Munggu",
    "Kedungu", "Amed", "Candidasa", "Lovina", "Sidemen", "Nusa Lembongan",
]

# (category, why it is a lead for a construction company, list of query templates)
# "{area}" templates fan out across AREAS; plain strings run once island-wide.
CATEGORIES = [
    (
        "property_developer",
        "Builds villa/resort projects; direct client for construction contracts",
        [
            "property developer in Bali",
            "real estate development company in Bali",
            "villa developer in {area}, Bali",
        ],
    ),
    (
        "villa_management",
        "Manages portfolios of villas; refers renovation and build work",
        [
            "villa management company in Bali",
            "villa management company in {area}, Bali",
        ],
    ),
    (
        "real_estate_agency",
        "Sells land and off-plan villas; refers buyers who need a builder",
        [
            "real estate agency in {area}, Bali",
            "land for sale real estate agency in Bali",
        ],
    ),
    (
        "architecture_design",
        "Designs villas; natural partner that brings construction clients",
        [
            "architecture firm in Bali",
            "architect studio in {area}, Bali",
            "interior design studio in Bali",
        ],
    ),
    (
        "property_investment",
        "Funds hospitality projects; commissions new builds",
        [
            "property investment company in Bali",
            "hospitality investment company in Bali",
        ],
    ),
    (
        "villa_owner_operator",
        "Existing villa owner/operator; renovation, extension and rebuild client",
        [
            "villa in {area}, Bali",
            "luxury private villa in {area}, Bali",
            "villa rental in {area}, Bali",
        ],
    ),
    (
        "hospitality_business",
        "Hotels, resorts and beach clubs; expansion and refurbishment client",
        [
            "boutique hotel in {area}, Bali",
            "resort in {area}, Bali",
            "beach club in Bali",
            "glamping resort in Bali",
        ],
    ),
]

KEY_ENV_VARS = [
    "GOOGLE_MAPS_API_KEY",
    "GOOGLE_MAPS_API",
    "GOOGLE_API_KEY",
    "MAPS_API_KEY",
    "GOOGLE_PLACES_API_KEY",
]


class CallBudgetExceeded(Exception):
    pass


def get_api_key():
    for var in KEY_ENV_VARS:
        value = os.environ.get(var, "").strip()
        # Ignore proxy placeholders and obviously non-key values.
        if value and value != "proxy-injected":
            return value, var
    return None, None


def build_query_plan():
    """Expand category templates into an ordered list of unique queries."""
    plan = []
    seen = set()
    for category, why, templates in CATEGORIES:
        for template in templates:
            queries = (
                [template.format(area=a) for a in AREAS]
                if "{area}" in template
                else [template]
            )
            for q in queries:
                if q not in seen:
                    seen.add(q)
                    plan.append((category, why, q))
    return plan


class PlacesClient:
    def __init__(self, api_key, max_calls):
        self.api_key = api_key
        self.max_calls = max_calls
        self.calls = 0

    def search_text(self, query, page_token=None):
        if self.calls >= self.max_calls:
            raise CallBudgetExceeded(
                f"API call budget of {self.max_calls} reached — aborting as requested."
            )
        body = {"textQuery": query, "pageSize": 20, "locationRestriction": BALI_RECTANGLE}
        if page_token:
            body["pageToken"] = page_token
        request = urllib.request.Request(
            SEARCH_URL,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": FIELD_MASK,
            },
            method="POST",
        )
        for attempt in range(4):
            self.calls += 1
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    return json.loads(response.read())
            except urllib.error.HTTPError as error:
                detail = error.read().decode(errors="replace")[:500]
                if error.code in (401, 403) or "API_KEY_INVALID" in detail:
                    sys.exit(
                        f"FATAL: Google rejected the API key ({error.code}).\n{detail}\n"
                        "Check that the key is valid and the 'Places API (New)' is "
                        "enabled for its Google Cloud project."
                    )
                if error.code in (429, 500, 502, 503) and attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"HTTP {error.code} for query '{query}': {detail}")
            except urllib.error.URLError as error:
                if attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"Network error for query '{query}': {error}")
        raise RuntimeError(f"Retries exhausted for query '{query}'")


def place_to_lead(place, category, why, query):
    return {
        "name": (place.get("displayName") or {}).get("text", ""),
        "phone": place.get("internationalPhoneNumber")
        or place.get("nationalPhoneNumber", ""),
        "address": place.get("formattedAddress", ""),
        "website": place.get("websiteUri", ""),
        "google_maps_url": place.get("googleMapsUri", ""),
        "rating": place.get("rating", ""),
        "review_count": place.get("userRatingCount", ""),
        "business_status": place.get("businessStatus", ""),
        "primary_type": place.get("primaryType", ""),
        "lead_category": category,
        "why_relevant": why,
        "found_via_query": query,
        "latitude": (place.get("location") or {}).get("latitude", ""),
        "longitude": (place.get("location") or {}).get("longitude", ""),
        "place_id": place.get("id", ""),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", type=int, default=1000, help="unique leads to collect")
    parser.add_argument("--max-calls", type=int, default=1000, help="hard API call budget")
    parser.add_argument("--max-pages", type=int, default=3, help="pages per query (20 results each)")
    parser.add_argument("--out", default="leads_bali_construction.csv", help="output CSV path")
    parser.add_argument("--dry-run", action="store_true", help="print the query plan and exit")
    args = parser.parse_args()

    plan = build_query_plan()
    if args.dry_run:
        print(f"Query plan: {len(plan)} queries, worst case "
              f"{len(plan) * args.max_pages} API calls (early-stops at "
              f"{args.target} leads / {args.max_calls} calls).")
        for category, _why, query in plan:
            print(f"  [{category}] {query}")
        return

    api_key, key_var = get_api_key()
    if not api_key:
        sys.exit(
            "FATAL: no Google Maps API key found. Set one of: "
            + ", ".join(KEY_ENV_VARS)
        )
    print(f"Using API key from ${key_var}. Budget: {args.max_calls} calls, "
          f"target: {args.target} leads, {len(plan)} queries planned.")

    client = PlacesClient(api_key, args.max_calls)
    leads = {}  # place_id -> lead row
    aborted = None

    try:
        for index, (category, why, query) in enumerate(plan, 1):
            if len(leads) >= args.target:
                break
            page_token = None
            new_here = 0
            for _page in range(args.max_pages):
                data = client.search_text(query, page_token)
                for place in data.get("places", []):
                    pid = place.get("id")
                    if pid and pid not in leads:
                        leads[pid] = place_to_lead(place, category, why, query)
                        new_here += 1
                page_token = data.get("nextPageToken")
                if not page_token or len(leads) >= args.target:
                    break
                time.sleep(0.2)
            print(f"[{index}/{len(plan)}] {query!r}: +{new_here} new "
                  f"(total {len(leads)}, calls {client.calls}/{args.max_calls})")
    except CallBudgetExceeded as error:
        aborted = str(error)
        print(f"\nABORT: {aborted}")
    except KeyboardInterrupt:
        aborted = "interrupted by user"

    rows = sorted(
        leads.values(),
        key=lambda r: (r["phone"] == "", r["lead_category"], r["name"]),
    )
    fieldnames = list(rows[0].keys()) if rows else []
    with open(args.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with_phone = sum(1 for r in rows if r["phone"])
    with_site = sum(1 for r in rows if r["website"])
    print(f"\nWrote {len(rows)} unique leads to {args.out} "
          f"({with_phone} with phone, {with_site} with website) "
          f"using {client.calls} API calls.")
    by_category = {}
    for row in rows:
        by_category[row["lead_category"]] = by_category.get(row["lead_category"], 0) + 1
    for category, count in sorted(by_category.items(), key=lambda kv: -kv[1]):
        print(f"  {category}: {count}")
    if aborted:
        print(f"Run ended early: {aborted}")


if __name__ == "__main__":
    main()
