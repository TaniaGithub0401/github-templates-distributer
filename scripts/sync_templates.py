
#!/usr/bin/env python3
"""Synchronize shared templates with GitHub repositories."""

import os
import re
import subprocess
from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap


DEPENDENCY_MARKER = "# TEMPLATE_DEPENDENCY_INPUT"


def get_target_repository():
    """Identify the GitHub repository from its Git remote."""
    repository = os.environ.get("TARGET_REPOSITORY")
    if repository:
        return repository

    remote = subprocess.check_output(
        ["git", "remote", "get-url", "origin"],
        text=True,
    ).strip()

    match = re.search(r"github\.com[:/]([^/]+)/([^/\s]+)", remote)
    if not match:
        raise ValueError(f"Cannot identify repository: {remote}")

    owner, repo = match.groups()
    return f"{owner}/{repo.removesuffix('.git')}"


def load_config(path):
    """Load template definitions and profiles."""
    with path.open(encoding="utf-8") as file:
        return YAML(typ="safe").load(file)


def parse_selection(value):
    """Parse comma-separated template or profile names."""
    return {item.strip() for item in value.split(",") if item.strip()}


def resolve_profile(name, profiles, visited=None):
    """Resolve a profile and all its included profiles."""
    if visited is None:
        visited = set()

    if name not in profiles:
        raise ValueError(f"Unknown profile: {name}")

    if name in visited:
        raise ValueError(f"Circular profile dependency: {name}")

    visited.add(name)

    profile = profiles[name]
    selected = set(profile.get("templates", []))

    for included in profile.get("includes", []):
        selected.update(
            resolve_profile(included, profiles, visited)
        )

    visited.remove(name)

    return selected


def select_templates(config):
    """Resolve templates from manual selection or defaults."""
    mode = os.environ.get("TEMPLATE_MODE", "auto")

    if mode == "manual":
        selected = parse_selection(
            os.environ.get("TEMPLATE_TEMPLATES", "")
        )
        profiles = parse_selection(
            os.environ.get("TEMPLATE_PROFILES", "")
        )

        if not selected and not profiles:
            raise ValueError("Manual mode requires templates or profiles")

    elif mode == "auto":
        selected = set(config.get("default_templates", []))
        profiles = set()

        if config.get("rules"):
            raise ValueError("Automatic rules are not implemented yet")

    else:
        raise ValueError(f"Unknown template mode: {mode}")

    available_profiles = config.get("profiles", {})

    for profile in profiles:
        selected.update(
            resolve_profile(profile, available_profiles)
        )

    unknown = selected - config["templates"].keys()
    if unknown:
        raise ValueError(f"Unknown templates: {sorted(unknown)}")

    print(f"Template mode: {mode}")
    print(f"Selected templates: {', '.join(sorted(selected)) or 'none'}")

    return selected


def read_yaml(path):
    """Read a GitHub workflow while retaining its YAML structure."""
    yaml = YAML()
    yaml.preserve_quotes = True

    with path.open(encoding="utf-8") as file:
        return yaml.load(file)


