# Bali Construction Lead Generation

Generates a CSV of up to 1,000 sales leads for a Bali villa / hospitality
construction company by querying the **Google Places API (New)** for
businesses on the island that build, own, manage, sell, design, or fund
villas and hospitality real estate.

## Lead categories searched

| Category | Why it's a lead |
|---|---|
| `property_developer` | Builds villa/resort projects — direct construction client |
| `villa_management` | Manages villa portfolios — refers renovation & build work |
| `real_estate_agency` | Sells land & off-plan villas — refers buyers needing a builder |
| `architecture_design` | Designs villas — partner channel that brings clients |
| `property_investment` | Funds hospitality projects — commissions new builds |
| `villa_owner_operator` | Existing villa owners/operators — renovation & extension clients |
| `hospitality_business` | Hotels, resorts, beach clubs — expansion & refurbishment clients |

Searches fan out across the high-activity areas: Canggu, Berawa, Pererenan,
Seminyak, Umalas, Kerobokan, Ubud, Uluwatu, Bingin, Ungasan, Jimbaran,
Nusa Dua, Sanur, Kuta, Legian, Denpasar, Tabanan, Munggu, Kedungu, Amed,
Candidasa, Lovina, Sidemen, and Nusa Lembongan, with a geographic
restriction to Bali's bounding box so no off-island results slip in.

## Setup

The script needs a Google Maps API key with **Places API (New)** enabled,
provided as an environment variable (any of these names works):

```
GOOGLE_MAPS_API_KEY   (preferred)
GOOGLE_MAPS_API
GOOGLE_API_KEY
MAPS_API_KEY
GOOGLE_PLACES_API_KEY
```

> Environment-secret names cannot contain spaces — a secret saved as
> "Google Maps API" will not reach the session. Save it as
> `GOOGLE_MAPS_API_KEY` instead.

## Run

```bash
python3 lead-generation/generate_leads.py                # full run: 1,000 leads
python3 lead-generation/generate_leads.py --dry-run      # show query plan, no API calls
python3 lead-generation/generate_leads.py --target 200 --max-calls 100
```

Output: `leads_bali_construction.csv` with columns
`name, phone, address, website, google_maps_url, rating, review_count,
business_status, primary_type, lead_category, why_relevant,
found_via_query, latitude, longitude, place_id` — sorted so leads with
phone numbers come first.

## API usage & cost control

- Every HTTP request = 1 API call. The script **hard-aborts at
  `--max-calls` (default 1,000)** and writes whatever it has collected.
- It also stops as soon as `--target` (default 1,000) unique leads are
  found — typically ~200–400 calls, well under budget.
- Each query fetches at most 3 pages × 20 results.
- Pricing: phone/website fields put requests in the Text Search
  Enterprise SKU (~US$35 per 1,000 calls), so a full run typically costs
  roughly US$7–14 depending on how quickly the target is reached.

## Data-use note

Per the Google Maps Platform Terms of Service, Places content other than
place IDs should not be cached longer than 30 days. Treat the CSV as a
working outreach list and refresh it rather than archiving it permanently.
