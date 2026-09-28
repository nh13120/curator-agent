# Trusted source list: proposal (Phase 9)

Status: **proposal for Nicolas's approval.** Verified by live fetch on 2026-09-26. Once approved, `config/sources.yaml` is updated to match; the scout only searches sources listed there. "html" means event titles and dates are visible in the fetched text (the scout's `fetch.py` can read it); "js" means the page needs a browser to render.

## AI and tech (Boston/Cambridge)

| Priority | Source | URL | Scrapable | Free? | Why trust it |
|---|---|---|---|---|---|
| 1 | MIT Events Calendar (JSON API) | `https://calendar.mit.edu/api/2/events?pp=100&days=30` | JSON, per-event `free` flag and `ticket_cost` | explicit per event | Institute-wide; covers CSAIL, EECS, Media Lab, List Center and MIT Museum via department and type filters |
| 1 | MIT Calendar, "artificial intelligence" search | `https://calendar.mit.edu/search/events?search=artificial+intelligence` (ICS: `/search/events.ics?search=...`) | html + ICS | see above | Same data, pre-filtered |
| 1 | MIT Calendar, lectures and seminars | `https://calendar.mit.edu/calendar?event_types%5B%5D=102764` (ICS available) | html + ICS | see above | Catches talks across all departments |
| 2 | MIT CSAIL events | `https://www.csail.mit.edu/events` (ICS: `/event_calendar.ics`) | html with a browser user agent | mostly open to the MIT community, unverified per event | The lab most relevant to AI talks |
| 2 | MIT Schwarzman College of Computing | `https://calendar.mit.edu/department/mit_schwarzman_college_of_computing/calendar` | html + ICS | see MIT calendar | The college's official feed (its own events page is dead) |
| 2 | Harvard SEAS events | `https://events.seas.harvard.edu/` (ICS: `/calendar/1.ics`) | html + ICS | mostly free academic talks, unverified per event | Official Localist calendar, 100+ events |
| 2 | Harvard Berkman Klein Center | `https://cyber.harvard.edu/events` | html | historically free, unverified on page | Strong AI-policy pipeline |
| 2 | Harvard Kennedy School events | `https://www.hks.harvard.edu/events` | html | often "open to Harvard ID", check per event | High volume of AI and policy seminars |
| 2 | Harvard Radcliffe Institute | `https://www.radcliffe.harvard.edu/events` | html | "free and open to the public unless otherwise noted" (verbatim) | Strong AI-and-humanities lectures |
| 3 | Harvard Data Science Initiative | `https://datascience.harvard.edu/events/` | html | unverified | Faculty AI seminar, industry talks |
| 3 | BU Computing & Data Sciences calendar | `https://www.bu.edu/cds-faculty/stay-connected/calendar/` | html | unverified | Spark! panels usually open |
| 3 | Venture Café Cambridge | `https://venturecafecambridge.org/events/` | html | "free and open to everyone" (site) | Weekly Thursday gatherings, many AI sessions |
| 3 | Luma Boston | `https://luma.com/boston` | html (server-rendered) | per event | Dominant platform for Boston AI meetups |
| 3 | Meetup, AI near Boston | `https://www.meetup.com/find/?keywords=artificial%20intelligence&location=us--ma--Boston` | html (JSON-LD in page) | per event | Aggregator; per-group ICS at `meetup.com/<group>/events/ical/` |
| 3 | PyData Boston-Cambridge | `https://www.meetup.com/pydata-boston-cambridge/` | html + ICS | usually free | Active, 3.4k members |
| 4 | Eventbrite, free AI events | `https://www.eventbrite.com/d/ma--boston/free--artificial-intelligence/` | inconsistent (anti-bot) | URL filters price = free | Broad but unreliable to fetch; last resort |
| 4 | AI Tinkerers Boston | `https://boston.aitinkerers.org/` | html | no price; attendees are screened ("apply to attend") | Real and active, but not open-door: ask-first only |
| skip | MIT Sloan events, Northeastern Experiential AI, MIT EECS page | | html | | Admissions noise or two events; covered by the MIT calendar anyway |

## Art (Boston/Cambridge)

