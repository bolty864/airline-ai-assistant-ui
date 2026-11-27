"""Generate the demo DGCA circular (PDF + HTML) served by /api/demo/sources/ for the offline demo.

    python scripts/make_sample_regulation.py
"""
from __future__ import annotations

import hashlib
import html
from pathlib import Path

import pymupdf

OUT = Path(__file__).resolve().parents[1] / "sample_data" / "demo_sources"

HEADER = "DGCA CAR Section 3 Series M Part IV (SAMPLE - NOT AN OFFICIAL DOCUMENT)"
LINES = [
    "GOVERNMENT OF INDIA",
    "OFFICE OF THE DIRECTOR GENERAL OF CIVIL AVIATION",
    "CIVIL AVIATION REQUIREMENTS: ADVANCE PASSENGER INFORMATION",
    "",
    "1. INTRODUCTION",
    "1.1 This CAR lays down the requirements for the handling of Advance Passenger Information (API) by scheduled operators.",
    "2. APPLICABILITY",
    "2.1 This CAR applies to all scheduled domestic and international operators.",
    "3. DEFINITIONS",
    "3.1 \"API\" means the passenger and travel document data collected at reservation or check-in.",
    "4. DATA RETENTION",
    "4.1 Operators shall transmit API data to the designated authority before the departure of each international flight.",
    "4.2 Passenger API records shall be retained for a minimum period of 5 years from the date of travel.",
    "4.3 Records required under this CAR shall be produced to DGCA within 7 days of a request.",
    "5. DATA SECURITY",
    "5.1 API data must be encrypted at rest and in transit, and access shall be restricted to authorised personnel only.",
    "5.2 Operators are required to conduct access reviews of all systems holding API data at least once every quarter.",
    "6. INCIDENT REPORTING",
    "6.1 Any unauthorised access to API data shall be reported to DGCA and CERT-In within 6 hours of detection.",
    "7. TRAINING",
    "7.1 Staff handling API data shall complete data protection training annually.",
    "7.2 Operators should consider refresher sessions for supervisors.",
    "8. EFFECTIVE DATE",
    "8.1 This CAR comes into force from 01 January 2027.",
]


def make_pdf(path: Path) -> None:
    doc = pymupdf.open()
    per_page = 9
    for p, start in enumerate(range(0, len(LINES), per_page), 1):
        page = doc.new_page()
        page.insert_text((50, 40), HEADER, fontsize=8)
        y = 80
        for line in LINES[start:start + per_page]:
            rect = pymupdf.Rect(50, y, 545, y + 60)
            page.insert_textbox(rect, line, fontsize=10)
            y += 42 if len(line) > 90 else 26
        page.insert_text((280, 810), f"Page {p}", fontsize=8)
    doc.save(path)


def make_html(path: Path) -> None:
    body = []
    for line in LINES:
        if not line:
            continue
        tag = "h2" if line[:2].strip(".").isdigit() and line.isupper() else "p"
        body.append(f"<{tag}>{html.escape(line)}</{tag}>")
    path.write_text(
        "<html><head><title>DGCA API CAR</title><script>var x=1;</script></head><body>"
        "<nav>Home | Circulars</nav><main>" + "\n".join(body) + "</main><footer>DGCA India</footer></body></html>",
        encoding="utf-8",
    )


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    pdf = OUT / "DGCA_CAR_API_Retention.pdf"
    make_pdf(pdf)
    make_html(OUT / "DGCA_CAR_API_Retention.html")
    print(hashlib.sha256(pdf.read_bytes()).hexdigest())
