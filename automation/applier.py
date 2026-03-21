"""Browser automation for pre-filling and submitting job applications."""

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from utils.config import get_personal_info, get_education, get_resume_path
from utils.database import update_job_status
from automation.cover_letter import scan_page_for_cover_letter, generate_cover_letter

_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


# Common form field patterns mapped to profile keys
FIELD_PATTERNS = {
    "first_name": ["first.?name", "fname", "given.?name", "legal.?first"],
    "last_name": ["last.?name", "lname", "surname", "family.?name", "legal.?last"],
    "preferred_name": ["preferred.?name", "nickname", "goes.?by", "known.?as"],
    "email": ["email", "e-mail"],
    "phone": ["phone", "tel", "mobile", "cell"],
    "location": ["location", "city", "address"],
    "linkedin_url": ["linkedin"],
    "university": ["school", "university", "college", "institution"],
    "degree": ["degree"],
    "major": ["major", "field.?of.?study", "concentration"],
    "gpa": ["gpa", "grade"],
    "graduation_date": ["graduat", "expected.?grad", "completion"],
}


def _try_fill_field(page, input_el, personal, education):
    """Try to match an input element to a profile field and fill it."""
    # Gather identifiers from the input element
    name = (input_el.get_attribute("name") or "").lower()
    id_attr = (input_el.get_attribute("id") or "").lower()
    placeholder = (input_el.get_attribute("placeholder") or "").lower()
    label_text = ""

    # Check for associated label
    input_id = input_el.get_attribute("id")
    if input_id:
        label = page.query_selector(f'label[for="{input_id}"]')
        if label:
            label_text = label.inner_text().lower()

    identifiers = f"{name} {id_attr} {placeholder} {label_text}"

    import re
    all_data = {**personal, **education}

    for field_key, patterns in FIELD_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, identifiers):
                value = all_data.get(field_key, "")
                if value:
                    input_el.fill(str(value))
                    return True
    return False


def _try_upload_resume(page, resume_path):
    """Look for file upload inputs and attach resume."""
    if not resume_path:
        return False

    file_inputs = page.query_selector_all('input[type="file"]')
    for file_input in file_inputs:
        accept = (file_input.get_attribute("accept") or "").lower()
        name = (file_input.get_attribute("name") or "").lower()
        # Upload to inputs that accept PDFs or have resume-related names
        if "pdf" in accept or "resume" in name or "cv" in name or not accept:
            try:
                file_input.set_input_files(resume_path)
                return True
            except Exception:
                continue
    return False


def _try_upload_cover_letter(page, cover_letter_path):
    """Try to find a cover letter file upload and attach the generated file."""
    file_inputs = page.query_selector_all('input[type="file"]')
    for file_input in file_inputs:
        name = (file_input.get_attribute("name") or "").lower()
        # Check associated label
        input_id = file_input.get_attribute("id")
        label_text = ""
        if input_id:
            label = page.query_selector(f'label[for="{input_id}"]')
            if label:
                label_text = label.inner_text().lower()
        context = f"{name} {label_text}"
        if "cover" in context and "letter" in context:
            try:
                file_input.set_input_files(cover_letter_path)
                return True
            except Exception:
                continue
    return False


def _fill_and_upload(page, personal, education, resume_path):
    """Fill visible form fields and upload resume. Returns (filled_count, resume_uploaded)."""
    inputs = page.query_selector_all(
        'input[type="text"], input[type="email"], input[type="tel"], '
        'input[type="url"], input:not([type])'
    )
    filled = 0
    for inp in inputs:
        if inp.is_visible():
            if _try_fill_field(page, inp, personal, education):
                filled += 1
    uploaded = _try_upload_resume(page, resume_path)
    return filled, uploaded


def _auto_submit_indeed(page, personal, education, resume_path):
    """Auto-submit via Indeed's Easily Apply modal. Returns True on success."""
    apply_btn = page.query_selector(
        '#indeedApplyButton, '
        'button:has-text("Apply now"), '
        'button[id*="applyButton"]'
    )
    if not apply_btn:
        return False
    apply_btn.click()
    page.wait_for_timeout(2000)

    # Loop through multi-step form (up to 10 steps)
    for _ in range(10):
        _fill_and_upload(page, personal, education, resume_path)

        # Check for final submit button
        submit_btn = page.query_selector(
            'button:has-text("Submit your application"), '
            'button:has-text("Submit application"), '
            'button[class*="submit"]:has-text("Submit")'
        )
        if submit_btn and submit_btn.is_visible():
            submit_btn.click()
            page.wait_for_timeout(3000)
            body = page.inner_text("body").lower()
            return "submitted" in body or "application has been" in body

        # Click Continue/Next for intermediate steps
        continue_btn = page.query_selector(
            'button:has-text("Continue"), button:has-text("Next")'
        )
        if continue_btn and continue_btn.is_visible():
            continue_btn.click()
            page.wait_for_timeout(1500)
        else:
            break

    return False