| Priority | Source | URL | Scrapable | Free? | Why trust it |
|---|---|---|---|---|---|
| 1 | MIT Calendar, arts and exhibits | `https://calendar.mit.edu/calendar?event_types%5B%5D=102755` (Arts/Music/Film), `...=102763` (Exhibits), `...=102757` (MIT Museum) | html + ICS | explicit per event | Same institute calendar; List Center and MIT Museum cross-post here |
| 1 | MFA Boston programs | `https://www.mfa.org/programs` | html | MIT and Harvard are University Members: free ticketed admission for students with ID | Major museum, frequent talks and openings |
| 1 | ICA Boston events | `https://www.icaboston.org/events` | html | Free Thursday nights 5–9 pm; MIT (code MITICA) and Harvard (HUICA) university members get free general admission | Many events tagged free |
| 1 | MIT List Visual Arts Center | `https://listart.mit.edu/calendar` | html | free museum (unstated on the calendar page) | Official; also on the MIT calendar |
| 2 | Harvard Art Museums | `https://harvardartmuseums.org/calendar` | js only | admission free to all visitors | Free museum, but the calendar needs the browser; scout falls back to the MIT/Harvard Gazette listings |
| 2 | Harvard Gazette events | `https://news.harvard.edu/gazette/harvard-events/` | html, few per page | mixed | University-wide aggregator (the old events.harvard.edu is blocked) |
| 2 | Tufts University Art Galleries / SMFA | `https://artgalleries.tufts.edu/events` | html | galleries free and open to all | Official, dated event list |
| 2 | Boston Center for the Arts | `https://bostonarts.org/experiences/` | html | mixed (RSVP vs tickets) | Official; check price per event |
| 2 | ArtsBoston BosTix, free category | `https://bostix.org/categories/free-events/` | html | category is explicitly free | Regional aggregator |
| 3 | Boston Public Library events | `https://bpl.bibliocommons.com/events/` | html | library programming is free (unstated) | Official |
| 3 | SoWa First Fridays / SoWa Artists Guild | `https://www.sowaboston.com/first-fridays/`, `https://www.sowaartists.com/events` | html | first Friday 5–9 pm and Sunday open studios, free | Recurring, reliable |
| 3 | Fort Point Arts Community | `https://www.fortpointarts.org/events` | html (calendar widget partly broken) | open studios free | Official |
| 3 | Cambridge Arts Council | `https://www.cambridgema.gov/arts/Calendar` (ICS available) | partial html + ICS | city programs generally free | Official city calendar |
| policy only | Isabella Stewart Gardner | `https://www.gardnermuseum.org/join-give/university-membership` | calendar blocked (403) | MIT and Harvard students free with ID via timed ticket and school code | Keep as a policy reference; events must come from other listings |

## Feeds worth using directly (all returned content on 2026-09-26)

- MIT: `https://calendar.mit.edu/calendar/1.ics`, `https://calendar.mit.edu/calendar/1.xml`, JSON `https://calendar.mit.edu/api/2/events?pp=100&days=30` (departments list at `/api/2/departments?pp=200`: CSAIL 10125, EECS 14796, Media Lab 18866).
- Harvard SEAS: `https://events.seas.harvard.edu/calendar/1.ics`.
- CSAIL: `https://www.csail.mit.edu/event_calendar.ics`.
- Cambridge Arts: `https://www.cambridgema.gov/arts/Calendar.ics`.
- Meetup groups: `https://www.meetup.com/<group>/events/ical/`.

## Fallback for other cities (travel weeks)

Everything found this way goes to the ask-first tier, as the brief requires.

1. University calendars on Localist: `https://<calendar host>/api/2/events?days=30&pp=100` (JSON with a `free` flag) or `/calendar/1.ics`; search feeds at `/search/events.ics?search=<keyword>`.
2. Luma: `https://luma.com/<city>` (nyc, sf, la, seattle, and so on), server-rendered.
3. Meetup: `https://www.meetup.com/find/?keywords=<kw>&location=us--<st>--<City>`.
4. Eventbrite free filter: `https://www.eventbrite.com/d/<state>--<city>/free--<keyword>/` (needs retries; the browser can render it if the fetch tool is blocked).
5. Library and arts aggregators: `https://<library>.bibliocommons.com/events/`, local "free events" categories.
6. Venture Café network for Thursday gatherings (St. Louis, Miami, Philadelphia, Providence).

## Dropped

Boston Athenaeum (JavaScript-only, mostly members or ticketed), Cambridge Art Association (calendar stale since 2017), the dead pages `computing.mit.edu/events`, `events.harvard.edu`, `seas.harvard.edu/events`, `listart.mit.edu/events`, `bostonarts.org/events`, and the MIT Museum programs page (bot checkpoint; its events are on the MIT calendar instead).

## Two implementation notes for the scout

- The MIT calendar JSON is the best single source: an explicit `free` boolean per event, so the price label is not guessed from prose.
- Some sites block one fetcher and not another: `csail.mit.edu` refuses the fetch tool but accepts a browser user agent; Eventbrite is the reverse. `tools/fetch.py` already sends a browser-like user agent; the browser remains the fallback for JavaScript-only pages.