def find_existing_workflows(template, target_dir):
    """Find workflows using the configured reusable workflow."""
    workflow_dir = target_dir / ".github/workflows"
    reusable = template["detect_by"]
    matches = []

    if not workflow_dir.is_dir():
        return matches

    for path in sorted(workflow_dir.iterdir()):
        if not path.is_file() or path.suffix not in (".yml", ".yaml"):
            continue

        data = read_yaml(path)
        if not isinstance(data, dict):
            continue

        for job_name, job in (data.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue

            uses = job.get("uses", "")
            if isinstance(uses, str) and uses.startswith(reusable + "@"):
                matches.append((path, job_name))

    return matches


def get_dependency_input(job, allowed):
    """Identify the single dependency source used by a job."""
    inputs = job.get("with") or {}

    found = {
        key: inputs[key]
        for key in allowed
        if key in inputs and inputs[key] is not None
    }

    if len(found) != 1:
        raise ValueError(
            f"Expected exactly one dependency input, found: {found}"
        )

    key, value = next(iter(found.items()))

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Invalid dependency input: {key}={value}")

    return key, value


def synchronize_mapping(existing, central, protected=()):
    """Apply central values with minimal edits, preserving selected local keys.

    Existing nodes are left untouched when their values already agree. This
    helps preserve quotes, comments, and formatting in unchanged sections.
    """
    protected = set(protected)
    changed = False

    for key in list(existing):
        if key not in central and key not in protected:
            del existing[key]
            changed = True

    for key, value in central.items():
        if key in protected:
            continue

        if key not in existing:
            existing[key] = value
            changed = True
        elif isinstance(existing[key], dict) and isinstance(value, dict):
            changed |= synchronize_mapping(existing[key], value)
        elif existing[key] != value:
            existing[key] = value
            changed = True

    return changed


def render_workflow(source, existing_path, job_name, template):
    """Synchronize common fields while preserving local workflow settings."""
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)

    source_text = source.read_text(encoding="utf-8")
    if source_text.count(DEPENDENCY_MARKER) != 1:
        raise ValueError(f"Missing or duplicate dependency marker: {source}")

    source_text = re.sub(
        r"^[ \t]*# TEMPLATE_DEPENDENCY_INPUT[ \t]*\n",
        "",
        source_text,
        count=1,
        flags=re.MULTILINE,
    )

    central = yaml.load(source_text)
    existing = read_yaml(existing_path)

    if not isinstance(central, dict) or not isinstance(existing, dict):
        raise ValueError("Workflow must be a YAML mapping")

    reusable = template["detect_by"] + "@"
    central_jobs = [
        job for job in (central.get("jobs") or {}).values()
        if isinstance(job, dict)
        and isinstance(job.get("uses"), str)
        and job["uses"].startswith(reusable)
    ]
    if len(central_jobs) != 1:
        raise ValueError(f"Expected one matching reusable job: {source}")

    central_job = central_jobs[0]
    existing_job = existing["jobs"][job_name]
    input_key, input_value = get_dependency_input(
        existing_job, template["dependency_inputs"]
    )

    # Derive the desired inputs from the central template, with local overrides.
    central_inputs = central_job.get("with") or CommentedMap()
    for candidate in template["dependency_inputs"]:
        central_inputs.pop(candidate, None)
    central_inputs.insert(0, input_key, input_value)

    existing_inputs = existing_job.get("with") or {}
    for key in template.get("preserve_inputs", []):
        if key in existing_inputs:
            central_inputs[key] = existing_inputs[key]
    central_job["with"] = central_inputs

    changed = False

    # The central template controls triggers and other common top-level fields.
    # The existing workflow keeps its human-readable name and job identities.
    for key, value in central.items():
        if key in ("name", "jobs"):
            continue
        if key not in existing:
            existing[key] = value
            changed = True
        elif isinstance(existing[key], dict) and isinstance(value, dict):
            changed |= synchronize_mapping(existing[key], value)
        elif existing[key] != value:
            existing[key] = value
            changed = True

    # A removed top-level trigger is intentional: the central template owns 'on'.
    if "on" not in central and "on" in existing:
        del existing["on"]
        changed = True

    # Only the matched reusable job is managed; other jobs stay untouched.
    changed |= synchronize_mapping(existing_job, central_job)

    # Do not reserialize unchanged files just to normalize their formatting.
    if not changed:
        return existing_path.read_bytes()
    output = StringIO()
    yaml.dump(existing, output)
    return output.getvalue().encode("utf-8")


def write_template(destination, content):
    """Write files only when their content differs."""
    if destination.is_file() and destination.read_bytes() == content:
        print(f"Unchanged: {destination}")
        return

    if destination.exists() and not destination.is_file():
        raise ValueError(f"Destination is not a file: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)

    print(f"Updated: {destination}")


def synchronize_templates(selected, config, templates_dir):
    """Apply regular or parameterized templates."""
    target_dir = Path.cwd().resolve()
    templates_dir = templates_dir.resolve()

    for name in sorted(selected):
        template = config["templates"][name]
        source = (templates_dir / template["source"]).resolve()

        if not source.is_relative_to(templates_dir):
            raise ValueError(f"Invalid source path: {name}")

        if not source.is_file():
            raise FileNotFoundError(source)

        # Parameterized workflows: update their existing instances.
        if "detect_by" in template:
            workflows = find_existing_workflows(template, target_dir)

            if not workflows:
                print(f"No existing workflow found: {name}")
                continue

            # Avoid updating the same file twice.
            paths = [path for path, _ in workflows]
            if len(paths) != len(set(paths)):
                raise ValueError(f"Multiple matching jobs in one file: {name}")

            for path, job_name in workflows:
                destination = path.resolve()

                if not destination.is_relative_to(target_dir):
                    raise ValueError(f"Invalid destination: {destination}")

                content = render_workflow(
                    source, destination, job_name, template
                )
                write_template(destination, content)

            continue

        # Regular templates: copy the file as it is.
        destination = (target_dir / template["destination"]).resolve()

        if not destination.is_relative_to(target_dir):
            raise ValueError(f"Invalid destination: {destination}")

        write_template(destination, source.read_bytes())


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