def _auto_submit_ziprecruiter(page):
    """Auto-submit via ZipRecruiter's 1-Click Apply. Returns True on success."""
    one_click = page.query_selector(
        'button:has-text("1-Click Apply"), '
        'button:has-text("One Click Apply"), '
        '[class*="one_click"] button, '
        '[class*="one-click"] button'
    )
    if not one_click:
        return False
    one_click.click()
    page.wait_for_timeout(3000)

    # Handle confirmation modal if it appears
    confirm_btn = page.query_selector(
        'button:has-text("Submit"), button:has-text("Confirm")'
    )
    if confirm_btn and confirm_btn.is_visible():
        confirm_btn.click()
        page.wait_for_timeout(2000)

    body = page.inner_text("body").lower()
    return "application" in body and ("sent" in body or "submitted" in body)


def _auto_submit_handshake(page, resume_path):
    """Auto-submit via Handshake's Quick Apply. Returns True on success."""
    apply_btn = page.query_selector(
        'button:has-text("Quick Apply"), '
        'button:has-text("Apply"), '
        'a:has-text("Quick Apply")'
    )
    if not apply_btn:
        return False
    apply_btn.click()
    page.wait_for_timeout(2000)

    # Upload resume if file input appears
    _try_upload_resume(page, resume_path)
    page.wait_for_timeout(1000)

    # Click submit
    submit_btn = page.query_selector(
        'button:has-text("Submit Application"), '
        'button:has-text("Submit"), '
        'button:has-text("Apply")'
    )
    if submit_btn and submit_btn.is_visible():
        submit_btn.click()
        page.wait_for_timeout(3000)
        body = page.inner_text("body").lower()
        return "applied" in body or "submitted" in body or "application" in body

    return False


