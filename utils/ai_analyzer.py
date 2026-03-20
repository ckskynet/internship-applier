"""AI-powered job fit analysis using Claude API."""

import json
import os

import anthropic

from utils.config import get_personal_info, get_education, get_search_prefs


def analyze_job_fit(job):
    """Analyze how well a job matches the user's profile.

    Args:
        job: dict with keys title, company, location, description, platform, url

    Returns:
        dict with keys: fit_score, strengths, gaps, talking_points,
                        recommendation, summary
        Returns None on failure.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  [!] ANTHROPIC_API_KEY not set. Cannot run fit analysis.")
        return None

    personal = get_personal_info()
    education = get_education()
    prefs = get_search_prefs()

    description = (job.get("description") or "")[:4000]
    if not description:
        description = f"{job['title']} at {job['company']}"

    prompt = f"""Analyze how well this internship matches the candidate's profile.
Return ONLY valid JSON with these exact keys:
- "fit_score": integer 1-10 (10 = perfect match)
- "strengths": list of 2-4 strings — what makes this candidate a good fit
- "gaps": list of 0-3 strings — areas where the candidate may fall short
- "talking_points": list of 2-4 strings — specific things to mention in an application
- "recommendation": one of "apply", "skip", or "maybe"
- "summary": one sentence explaining the fit score

Be realistic. A score of 7+ means strong alignment between the candidate's
background and the job requirements. Score lower if the role needs skills or
experience the candidate clearly lacks.

CANDIDATE PROFILE:
- Name: {personal.get('first_name', '')} {personal.get('last_name', '')}
- University: {education.get('university', '')}
- Degree: {education.get('degree', '')} in {education.get('major', '')}
- Expected Graduation: {education.get('graduation_date', '')}
- Location: {personal.get('location', '')}
- Search Keywords: {', '.join(prefs.get('keywords', []))}

JOB LISTING:
- Title: {job['title']}
- Company: {job['company']}
- Location: {job.get('location', 'Not specified')}
- Platform: {job.get('platform', '')}
- Description: {description}
"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()

        # Extract JSON from response (handle markdown code blocks)
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        return json.loads(text)

    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"  [!] Failed to parse AI response: {e}")
        return None
    except Exception as e:
        print(f"  [!] AI analysis failed: {e}")
        return None
