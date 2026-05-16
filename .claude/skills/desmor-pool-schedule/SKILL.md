---
name: desmor-pool-schedule
description: Use when the user asks about open hours / "horário livre" at the Desmor / Escola de Natação de Rio Maior pool (50m, 25m, or learning tank). Do NOT use for other pools the user may visit. Looks up the current week's free-swim schedule from desmor.pt with a one-week cache.
---

# Pool schedule (Desmor — Rio Maior)

The user swims at the Escola de Natação de Rio Maior (Desmor). Each Thursday, `secretaria.piscinas@desmor.pt` emails a one-week "Horário Livre" PDF covering Mon–Sat (the pool is closed Sunday). The same PDF is published on https://desmor.pt/conte.php?a=42.

The default pool of interest is **50m (PISCINA DE 50 METROS)**. Only mention other pools if the user asks or the 50m is closed and a fallback is useful.

## Workflow

The design priority is **fast first response**: corrections are rare, so don't make the user wait on a Gmail roundtrip. Answer from cache (which already has previously-applied corrections), then check for new corrections, then issue a brief follow-up only if the answer changed.

1. **Resolve "today"** in Europe/Lisbon: `TZ=Europe/Lisbon date +%Y-%m-%d` and `TZ=Europe/Lisbon date +%u` (1=Mon … 7=Sun). Use this date, not the system context date, in case the user is travelling.
2. **Load schedule** — pick one of:
   - **Fast path (common):** cache exists at `~/.claude/skills/desmor-pool-schedule/cache/current.json` and `week_start <= today <= week_end`. Use it.
   - **Slow path:** no cache or stale → refresh from source first:
     - Scrape `https://desmor.pt/conte.php?a=42` for the link whose href starts with `filecont/Horario_Livre-`. Build the full URL: `https://desmor.pt/<href>`. Do **not** guess the URL — the suffix (`-V-v1`, `-v2`, etc.) changes.
     - `curl -sSL -o /tmp/horario_livre.pdf "<url>"` then `Read` the PDF. The model reads the table directly.
     - Parse into the cache structure below and write `current.json` (with empty `date_overrides` and `applied_corrections`). Also write a dated copy `cache/<week_start>.json` for history.
3. **Compute the initial answer** for the asked-about `(date, pool)` using the merged view:
   - If `date_overrides[D][P]` exists, use it; otherwise use `pools[P].schedule[weekday_of_D]`.
   - Default pool is 50m. Default date is today.
   - Remember this answer as `initial_slots` for comparison in step 5.
4. **Reply to the user immediately** with `initial_slots`:
   - Format example: *"50m today (Fri): 11:30–12:30 and 17:30–19:30"*.
   - If the slots came from an override, mention it briefly: *"(adjusted per email 12 May)"*.
   - If the pool is closed (e.g. Sunday), say so and give the next opening.
   - If the user asked about now-vs-open, compare current time to today's effective slots.
   - Add the "may change without notice" disclaimer only if the user is clearly making plans.
   - Do **not** announce that you're about to check for corrections. The recheck happens silently, and we only follow up if something actually changed (see step 6).
5. **Now check Gmail for new correction emails** (do this AFTER replying):
   - Search: `mcp__claude_ai_Gmail__search_threads` with query `from:secretaria.piscinas@desmor.pt after:{week_start_in_YYYY/MM/DD}`. Note Gmail uses `/` separators in dates.
   - Filter out the weekly schedule email itself: ignore any thread whose subject starts with `Horário Livre - ` (those are the PDF announcements, not corrections).
   - For each remaining thread whose **message id is not already in `applied_corrections[].message_id`**:
     - `get_thread` with `messageFormat: FULL_CONTENT` to read the body.
     - Interpret the Portuguese text. Corrections typically say something like *"devido a [reason], a Piscina de 50m estará encerrada no dia 14 de maio das 11:30 às 12:30"* or *"alteração: o horário de sábado passa para 12:00-13:00"*.
     - For each affected `(date, pool)` pair, write the **complete replacement list of slots for that day** into `date_overrides[YYYY-MM-DD][pool_id]`. (Replacement = whatever the schedule for that day for that pool should be after the correction. If a slot is just removed, list the remaining ones; if added, list all original + new.)
     - Append an entry to `applied_corrections` with the message id, received date, subject, a one-line `summary` (English is fine), and the affected dates/pools.
     - Save `current.json` after each correction so a partial failure doesn't lose progress.
   - If a correction is too ambiguous to apply confidently, **don't guess** — record it in `applied_corrections` with `summary: "UNAPPLIED: <reason>"` and quote the relevant text. Surface it in the follow-up and ask the user to clarify.
