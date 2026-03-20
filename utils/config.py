"""Load user profile and search configuration."""

import glob
import os
import yaml

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "profile.yaml")


def load_profile():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def get_personal_info():
    return load_profile()["personal"]


def get_education():
    return load_profile()["education"]


def get_resume_path():
    """Return the path to the resume PDF.

    Looks for a PDF in the resume/ folder first. Falls back to the path
    configured in profile.yaml.
    """
    resume_dir = os.path.join(os.path.dirname(__file__), "..", "resume")
    pdfs = glob.glob(os.path.join(resume_dir, "*.pdf"))
    if pdfs:
        # Use the most recently modified PDF
        return max(pdfs, key=os.path.getmtime)
    return load_profile()["resume"]["path"]


def get_search_prefs():
    return load_profile()["search"]


def get_enabled_platforms():
    profile = load_profile()
    return [p for p, enabled in profile["platforms"].items() if enabled]