def auto_apply_to_job(job):
    """Attempt auto-submit for quick-apply jobs. Falls back to manual on failure.

    Returns the final status: 'applied', 'skipped', or 'error'.
    """
    from utils.database import update_apply_method

    personal = get_personal_info()
    education = get_education()
    resume_path = get_resume_path()
    platform = job["platform"]

    # Handshake and ZipRecruiter need persistent contexts for auth
    use_persistent = platform in ("handshake", "ziprecruiter")

    with sync_playwright() as p:
        if use_persistent and platform == "handshake":
            import os
            profile_dir = os.path.join(os.path.dirname(__file__), "..", "data", "browser_profiles", "handshake")
            os.makedirs(profile_dir, exist_ok=True)
            context = p.chromium.launch_persistent_context(user_data_dir=profile_dir, headless=False)
            page = context.new_page()
            browser = None
        elif use_persistent and platform == "ziprecruiter":
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(user_agent=_USER_AGENT)
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
        else:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(user_agent=_USER_AGENT)
            page = context.new_page()
            Stealth().apply_stealth_sync(page)

        try:
            page.goto(job["url"], wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            success = False
            if platform == "indeed":
                success = _auto_submit_indeed(page, personal, education, resume_path)
            elif platform == "ziprecruiter":
                success = _auto_submit_ziprecruiter(page)
            elif platform == "handshake":
                success = _auto_submit_handshake(page, resume_path)

            if success:
                update_job_status(job["id"], "applied", "auto-applied")
                update_apply_method(job["id"], "auto")
                return "applied"
            else:
                # Fall back to manual review with the open browser
                print("  [!] Auto-submit failed — falling back to manual review...")
                _fill_and_upload(page, personal, education, resume_path)
                print("  Browser is open — review and submit manually.")
                print("  Press Enter when done (or type 'skip')...")
                user_input = input("  > ").strip().lower()
                if user_input == "skip":
                    update_job_status(job["id"], "skipped")
                    return "skipped"
                else:
                    update_job_status(job["id"], "applied")
                    update_apply_method(job["id"], "manual")
                    return "applied"

        except Exception as e:
            print(f"  Auto-apply error: {e}")
            update_job_status(job["id"], "error", f"auto-apply failed: {e}")
            return "error"

        finally:
            if browser:
                browser.close()
            else:
                context.close()


def apply_to_job(job):
    """Open a job listing, pre-fill the application, and wait for user review.

    Returns the final status: 'applied', 'skipped', or 'error'.
    """
    personal = get_personal_info()
    education = get_education()
    resume_path = get_resume_path()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(user_agent=_USER_AGENT)
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        try:
            page.goto(job["url"], wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            # Look for "Apply" button and click it
            apply_btn = page.query_selector(
                'a:has-text("Apply"), button:has-text("Apply"), '
                '[class*="apply"], [data-testid*="apply"]'
            )
            if apply_btn:
                apply_btn.click()
                page.wait_for_timeout(2000)

            # Try to fill visible form fields
            inputs = page.query_selector_all(
                'input[type="text"], input[type="email"], input[type="tel"], '
                'input[type="url"], input:not([type])'
            )
            filled_count = 0
            for inp in inputs:
                if inp.is_visible():
                    if _try_fill_field(page, inp, personal, education):
                        filled_count += 1

            # Try to upload resume
            resume_uploaded = _try_upload_resume(page, resume_path)

            # Check if cover letter is needed and generate one
            cover_letter_path = None
            cl_status = scan_page_for_cover_letter(page)
            if cl_status == "required":
                print("\n  [*] Cover letter REQUIRED — generating with Claude...")
                body_text = page.inner_text("body")
                cover_letter_path = generate_cover_letter(
                    job_title=job["title"],
                    company=job["company"],
                    job_description=body_text[:5000],
                )
                if cover_letter_path:
                    print(f"  Cover letter saved: {cover_letter_path}")
                    # Try to upload it to a cover letter file input
                    _try_upload_cover_letter(page, cover_letter_path)
            elif cl_status == "optional":
                print("\n  [i] Cover letter is optional for this posting.")

            print(f"\n  Pre-filled {filled_count} fields.")
            if resume_uploaded:
                print("  Resume uploaded.")
            if cover_letter_path:
                print(f"  Cover letter generated: {cover_letter_path}")
            print("  Browser is open — review the application and submit manually.")
            print("  Press Enter here when done (or type 'skip' to skip)...")

            user_input = input("  > ").strip().lower()

            if user_input == "skip":
                update_job_status(job["id"], "skipped")
                return "skipped"
            else:
                update_job_status(job["id"], "applied")
                return "applied"

        except Exception as e:
            print(f"  Error: {e}")
            update_job_status(job["id"], "error", str(e))
            return "error"

        finally:
            browser.close()


def apply_to_job_web(job):
    """Open a job listing from the web UI, pre-fill the application.

    Opens a browser that stays alive until the user closes it manually.
    Runs in a background thread from Flask.
    """
    personal = get_personal_info()
    education = get_education()
    resume_path = get_resume_path()

    try:
        from playwright.sync_api import sync_playwright
        # Don't use context manager — we need playwright to stay alive
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(user_agent=_USER_AGENT)
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        page.goto(job["url"], wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        # Look for "Apply" button and click it
        apply_btn = page.query_selector(
            'a:has-text("Apply"), button:has-text("Apply"), '
            '[class*="apply"], [data-testid*="apply"]'
        )
        if apply_btn:
            apply_btn.click()
            page.wait_for_timeout(2000)

        # Try to fill visible form fields
        inputs = page.query_selector_all(
            'input[type="text"], input[type="email"], input[type="tel"], '
            'input[type="url"], input:not([type])'
        )
        filled = 0
        for inp in inputs:
            if inp.is_visible():
                if _try_fill_field(page, inp, personal, education):
                    filled += 1

        # Try to upload resume
        _try_upload_resume(page, resume_path)

        # Check cover letter status and generate if needed
        cl_status = scan_page_for_cover_letter(page)
        if cl_status == "required":
            body_text = page.inner_text("body")
            cl_path = generate_cover_letter(
                job_title=job["title"],
                company=job["company"],
                job_description=body_text[:5000],
            )
            if cl_path:
                _try_upload_cover_letter(page, cl_path)

        # Wait for user to close the browser window, then clean up
        browser.on("disconnected", lambda: pw.stop())

    except Exception as e:
        print(f"[apply_to_job_web] Error: {e}")
        try:
            pw.stop()
        except Exception:
            pass


def fetch_job_description(url):
    """Fetch the text content of a job posting page for cover letter generation."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=_USER_AGENT)
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
            text = page.inner_text("body")
            browser.close()
            return text[:8000]
    except Exception as e:
        return f"Error fetching job page: {e}"
