"""Load user profile and search configuration."""

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
    return load_profile()["resume"]["path"]


def get_search_prefs():
    return load_profile()["search"]


def get_enabled_platforms():
    profile = load_profile()
    return [p for p, enabled in profile["platforms"].items() if enabled]
