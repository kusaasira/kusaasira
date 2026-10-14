#!/usr/bin/env python3
"""Build a one-shot count-up GIF from GitHub's publicly visible contributions."""
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from PIL import Image, ImageDraw, ImageFont
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
USER = "kusaasira"
BG, PANEL, BORDER = "#0c1420", "#111d2a", "#345062"
MINT, WHITE, TEXT, MUTED = "#78e4c1", "#f5f8fb", "#c9d5e0", "#94a6ba"
W, H = 1060, 302

def graphql(query, token):
    req = Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
            "User-Agent": "kusaasira-profile-activity",
        },
        method="POST",
    )
    with urlopen(req, timeout=30) as response:
        result = json.load(response)
    if result.get("errors"):
        raise RuntimeError(f"GitHub GraphQL errors: {result['errors']}")
    return result["data"]

def contributions(token, today):
    years_data = graphql(
        f'query {{ user(login: "{USER}") {{ contributionsCollection {{ contributionYears }} }} }}', token
    )
    years = set(years_data["user"]["contributionsCollection"]["contributionYears"])
    years.add(today.year)
    data_by_day = {}
    for year in sorted(y for y in years if 2005 <= y <= today.year):
        last_day = min(date(year, 12, 31), today)
        q = (
            f'query {{ user(login: "{USER}") {{ '
            f'contributionsCollection(from: "{year}-01-01T00:00:00Z", '
            f'to: "{last_day.isoformat()}T23:59:59Z") {{ '
            'contributionCalendar { weeks { contributionDays { date contributionCount } } } '
            '} } }'
        )
        weeks = graphql(q, token)["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
        for week in weeks:
            for item in week["contributionDays"]:
                day = date.fromisoformat(item["date"])
                if day.year == year and day <= today:
                    data_by_day[day] = int(item["contributionCount"])
    if not data_by_day:
        raise RuntimeError("No contribution days returned by GitHub")
    return data_by_day

def calculate(days, today):
    total = sum(days.values())
    best, start_best, end_best = 0, None, None
    run = 0
    start_run = None
    previous = None
    for day in sorted(days):
        if days[day] > 0:
            if run == 0 or previous != day - timedelta(days=1):
                start_run, run = day, 0
            run += 1
            if run > best:
                best, start_best, end_best = run, start_run, day
        else:
            run = 0
        previous = day
    end = today if days.get(today, 0) else today - timedelta(days=1)
    cursor = end
    current = 0
    while days.get(cursor, 0) > 0:
        cursor -= timedelta(days=1)
        current += 1
    return {
        "user": USER,
        "total": total,
        "current": current,
        "longest": best,
        "current_start": (cursor + timedelta(days=1)).isoformat() if current else None,
        "current_end": end.isoformat() if current else None,
        "longest_start": start_best.isoformat() if start_best else None,
        "longest_end": end_best.isoformat() if end_best else None,
        "date": today.isoformat(),
        "scope": "publicly visible contributions",
    }

def span(start, end):
    if not start or not end:
        return "No active streak"
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    if a == b:
        return a.strftime("%d %b %Y")
    if a.year == b.year:
        return f'{a.strftime("%d %b")} - {b.strftime("%d %b %Y")}'
    return f'{a.strftime("%b %Y")} - {b.strftime("%b %Y")}'

def font(n, bold=False):
    fname = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/" + fname, n)

def paint(stats, t):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((1, 1, W-2, H-2), radius=17, fill=BG, outline=BORDER, width=2)
    d.rounded_rectangle((18, 18, W-19, H-19), radius=13, fill=PANEL)
    if t > 0:
        d.rounded_rectangle((18, 18, 18+int((W-37)*t), 22), radius=2, fill=MINT)
    for x in (355, 705):
        d.line((x, 67, x, 244), fill=BORDER, width=2)
    d.text((42, 37), "GITHUB // ENGINEERING ACTIVITY", fill=MINT, font=font(14, True))
    d.text((W-40, 39), "AS OF "+stats["date"], anchor="ra", fill=MUTED, font=font(12))
    eased = 1 - (1-t)**4
    nums = [round(stats[k]*eased) for k in ("total", "current", "longest")]
    notes = [
        "ALL-TIME VISIBLE",
        span(stats["current_start"], stats["current_end"]),
        span(stats["longest_start"], stats["longest_end"]),
    ]
    for x, number, title, note in zip(
        (184, 531, 880), nums,
        ("TOTAL CONTRIBUTIONS", "CURRENT STREAK", "LONGEST STREAK"), notes
    ):
        d.text((x, 157), f"{number:,}", anchor="mm", fill=WHITE, font=font(50, True))
        d.text((x, 232), title, anchor="mm", fill=TEXT, font=font(14, True))
        d.text((x, 257), note, anchor="mm", fill=MUTED, font=font(11))
    d.arc((464, 90, 598, 224), 210, 510, fill="#365665", width=3)
    if t:
        d.arc((464, 90, 598, 224), 210, 210+int(300*t), fill=MINT, width=5)
    d.text((42, 274), "PUBLIC GITHUB ACTIVITY", fill=MUTED, font=font(10))
    d.text((W-38, 274), "BUILT TO SHIP. BUILT TO LAST.", fill=MINT, anchor="ra", font=font(10, True))
    return im

def render(stats):
    ASSETS.mkdir(exist_ok=True)
    # No loop extension: one 2.5-second count-up, then hold the final values.
    images = [
        paint(stats, i/36).quantize(colors=64, method=Image.Quantize.MEDIANCUT)
        for i in range(37)
    ]
    images[0].save(
        ASSETS/"github-activity.gif",
        save_all=True,
        append_images=images[1:],
        duration=[70]*36+[3000],
        optimize=True,
        disposal=2,
    )
    entries = [
        ("TOTAL CONTRIBUTIONS", stats["total"], "ALL-TIME VISIBLE"),
        ("CURRENT STREAK", stats["current"], span(stats["current_start"], stats["current_end"])),
        ("LONGEST STREAK", stats["longest"], span(stats["longest_start"], stats["longest_end"])),
    ]
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img">',
        f'<title>GitHub activity of {USER}</title>',
        '<rect width="1060" height="302" rx="17" fill="#0c1420"/>',
        '<rect x="18" y="18" width="1024" height="266" rx="13" fill="#111d2a"/>',
        '<path d="M355 67V264M705 67V264" stroke="#345062" stroke-width="2"/>',
        '<text x="42" y="50" font-family="monospace" font-size="14" font-weight="bold" fill="#78e4c1">GITHUB // ENGINEERING ACTIVITY</text>',
        f'<text x="1020" y="50" text-anchor="end" font-family="sans-serif" font-size="12" fill="#94a6ba">AS OF {stats["date"]}</text>',
    ]
    for x, (title, number, note) in zip((184, 531, 880), entries):
        svg.extend([
            f'<text x="{x}" y="175" text-anchor="middle" font-family="sans-serif" font-size="51" font-weight="bold" fill="#f5f8fb">{number:,}</text>',
            f'<text x="{x}" y="238" text-anchor="middle" font-family="sans-serif" font-size="14" font-weight="bold" fill="#c9d5e0">{title}</text>',
            f'<text x="{x}" y="263" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#94a6ba">{escape(note)}</text>',
        ])
    svg.extend([
        '<text x="42" y="275" font-family="monospace" font-size="10" fill="#94a6ba">PUBLIC GITHUB ACTIVITY</text>',
        '<text x="1020" y="275" text-anchor="end" font-family="monospace" font-size="10" fill="#78e4c1">BUILT TO SHIP. BUILT TO LAST.</text>',
        '</svg>',
    ])
    (ASSETS/"github-activity.svg").write_text("\n".join(svg)+"\n")
    (ASSETS/"github-activity.json").write_text(json.dumps(stats, indent=2)+"\n")

def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required")
    today = datetime.now(timezone.utc).date()
    stats = calculate(contributions(token, today), today)
    print(json.dumps(stats, indent=2))
    render(stats)

if __name__ == "__main__":
    main()
