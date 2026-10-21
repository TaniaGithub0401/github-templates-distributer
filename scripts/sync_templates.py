
#!/usr/bin/env python3
"""Synchronize shared templates with a target GitHub repository."""

import os
import re
import subprocess
from pathlib import Path

import yaml


def get_target_repository():
    """Identify the target repository from its Git remote."""
    repository = os.environ.get("TARGET_REPOSITORY")
    if repository:
        return repository

    remote = subprocess.check_output(
        ["git", "remote", "get-url", "origin"],
        text=True,
    ).strip()

    match = re.search(r"github\.com[:/]([^/]+)/([^/\s]+)", remote)
    if not match:
        raise ValueError(f"Cannot identify GitHub repository: {remote}")

    owner, repo = match.groups()
    return f"{owner}/{repo.removesuffix('.git')}"


def load_config(config_path):
    """Load template definitions and profiles."""
    with config_path.open(encoding="utf-8") as file:
        return yaml.safe_load(file)


def parse_selection(value):
    """Convert a comma-separated string into a set of names."""
    return {name.strip() for name in value.split(",") if name.strip()}


def select_templates(config):
    """Resolve templates selected manually or automatically."""
    mode = os.environ.get("TEMPLATE_MODE", "auto")

    if mode == "manual":
        templates = parse_selection(os.environ.get("TEMPLATE_TEMPLATES", ""))
        profiles = parse_selection(os.environ.get("TEMPLATE_PROFILES", ""))

        if not templates and not profiles:
            raise ValueError("Manual mode requires templates or profiles")

    elif mode == "auto":
        templates = set(config.get("default_templates", []))
        profiles = set()

        if config.get("rules"):
            raise ValueError("Automatic rules are not implemented yet")

    else:
        raise ValueError(f"Unknown template mode: {mode}")

    available_templates = config["templates"]
    available_profiles = config.get("profiles", {})

    unknown_profiles = profiles - available_profiles.keys()
    if unknown_profiles:
        raise ValueError(
            f"Unknown profiles: {', '.join(sorted(unknown_profiles))}"
        )

    for profile in profiles:
        templates.update(available_profiles[profile])

    unknown_templates = templates - available_templates.keys()
    if unknown_templates:
        raise ValueError(
            f"Unknown templates: {', '.join(sorted(unknown_templates))}"
        )

    print(f"Template mode: {mode}")
    print(f"Selected templates: {', '.join(sorted(templates)) or 'none'}")

    return templates


def synchronize_templates(selected, config, templates_dir):
    """Copy selected templates into the target repository."""
    target_dir = Path.cwd().resolve()
    templates_dir = templates_dir.resolve()

    for name in sorted(selected):
        template = config["templates"][name]

        source = (templates_dir / template["source"]).resolve()
        destination = (target_dir / template["destination"]).resolve()

        if not source.is_relative_to(templates_dir):
            raise ValueError(f"Invalid template source: {name}")

        if not destination.is_relative_to(target_dir):
            raise ValueError(f"Invalid template destination: {name}")

        if not source.is_file():
            raise FileNotFoundError(f"Template not found: {source}")

        content = source.read_bytes()

        if destination.is_file() and destination.read_bytes() == content:
            print(f"Unchanged: {template['destination']}")
            continue

        if destination.exists() and not destination.is_file():
            raise ValueError(f"Destination is not a file: {destination}")

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)

        print(f"Updated: {template['destination']}")


def main():
    templates_dir = Path(os.environ["TEMPLATES_DIR"])
    config_path = Path(os.environ["CONFIG_PATH"])

    print(f"Processing repository: {get_target_repository()}")

    config = load_config(config_path)
    selected = select_templates(config)

    if not selected:
        print("No templates selected.")
        return

    synchronize_templates(selected, config, templates_dir)


if __name__ == "__main__":
    main()
