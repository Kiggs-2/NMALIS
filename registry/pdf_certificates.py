"""Generate official-style license and accreditation PDF certificates."""

from io import BytesIO

from django.utils import timezone

SYSTEM_NAME = "National Medical Accreditation and Licensing Information System"
AUTHORITY = "Kenya Medical Practitioners and Dentists Council (KMPDC)"


def _reportlab():
    """Load ReportLab on demand so the app starts even if the package is missing."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise ImportError(
            "ReportLab is required for PDF certificates. Install dependencies with: "
            "pip install -r requirements.txt"
        ) from exc
    return colors, A4, mm, canvas


def _draw_header(c, colors, mm, width, height, title: str):
    c.setFillColor(colors.HexColor("#1e3a8a"))
    c.rect(0, height - 45 * mm, width, 45 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, height - 18 * mm, AUTHORITY)
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, height - 26 * mm, SYSTEM_NAME)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, height - 38 * mm, title)


def _draw_footer(c, colors, mm, width, issued_on):
    c.setFillColor(colors.HexColor("#64748b"))
    c.setFont("Helvetica", 8)
    c.drawString(
        20 * mm,
        15 * mm,
        f"Digitally issued via {SYSTEM_NAME} · {issued_on.strftime('%d %B %Y, %H:%M')} EAT",
    )
    c.drawString(20 * mm, 10 * mm, "This document is valid only when status in the national registry is Active.")


def build_practitioner_license_pdf(practitioner) -> BytesIO:
    colors, A4, mm, canvas = _reportlab()
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    issued_on = timezone.now()

    _draw_header(c, colors, mm, width, height, "PRACTISING LICENCE CERTIFICATE")

    y = height - 60 * mm
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 11)
    c.drawString(20 * mm, y, "This certifies that the practitioner named below is registered in the national registry.")
    y -= 12 * mm

    fields = [
        ("Full name", practitioner.full_name),
        ("License number", practitioner.license_number),
        ("Specialty", practitioner.specialty or "—"),
        ("Status", practitioner.get_status_display()),
        ("License expiry", str(practitioner.license_expiry)),
        ("Indemnity expiry", str(practitioner.indemnity_expiry)),
        ("CPD points", str(practitioner.cpd_points)),
    ]
    for label, value in fields:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, y, f"{label}:")
        c.setFont("Helvetica", 11)
        c.drawString(55 * mm, y, value)
        y -= 8 * mm

    c.setStrokeColor(colors.HexColor("#2563eb"))
    c.setLineWidth(1.5)
    c.rect(20 * mm, 35 * mm, width - 40 * mm, 25 * mm, stroke=1, fill=0)
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(25 * mm, 50 * mm, "Official copy for institutional verification and employment records.")

    _draw_footer(c, colors, mm, width, issued_on)
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


def build_facility_accreditation_pdf(facility) -> BytesIO:
    colors, A4, mm, canvas = _reportlab()
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    issued_on = timezone.now()

    _draw_header(c, colors, mm, width, height, "FACILITY ACCREDITATION CERTIFICATE")

    y = height - 60 * mm
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 11)
    c.drawString(20 * mm, y, "This certifies that the healthcare facility below is recorded in the national registry.")
    y -= 12 * mm

    fields = [
        ("Facility name", facility.name),
        ("Registration number", facility.registration_number),
        ("County", facility.county or "—"),
        ("Status", facility.get_status_display()),
        ("Accreditation expiry", str(facility.accreditation_expiry)),
        ("Services", (facility.services_offered or "—")[:80]),
    ]
    for label, value in fields:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, y, f"{label}:")
        c.setFont("Helvetica", 11)
        c.drawString(55 * mm, y, value)
        y -= 8 * mm

    c.setStrokeColor(colors.HexColor("#2563eb"))
    c.setLineWidth(1.5)
    c.rect(20 * mm, 35 * mm, width - 40 * mm, 25 * mm, stroke=1, fill=0)
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(25 * mm, 50 * mm, "Official copy for practitioner due diligence and regulatory compliance.")

    _draw_footer(c, colors, mm, width, issued_on)
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


def build_facility_services_update_pdf(facility, application) -> BytesIO:
    colors, A4, mm, canvas = _reportlab()
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    issued_on = timezone.now()

    _draw_header(c, colors, mm, width, height, "FACILITY SERVICES UPDATE CERTIFICATE")

    y = height - 60 * mm
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 11)
    c.drawString(20 * mm, y, "This certifies that the facility's registered services have been updated in the national registry.")
    y -= 12 * mm

    fields = [
        ("Facility name", facility.name),
        ("Registration number", facility.registration_number),
        ("County", facility.county or "—"),
        ("Application ref", f"APP-{application.pk}"),
        ("Approved on", application.reviewed_at.strftime("%d %B %Y") if application.reviewed_at else "—"),
        ("Approved services", (application.services_requested or "—")[:90]),
    ]
    for label, value in fields:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, y, f"{label}:")
        c.setFont("Helvetica", 11)
        c.drawString(55 * mm, y, value)
        y -= 8 * mm

    c.setStrokeColor(colors.HexColor("#2563eb"))
    c.setLineWidth(1.5)
    c.rect(20 * mm, 35 * mm, width - 40 * mm, 25 * mm, stroke=1, fill=0)
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(25 * mm, 50 * mm, "Official copy confirming approved services update for regulatory compliance.")

    _draw_footer(c, colors, mm, width, issued_on)
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer
