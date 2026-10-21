
#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

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

# Configure Multi-Gitter
OPTIONS=()

if [[ "$DRY_RUN" == true ]]; then
    OPTIONS+=("--dry-run")
fi

echo "Starting template synchronization..."
echo "Repositories: ${REPOSITORIES[*]}"
echo "Mode: $TEMPLATE_MODE"
echo "Templates: ${TEMPLATE_TEMPLATES:-none}"
echo "Profiles: ${TEMPLATE_PROFILES:-none}"
echo "Dry run: $DRY_RUN"

multi-gitter run \
    "python3 $PROJECT_DIR/scripts/sync_templates.py" \
    "${REPOSITORY_ARGS[@]}" \
    --base-branch main \
    --fork \
    --git-type cmd \
    "${OPTIONS[@]}" \
    -B sync-repository-templates \
    -m "Synchronize repository templates" \
    --pr-title "Synchronize shared repository templates" \
    --pr-body "Synchronize shared files from the central template repository." \
    --author-name "github-actions[bot]" \
    --author-email "41898282+github-actions[bot]@users.noreply.github.com" \
    --log-level=info
