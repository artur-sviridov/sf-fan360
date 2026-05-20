# Attributions

This project consumes free, publicly-available football data. Every source is credited below per its respective terms.

## Match results (historical, 2010/11-present)

**OpenFootball / football.json** - public domain under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). No attribution legally required; we credit anyway out of respect.
Repository: [https://github.com/openfootball/football.json](https://github.com/openfootball/football.json).

## xG and shot data (EPL 2014/15 to current)

**Understat** ([https://understat.com](https://understat.com)) - accessed via the `[understatapi](https://pypi.org/project/understatapi/)` Python package.
Scraping is rate-limited to <=1 req/s with the User-Agent `fan360-bot/0.1 (contact: see-repo-readme)`. We do not republish
Understat data outside the private GCP project.

## Live fixtures, scores, league tables

**football-data.org** ([https://www.football-data.org](https://www.football-data.org)) - free tier, attribution requested.

## Live player events (matchdays)

**Fantasy Premier League Bootstrap API** (`https://fantasy.premierleague.com/api/bootstrap-static/`) - unofficial, no published terms. Used at low frequency (>=60 s between calls) with the same identified User-Agent. No commercial use.

## Live match events (optional, 100 req/day cap)

**API-Football** (api-sports) - [https://www.api-football.com/](https://www.api-football.com/); register and manage keys at [https://dashboard.api-football.com/](https://dashboard.api-football.com/). Free tier used under their published terms (typically 100 requests/day).

## Logos, badges, player photos (UI only)

**TheSportsDB** ([https://www.thesportsdb.com](https://www.thesportsdb.com)) - free for non-commercial use with attribution.

## Tactical context, biographies, manager narratives

**Wikipedia** ([https://en.wikipedia.org](https://en.wikipedia.org)) - articles used under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Each ingested article retains its source URL as a citation. Snippets surfaced by the agent display the source URL.

**Wikidata** ([https://www.wikidata.org](https://www.wikidata.org)) - structured facts used under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/).

## Trademark notice

"Premier League", "EPL", club names, club crests, and player names are trademarks of their respective owners (The Football Association Premier League Ltd., the individual clubs, and the players themselves). This is an unaffiliated, non-commercial portfolio project. No endorsement is implied or claimed.

If you are a rightsholder and have a concern about how your data, logo, or trademark appears here, please open an issue on the GitHub repository and we will respond within 7 days.
