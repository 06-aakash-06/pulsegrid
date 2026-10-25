"""Builds review.html from review/before (main) and review/after (ui/polish) screenshots."""
import html
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ORDER = ["patient", "receptionist", "doctor", "pharmacist", "billing", "emergency", "admin", "ops"]
NOTES = {
    "patient-dashboard": "One welcome card with three aligned stats; slips share size and sit in their own row; the info row is no longer overlapped; the queue panel shows a check-in state before a token exists.",
    "patient-doctors": "64px initials circle; the profile shows next available, open slots and specialty; roster times read \"25 Oct · 15:00\"; the roster box fits whole rows with a fade.",
    "patient-appointments": "Availability loads when the doctor or date changes; patient details are read-only text; the summary column holds the printed slip.",
    "patient-queue": "Kiosk, live queue and your-turn panels fit one 1536×864 screen; the patient name column is gone.",
    "patient-check-in": "The kiosk fits its column; duplicated copy removed.",
    "patient-records": "The patient strip shrinks to fit; one Related card holds record history, prescription and journey links, access permissions and details.",
    "patient-pharmacy": "Disclosures show open and closed cues; the shelf toggle sits on a card.",
    "patient-billing": "Receipt and invoice list sit side by side.",
    "patient-waitlist": "The intro text sits on a card.",
    "patient-journey": "The journey uses the full width.",
    "pharmacist-dashboard": "Decorative cartons with full names below; one search rail; one Manage menu.",
    "pharmacist-inventory": "Decorative cartons with full names below; one search rail; one Manage menu.",
    "pharmacist-prescriptions": "Shelf cleaned up; duplicated reservation heading removed.",
    "billing-dashboard": "Normal tabs; the import-by-reference form sits behind Advanced because the API does not let Billing list sources.",
    "emergency-requests": "Queue titles wrap to two lines with tooltips.",
    "emergency-dashboard": "Queue titles wrap to two lines with tooltips.",
    "doctor-consultations": "Finalize is a sticky footer inside the dossier card.",
    "doctor-prescriptions": "\"Write a prescription\" is the header action; the empty viewer column is gone.",
    "doctor-queue": "Row actions sit on one line.",
    "admin-control-room": "Short table headers, distinct queue labels, raw queue names in monospace under Details, aligned KPI values.",
    "ops-dashboard": "Short table headers, distinct queue labels, raw queue names in monospace under Details, aligned KPI values.",
    "admin-staff": "Search, role, state and Apply on one line above a full-width table.",
    "receptionist-appointments": "Empty check-in heading hidden; booking polish as for patients.",
    "receptionist-dashboard": "Row actions sit on one line.",
}


def routes():
    names = {f.rsplit("-", 1)[0] for f in os.listdir(os.path.join(HERE, "review", "after")) if f.endswith(".jpg")}
    return sorted(names, key=lambda r: (ORDER.index(r.split("-")[0]), r))


def figure(caption, src, alt):
    return f'<figure><figcaption>{caption}</figcaption><a href="{src}"><img loading="lazy" src="{src}" alt="{alt}"></a></figure>'


def section(route):
    role, _, page = route.partition("-")
    note = html.escape(NOTES.get(route, "Shared polish only: tables, disclosures and spacing."))
    desktop = figure("Before · main · 1536", f"review/before/{route}-1536.jpg", f"{route} before at 1536px") + figure("After · ui/polish · 1536", f"review/after/{route}-1536.jpg", f"{route} after at 1536px")
    phone = figure("Before · 390", f"review/before/{route}-390.jpg", f"{route} before at 390px") + figure("After · 390", f"review/after/{route}-390.jpg", f"{route} after at 390px")
    return (f'<section class="route" id="{route}"><h2><span>{role}</span>/{role}/{page}</h2><p>{note}</p>'
            f'<div class="pair">{desktop}</div><details><summary>Phone, 390px</summary><div class="pair phone">{phone}</div></details></section>')


STYLE = """
:root{--bg:#f6f1ea;--ink:#13293d;--muted:#5b6670;--line:#e2d6c4;--card:#fffdf8}
@media(prefers-color-scheme:dark){:root{--bg:#141a1f;--ink:#e8edf0;--muted:#9aa6ae;--line:#2c363e;--card:#1b232a}}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}
main{max-width:1400px;margin:0 auto;padding:24px 16px}
h1{margin:0 0 4px}.lead{color:var(--muted);margin:0 0 16px}
nav{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 24px}
nav a{font-size:12px;padding:3px 8px;border:1px solid var(--line);border-radius:999px;color:var(--ink);text-decoration:none}
.route{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:0 0 24px}
.route h2{font-size:17px;margin:0 0 4px}
.route h2 span{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-right:8px}
.route p{margin:0 0 12px;color:var(--muted)}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}.pair.phone{max-width:640px;margin-top:12px}
figure{margin:0;min-width:0}figcaption{font-size:12px;color:var(--muted);margin-bottom:4px}
img{display:block;width:100%;height:auto;max-height:900px;object-fit:cover;object-position:top;border:1px solid var(--line);border-radius:6px}
summary{cursor:pointer;margin-top:12px;font-weight:600}
@media(max-width:700px){.pair{grid-template-columns:1fr}}
"""


def main():
    items = routes()
    toc = "".join(f'<a href="#{r}">{r}</a>' for r in items)
    body = "".join(section(r) for r in items)
    page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>PulseGrid UI review</title><style>{STYLE}</style></head><body><main><h1>PulseGrid UI review</h1>'
            f'<p class="lead">Before is <code>main</code>; after is <code>ui/polish</code> (fixes 1 to 3) in mock mode, for all {len(items)} sidebar routes across the eight roles. '
            f'Desktop pairs are 1536px wide; phone pairs (390px) open under each route. Click an image for full size.</p>'
            f'<nav>{toc}</nav>{body}</main></body></html>')
    with open(os.path.join(HERE, "review.html"), "w") as out:
        out.write(page)
    print(f"{len(items)} routes")


main()
