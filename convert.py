"""Pin the GO Calendar feed's floating event times to one time zone.

The upstream feed (othyn/go-calendar) leaves event times without a time zone so
clients show them as local time. Google Calendar URL subscriptions read those
times as UTC instead, so this script tags every timed DTSTART/DTEND with
TZID=Australia/Melbourne and adds the matching VTIMEZONE definition.
All-day dates and times already marked UTC (ending in Z) are left alone.
"""

import sys
import urllib.request

SOURCE_URL = "https://raw.githubusercontent.com/othyn/go-calendar/main/dist/gocal.ics"
TZID = "Australia/Melbourne"
CAL_NAME = "GO Calendar (Melbourne time)"

VTIMEZONE = [
    "BEGIN:VTIMEZONE",
    f"TZID:{TZID}",
    "X-LIC-LOCATION:Australia/Melbourne",
    "BEGIN:STANDARD",
    "TZOFFSETFROM:+1100",
    "TZOFFSETTO:+1000",
    "TZNAME:AEST",
    "DTSTART:19700405T030000",
    "RRULE:FREQ=YEARLY;BYMONTH=4;BYDAY=1SU",
    "END:STANDARD",
    "BEGIN:DAYLIGHT",
    "TZOFFSETFROM:+1000",
    "TZOFFSETTO:+1100",
    "TZNAME:AEDT",
    "DTSTART:19701004T020000",
    "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=1SU",
    "END:DAYLIGHT",
    "END:VTIMEZONE",
]


def load_excludes(path: str = "exclude.txt") -> list:
    """One match per line; blank lines and lines starting with # are ignored."""
    try:
        with open(path, encoding="utf-8") as f:
            return [
                s.strip().lower()
                for s in f
                if s.strip() and not s.strip().startswith("#")
            ]
    except FileNotFoundError:
        return []


def event_title(block: list) -> str:
    """Unfolded, unescaped SUMMARY of one VEVENT block."""
    for i, line in enumerate(block):
        if line.startswith("SUMMARY"):
            value = line.split(":", 1)[1]
            for cont in block[i + 1:]:
                if not cont.startswith((" ", "\t")):
                    break
                value += cont[1:]
            return value.replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")
    return ""


def drop_excluded(lines: list, excludes: list) -> list:
    if not excludes:
        return lines
    out, block = [], None
    for line in lines:
        if line == "BEGIN:VEVENT":
            block = [line]
            continue
        if block is not None:
            block.append(line)
            if line == "END:VEVENT":
                title = event_title(block).lower()
                if any(x in title for x in excludes):
                    print(f"Excluded: {event_title(block)}")
                else:
                    out.extend(block)
                block = None
            continue
        out.append(line)
    return out


def convert(text: str, excludes: list = ()) -> str:
    lines = drop_excluded(text.replace("\r\n", "\n").split("\n"), list(excludes))
    out = []
    timed = 0
    for line in lines:
        for prop in ("DTSTART", "DTEND"):
            prefix = prop + ":"
            # Only bare floating date-times, e.g. DTSTART:20261121T140000
            if line.startswith(prefix):
                value = line[len(prefix):].strip()
                if "T" in value and not value.endswith("Z"):
                    line = f"{prop};TZID={TZID}:{value}"
                    timed += 1
        if line.startswith("NAME:") or line.startswith("X-WR-CALNAME:"):
            line = line.split(":", 1)[0] + ":" + CAL_NAME
        out.append(line)
        if line.startswith("X-WR-CALNAME:"):
            out.append(f"X-WR-TIMEZONE:{TZID}")
        if line.startswith("X-PUBLISHED-TTL"):
            out.extend(VTIMEZONE)

    if "BEGIN:VTIMEZONE" not in out:
        # Feed layout changed: insert before the first event instead.
        first = out.index("BEGIN:VEVENT") if "BEGIN:VEVENT" in out else len(out) - 1
        out[first:first] = VTIMEZONE
    if timed == 0:
        raise SystemExit("No timed events found; refusing to publish an empty-looking feed.")
    return "\r\n".join(out)


def main() -> None:
    dest = sys.argv[1] if len(sys.argv) > 1 else "gocal-melbourne.ics"
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "go-calendar-local"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode("utf-8")
    if "BEGIN:VCALENDAR" not in text:
        raise SystemExit("Upstream did not return a calendar; keeping the previous file.")
    with open(dest, "w", encoding="utf-8", newline="") as f:
        f.write(convert(text, load_excludes()))


if __name__ == "__main__":
    main()
