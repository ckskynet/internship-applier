"""Cover letter detection and generation using Claude API."""

import os
import re
from datetime import datetime

import anthropic

from utils.config import get_personal_info, get_education


# Patterns that indicate a cover letter is required or requested
COVER_LETTER_PATTERNS = [
    r"cover\s*letter\s*(required|is\s+required|mandatory|must|needed)",
    r"(submit|upload|attach|include|provide)\s+(a\s+)?cover\s*letter",
    r"cover\s*letter\s*(upload|attachment|field)",
    r"please\s+(include|attach|provide|submit)\s+.*cover\s*letter",
    r"(required|optional)\s*:\s*cover\s*letter",
    r"cover\s*letter\s*\*",  # asterisk often means required
]

# Patterns that suggest it's optional (lower priority)
OPTIONAL_PATTERNS = [
    r"cover\s*letter\s*(optional|not\s+required|encouraged)",
    r"(optional|bonus)\s*:\s*cover\s*letter",
]


def detect_cover_letter_needed(page_text):
    """Scan page text to determine if a cover letter is required.

    Returns:
        'required' — posting explicitly requires a cover letter
        'optional' — posting mentions cover letter but it's optional
        'none'     — no cover letter mentioned
    """
    text = page_text.lower()

    # Check for explicit requirement
    for pattern in COVER_LETTER_PATTERNS:
        if re.search(pattern, text):
            # But check if it's actually marked optional
            for opt_pattern in OPTIONAL_PATTERNS:
                if re.search(opt_pattern, text):
                    return "optional"
            return "required"

    # Check for any mention at all
    if "cover letter" in text or "coverletter" in text:
        return "optional"

    return "none"


def scan_page_for_cover_letter(page):
    """Use Playwright page to check for cover letter requirement.

    Checks both the page text and form elements (file upload labels, etc).
    """
    # Check page body text
    body_text = page.inner_text("body")
    result = detect_cover_letter_needed(body_text)

    if result != "none":
        return result

    # Also check for file upload fields labeled "cover letter"
    labels = page.query_selector_all("label")
    for label in labels:
        label_text = label.inner_text().lower()
        if "cover" in label_text and "letter" in label_text:
            return "required"

    # Check for upload buttons with cover letter text
    buttons = page.query_selector_all("button, a, span, div")
    for btn in buttons:
        try:
            btn_text = btn.inner_text().lower()
            if "cover letter" in btn_text and ("upload" in btn_text or "attach" in btn_text):
                return "required"
        except Exception:
            continue

    return "none"


def generate_cover_letter(job_title, company, job_description, output_dir=None):
    """Generate a tailored cover letter using the Claude API.

    Args:
        job_title: The position title
        company: The company name
        job_description: The full job description text
        output_dir: Directory to save the cover letter (defaults to data/)

    Returns:
        Path to the generated cover letter text file, or None on failure.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  [!] ANTHROPIC_API_KEY not set. Cannot generate cover letter.")
        print("      Set it with: export ANTHROPIC_API_KEY=your-key-here")
        return None

    personal = get_personal_info()
    education = get_education()

    prompt = f"""Write a professional, concise cover letter for the following internship position.
Tailor it specifically to the job description and company. Keep it to 3-4 paragraphs.
Do NOT include placeholders — use the provided information directly.
Output ONLY the body paragraphs of the cover letter. Do NOT include any header, contact info,
date, address block, or sign-off with contact details. Start directly with "Dear Hiring Manager,"
or similar greeting and end with the closing line and your name only.
Do NOT introduce yourself by name in the first paragraph (e.g. "My name is...") since the
header already contains the applicant's name. Jump straight into why you are interested in
the position and what makes you a good fit.

WRITING STYLE RULES (strict):
- Write like a real college student, not a corporate AI. Use natural, straightforward language.
- NEVER use em dashes (—) or en dashes (–). Use commas, periods, or "and" instead.
- NEVER use emojis or special unicode characters.
- Avoid overused AI phrases: "passion for", "I am excited to", "I am thrilled", "I believe",
  "cutting-edge", "leverage", "utilize", "furthermore", "in addition", "I am confident that",
  "unique opportunity", "align with", "deeply", "eager".
- Use simple, direct sentences. Vary sentence length. Don't start every sentence with "I".
- Sound genuine and specific — reference actual details from the job description rather than
  making generic statements about being a "team player" or having "strong communication skills".
- Keep the tone professional but conversational, like an email you'd actually send.

APPLICANT INFO:
- Name: {personal.get('first_name', '')} {personal.get('last_name', '')}
- Email: {personal.get('email', '')}
- Phone: {personal.get('phone', '')}
- University: {education.get('university', '')}
- Degree: {education.get('degree', '')} in {education.get('major', '')}
- Expected Graduation: {education.get('graduation_date', '')}
- LinkedIn: {personal.get('linkedin_url', '')}

POSITION:
- Title: {job_title}
- Company: {company}

JOB DESCRIPTION:
{job_description[:3000]}

Today's date: {datetime.now().strftime('%B %d, %Y')}
"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        cover_letter_text = message.content[0].text

        # Save to files
        if output_dir is None:
            output_dir = os.path.join(os.path.dirname(__file__), "..", "data", "cover_letters")
        os.makedirs(output_dir, exist_ok=True)

        safe_company = re.sub(r'[^\w\-]', '_', company)[:30]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_name = f"cover_letter_{safe_company}_{timestamp}"

        # Save as .docx
        docx_path = os.path.join(output_dir, f"{base_name}.docx")
        _save_as_docx(cover_letter_text, docx_path, personal, job_title, company)

        # Also save plain text for easy copying
        txt_path = os.path.join(output_dir, f"{base_name}.txt")
        with open(txt_path, "w") as f:
            f.write(cover_letter_text)

        return docx_path

    except Exception as e:
        print(f"  [!] Failed to generate cover letter: {e}")
        return None


def _save_as_docx(text, filepath, personal, job_title, company):
    """Save cover letter text as a formatted Word document."""
    from docx import Document
    from docx.shared import Pt, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()

    # Set default font
    style = doc.styles["Normal"]
    font = style.font
    font.name = "Calibri"
    font.size = Pt(11)
    style.paragraph_format.space_after = Pt(0)
    style.paragraph_format.space_before = Pt(0)

    # Set narrow margins
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    # Header: name centered and bold
    name = f"{personal.get('first_name', '')} {personal.get('last_name', '')}"
    header_p = doc.add_paragraph()
    header_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    header_run = header_p.add_run(name)
    header_run.bold = True
    header_run.font.size = Pt(14)

    # Contact line below name
    contact_parts = []
    if personal.get("email"):
        contact_parts.append(personal["email"])
    if personal.get("phone"):
        contact_parts.append(personal["phone"])
    if personal.get("location"):
        contact_parts.append(personal["location"])
    if contact_parts:
        contact_p = doc.add_paragraph()
        contact_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        contact_run = contact_p.add_run(" | ".join(contact_parts))
        contact_run.font.size = Pt(10)

    # Date
    date_p = doc.add_paragraph()
    date_p.add_run(datetime.now().strftime("%B %d, %Y"))
    date_p.paragraph_format.space_before = Pt(18)
    date_p.paragraph_format.space_after = Pt(12)

    # Body paragraphs — split on double newlines for proper spacing
    paragraphs = [p.strip() for p in text.strip().split("\n\n") if p.strip()]
    for para_text in paragraphs:
        p = doc.add_paragraph(para_text)
        p.paragraph_format.space_after = Pt(12)

    doc.save(filepath)
