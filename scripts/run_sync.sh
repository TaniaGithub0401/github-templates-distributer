
#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# List available templates and profiles without running Multi-Gitter
if [[ "${1:-}" == "--list-templates" || "${1:-}" == "--list-profiles" ]]; then
    case "$1" in
        --list-templates)
            export LIST_MODE=templates
            ;;
        --list-profiles)
            export LIST_MODE=profiles
            ;;
    esac

    export CONFIG_PATH="$PROJECT_DIR/config/templates.yml"

    exec python3 "$PROJECT_DIR/scripts/sync_templates.py"
fi

export TEMPLATES_DIR="${TEMPLATES_DIR:-$PROJECT_DIR/../github-templates/templates}"
export CONFIG_PATH="$PROJECT_DIR/config/templates.yml"

# Check required tools and configuration
for tool in multi-gitter python3; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "Error: $tool is not installed."
        exit 1
    fi
done

if [[ -z "${GITHUB_TOKEN:-}" ]]; then
    echo "Error: GITHUB_TOKEN is not configured."
    exit 1
fi

if [[ ! -d "$TEMPLATES_DIR" ]]; then
    echo "Error: Templates directory not found: $TEMPLATES_DIR"
    exit 1
fi

# Parse arguments
DRY_RUN=true
USE_FORK=false
export TEMPLATE_MODE=auto
export TEMPLATE_TEMPLATES=""
export TEMPLATE_PROFILES=""

REPOSITORIES=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --apply)
            DRY_RUN=false
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --fork)
            USE_FORK=true
            shift
            ;;
        --templates)
            if [[ $# -lt 2 || -z "$2" || "$2" == --* ]]; then
                echo "Error: --templates requires a comma-separated list."
                exit 1
            fi
            TEMPLATE_MODE=manual
            TEMPLATE_TEMPLATES="$2"
            shift 2
            ;;

        --profiles)
            if [[ $# -lt 2 || -z "$2" || "$2" == --* ]]; then
                echo "Error: --profiles requires a comma-separated list."
                exit 1
            fi
            TEMPLATE_MODE=manual
            TEMPLATE_PROFILES="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [--apply|--dry-run] [--templates name1,name2] [--profiles name1,name2] owner/repo ..."
            exit 0
            ;;
        -*)
            echo "Error: Unknown option: $1"
            exit 1
            ;;
        *)
            REPOSITORIES+=("$1")
            shift
            ;;
    esac
done

if [[ ${#REPOSITORIES[@]} -eq 0 ]]; then
    echo "Error: At least one repository is required."
    exit 1
fi

# Validate repositories
REPOSITORY_ARGS=()

for repository in "${REPOSITORIES[@]}"; do
    if [[ ! "$repository" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
        echo "Error: Invalid repository: $repository"
        exit 1
    fi
    REPOSITORY_ARGS+=("-R" "$repository")
done

# Generate a branch name from selected profiles and templates
BRANCH_PARTS=()

if [[ -n "$TEMPLATE_PROFILES" ]]; then
    IFS=',' read -ra PROFILES <<< "$TEMPLATE_PROFILES"

    for profile in "${PROFILES[@]}"; do
        BRANCH_PARTS+=("profile-${profile}")
    done
fi

if [[ -n "$TEMPLATE_TEMPLATES" ]]; then
    IFS=',' read -ra TEMPLATES <<< "$TEMPLATE_TEMPLATES"

    for template in "${TEMPLATES[@]}"; do
        BRANCH_PARTS+=("$template")
    done
fi

if [[ ${#BRANCH_PARTS[@]} -eq 0 ]]; then
    BRANCH_NAME="sync-templates-auto"
else
    # Sort names to ensure the same selection produces the same branch
    mapfile -t BRANCH_PARTS < <(
        printf '%s\n' "${BRANCH_PARTS[@]}" | LC_ALL=C sort -u
    )

    BRANCH_SUFFIX=$(IFS=-; echo "${BRANCH_PARTS[*]}")
    BRANCH_NAME="sync-${BRANCH_SUFFIX}"

    # Keep branch names short and deterministic
    if [[ ${#BRANCH_NAME} -gt 70 ]]; then
        BRANCH_HASH=$(
            printf '%s\n' "${BRANCH_PARTS[@]}" |
            sha256sum |
            cut -c1-8
        )

        BRANCH_NAME="sync-templates-${BRANCH_HASH}"
    fi
fi

echo "Branch: $BRANCH_NAME"

# Generate a readable pull request title
if [[ "$TEMPLATE_MODE" == "auto" ]]; then
    PR_TITLE="Sync repository templates (auto)"
else
    TITLE_PARTS=()

    if [[ -n "$TEMPLATE_PROFILES" ]]; then
        IFS=',' read -ra PROFILES <<< "$TEMPLATE_PROFILES"

        for profile in "${PROFILES[@]}"; do
            TITLE_PARTS+=("$profile")
        done
    fi

    if [[ -n "$TEMPLATE_TEMPLATES" ]]; then
        IFS=',' read -ra TEMPLATES <<< "$TEMPLATE_TEMPLATES"

        for template in "${TEMPLATES[@]}"; do
            TITLE_PARTS+=("$template")
        done
    fi

    mapfile -t TITLE_PARTS < <(
        printf '%s\n' "${TITLE_PARTS[@]}" | LC_ALL=C sort -u
    )
    printf -v TITLE_TEXT '%s + ' "${TITLE_PARTS[@]}"
    TITLE_TEXT="${TITLE_TEXT% + }"
    PR_TITLE="Sync templates: $TITLE_TEXT"
fi

PR_BODY="Automated synchronization from mundialis/github-templates.

Selected profiles: ${TEMPLATE_PROFILES:-none}
Selected individual templates: ${TEMPLATE_TEMPLATES:-none}

The changes are generated by github-templates-distributer."

# Configure Multi-Gitter
OPTIONS=()

if [[ "$DRY_RUN" == true ]]; then
    OPTIONS+=("--dry-run")
fi

if [[ "$USE_FORK" == true ]]; then
    OPTIONS+=("--fork")
fi

echo "Starting template synchronization..."
echo "Repositories: ${REPOSITORIES[*]}"
echo "Mode: $TEMPLATE_MODE"
echo "Templates: ${TEMPLATE_TEMPLATES:-none}"
echo "Profiles: ${TEMPLATE_PROFILES:-none}"
echo "Dry run: $DRY_RUN"
echo "Branch: $BRANCH_NAME"
echo "PR title: $PR_TITLE"
echo "PR body:"
echo "$PR_BODY"

multi-gitter run \
    "python3 $PROJECT_DIR/scripts/sync_templates.py" \
    "${REPOSITORY_ARGS[@]}" \
    --base-branch main \
    --git-type cmd \
    "${OPTIONS[@]}" \
    -B "$BRANCH_NAME" \
    -m "Synchronize repository templates" \
    --pr-title "$PR_TITLE" \
    --pr-body "$PR_BODY" \
    --author-name "github-actions[bot]" \
    --author-email "41898282+github-actions[bot]@users.noreply.github.com" \
    --log-level=info