6. **Recompute the answer** for the same `(date, pool)` and compare to `initial_slots`:
   - **No new corrections found OR none affected the asked-about day/pool** → say **nothing**. Don't send a "no updates" confirmation; the silence is the all-clear.
   - **Answer changed** → send a clearly-marked follow-up: *"Update: a correction email I just spotted changes today's slots — actually it's [new schedule]. (Reason: [summary], email [date])"*. Always include both the new slots and a brief reason so the user can decide.
   - **Ambiguous correction was found** → say *"Heads up: a correction email arrived but I couldn't apply it confidently — [quote]. The cached schedule above may be wrong; want to clarify?"*
   - Keep the follow-up short (1–3 lines). Don't restate everything.

## Cache structure (`current.json`)

```json
{
  "week_start": "YYYY-MM-DD",
  "week_end": "YYYY-MM-DD",
  "fetched_at": "ISO-8601",
  "source_pdf_url": "...",
  "pools": {
    "piscina_50m":         {"label": "PISCINA DE 50 METROS",   "schedule": {"monday": ["HH:MM-HH:MM", ...], ..., "sunday": []}},
    "piscina_25m":         {"label": "PISCINA DE 25 METROS",   "schedule": {...}},
    "tanque_aprendizagem": {"label": "TANQUE DE APRENDIZAGEM", "schedule": {...}}
  },
  "date_overrides": {
    "2026-05-14": {
      "piscina_50m": ["17:30-19:30"]
    }
  },
  "applied_corrections": [
    {
      "message_id": "19e1...",
      "received_at": "2026-05-12T10:00:00Z",
      "subject": "Alteração horário Piscina 50m - 14 mai",
      "summary": "50m pool closed 14 May 11:30-12:30 (maintenance)",
      "affected": [{"date": "2026-05-14", "pool": "piscina_50m"}]
    }
  ]
}
```

- `pools` always reflects the **original PDF** — never mutate it for corrections; that way we can re-derive overrides if logic changes.
- `date_overrides[date][pool]` is the **full replacement list of slots** for that day and pool — empty array means closed that day.
- Day keys in `pools[*].schedule` are lowercase English. An empty array means closed that day. A dash `—` in the PDF means no slot — omit it.

## Day-name mapping (PDF uses Portuguese)

SEGUNDA→monday, TERÇA→tuesday, QUARTA→wednesday, QUINTA→thursday, SEXTA→friday, SÁBADO→saturday. No Domingo column = closed Sunday.

## Pool aliases

- `50m`, `50 metros`, `olímpica`, `olympic`, `long course` → `piscina_50m`
- `25m`, `25 metros`, `short course` → `piscina_25m`
- `aprendizagem`, `learning`, `tank` → `tanque_aprendizagem`

## Failure modes & fallbacks

- **`desmor.pt` unreachable** → fall back to last cached week with a clear "(stale, network failed)" note. Don't silently serve stale data.
- **Page reachable but no `filecont/Horario_Livre-...` link** → site layout may have changed. Fall back to Gmail: `mcp__claude_ai_Gmail__search_threads` with query `from:secretaria.piscinas@desmor.pt subject:"Horário Livre"`. Parse week range from the subject (`Horário Livre - DD mmm a DD mmm YYYY`, Portuguese months: jan/fev/mar/abr/mai/jun/jul/ago/set/out/nov/dez), then guess the PDF URL `https://desmor.pt/filecont/Horario_Livre-{YYYY}_{MM}_{DD}_a_{YYYY}_{MM}_{DD}-V-v1.pdf` and try `curl -fI` first. If still no luck, tell the user the source is unavailable rather than fabricating hours.
- **PDF for the upcoming week not yet published** (asking late Sunday for Monday) → use the most recent PDF anyway and warn that it covers last week; the new one usually drops Thursday.
- **Gmail attachment**: the Gmail MCP exposes search/get_thread but **not** attachment download. Don't try — go to the website.
- **Cross-week query** (user asks about a date in a future week) → refresh; if the future week's PDF isn't published yet, say so.
- **Gmail unreachable when checking corrections** → the initial reply already went out. In the follow-up, say "(could not check for mid-week corrections — Gmail unreachable)". Don't retry in a loop.
- **Slow path (cache miss)** → the user does have to wait for the PDF fetch before step 4, but Gmail is still deferred to after the reply. Don't block the first reply on Gmail even when refetching the PDF.
- **Ambiguous correction** → record as `UNAPPLIED` in `applied_corrections` (so we don't re-ask Gmail for it) and surface to the user. On the next invocation, if the user has clarified, re-process by removing that entry from `applied_corrections`.
- **Correction supersedes a prior correction** for the same date/pool → just overwrite `date_overrides[date][pool]` with the newer value. Keep both entries in `applied_corrections` for audit, ordered by `received_at`.

## Notes

- Pool closes Sundays — there is no Domingo column.
- The PDF carries the weekly disclaimer "existe sempre a possibilidade deste horário ser alterado sem aviso prévio" (schedule may change without notice).
- Cache is per-user, single-machine. No locking needed.
- This skill is read-only; it never modifies email or schedules anything.
