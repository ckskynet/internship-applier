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
Output ONLY the cover letter text, no extra commentary.

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

        # Save to file
        if output_dir is None:
            output_dir = os.path.join(os.path.dirname(__file__), "..", "data", "cover_letters")
        os.makedirs(output_dir, exist_ok=True)

        safe_company = re.sub(r'[^\w\-]', '_', company)[:30]
        filename = f"cover_letter_{safe_company}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "w") as f:
            f.write(cover_letter_text)

        return filepath

    except Exception as e:
        print(f"  [!] Failed to generate cover letter: {e}")
        return None
