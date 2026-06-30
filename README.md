# MTG Vault

A single-user Magic: The Gathering card & deck manager. Django + SQLite + Tailwind, run via Docker.

## Run

```bash
cp .env.example .env        # adjust FX rate + Scryfall User-Agent contact
docker compose up --build
```

Open http://localhost:8000 — it redirects to the Vault. Data (SQLite DB + downloaded
Scryfall bulk file) persists in the `mtg_data` volume across rebuilds.

## Concepts

- **The Vault** — cards you deliberately add and tag (your reference library). "Recently
  Added" reflects only these.
- **Decks** — decklists for tracking which cards you own vs. still need to buy. Cards pulled
  in by a deck import do **not** appear in the Vault.

A `Card` row stores Scryfall data for one unique card (one per name). It's created on demand
for either space; the `in_vault` flag is what marks Vault membership.

## Common tasks

- **Add a card:** "+ Add card" → name (fuzzy match on by default). Data/price from Scryfall.
- **Build a deck:** "+ New deck" with an optional paste-to-import box. Edit later via
  "Edit decklist (bulk)" — saving replaces contents but keeps your owned/category flags.
- **Set a commander:** hover a card in the deck and click ⭐.
- **Refresh prices:** `docker compose run --rm sync` (downloads the Scryfall bulk file and
  updates tracked cards; never touches tags or Vault membership).
- **Export a deck:** "Export (plain text)" → copy into Moxfield/Arena.

## Pricing note

Scryfall provides USD only. CAD is computed from `FX_RATE_USD_CAD` in `.env`; update it
occasionally.

## Tests

```bash
docker compose run --rm web python manage.py test
```

## Admin (optional)

```bash
docker compose run --rm web python manage.py createsuperuser
```
Then visit http://localhost:8000/admin/.
