# GitHub Workflow Template Distributor

Synchronize shared GitHub Actions workflows across repositories using [Multi-Gitter](https://github.com/lindell/multi-gitter). Templates are maintained in [mundialis/github-templates](https://github.com/mundialis/github-templates); this repository provides a GitHub Actions interface and a command-line script to distribute them.

The distributor proposes changes through **pull requests**. It does not merge them. Review each PR before merging, particularly when a template replaces an existing workflow.

## Run with GitHub Actions

Each user runs the workflow from a personal fork of the distributor and uses their own token.

### One-time setup

1. **Fork** [mundialis/github-templates-distributer](https://github.com/mundialis/github-templates-distributer) to your GitHub account. The workflow uses templates from the official [mundialis/github-templates](https://github.com/mundialis/github-templates) repository.

   **Note:** Keep your fork up to date with the official distributor. The workflow must be present on your fork's default branch (usually `main`) to be available in GitHub Actions.

2. Open **Actions** in your fork and enable workflows if GitHub asks you to.
3. Create a **personal access token (PAT)** in **GitHub → Settings → Developer settings → Personal access tokens**. Prefer a fine-grained token limited to the repositories you intend to update, with the permissions needed to create branches and PRs (typically **Contents: read and write** and **Pull requests: read and write**).
4. In **your fork**, go to **Settings → Secrets and variables → Actions → New repository secret**. Save your PAT as `MULTI_GITTER_TOKEN`.

### Start a distribution

1. In **your fork**, open **Actions → Distribute repository templates → Run workflow**.
2. Select the branch containing the distributor workflow (normally `main`).
3. Enter the target repositories under **Repositories**, separated by spaces, for example:

   ```text
   mundialis/grass-gis-helpers actinia-org/actinia-core
   ```

4. Choose a **Profile**, individual template checkboxes, or both. For example, **Security** selects CodeQL, SBOM Vulnerability Scan and Third-Party Licenses. Choose **None - Individual templates only** to select just individual workflows.
5. Check the repository names and selections, then click **Run workflow**.
6. Inspect the run logs and review the generated pull requests before merging.

### Permissions and forks

The **Use forks** option determines where Multi-Gitter creates the branches containing the template updates:

- **Disabled (default):** Multi-Gitter creates branches directly in the selected target repositories. Your token must have write access to these repositories.
- **Enabled:** Multi-Gitter creates branches in your personal forks and opens pull requests to the original repositories. If a fork does not exist yet, Multi-Gitter can create it automatically, provided your token has the necessary permissions and the organization allows forking.

When **Use forks** is enabled, you do not need to fork each target repository manually.

## Run from a local terminal

Use the terminal to preview changes with `--dry-run` before creating pull requests.

### Install and set up

**Requirements:** Git, Python 3 (`venv` and `pip`), and [Multi-Gitter](https://github.com/lindell/multi-gitter). Make sure Multi-Gitter is installed and available in your `PATH`.

```bash
curl -fsSL https://raw.githubusercontent.com/lindell/multi-gitter/master/install.sh | sh
```

Clone the two official mundialis repositories into the same directory:

```bash
git clone https://github.com/mundialis/github-templates-distributer.git
git clone https://github.com/mundialis/github-templates.git

cd github-templates-distributer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

By default, the distributor reads the shared templates from `../github-templates/templates`. If the repositories are stored in different locations, specify the template directory using `TEMPLATES_DIR`:

```bash
export TEMPLATES_DIR="/path/to/github-templates/templates"
```

### Authenticate

The terminal script requires `GITHUB_TOKEN` for synchronization. If you have an authenticated GitHub CLI (`gh`) with suitable permissions:

```bash
gh auth status
export GITHUB_TOKEN="$(gh auth token)"
```

Alternatively, set `GITHUB_TOKEN` with a PAT through your approved secret-management method. Make sure it has access to the target repositories.

### Select templates and preview changes

List the configured profiles and templates:

```bash
./scripts/run_sync.sh --list-profiles
./scripts/run_sync.sh --list-templates
```

Preview a single-repository update using the `security` profile:

```bash
./scripts/run_sync.sh \
  --dry-run \
  --profiles security \
  actinia-org/actinia-core
```

You can also select individual templates or combine a profile with additional templates:

```bash
./scripts/run_sync.sh \
  --dry-run \
  --profiles security \
  --templates post-pr-reviews \
  actinia-org/actinia-core \
  actinia-org/actinia-module-plugin
```

A local run defaults to **dry-run** if neither `--dry-run` nor `--apply` is specified. Dry-run runs the synchronization in temporary clones but does not push branches or create PRs.

### Create pull requests

Once the preview looks correct, run the same selection with `--apply`:

```bash
./scripts/run_sync.sh \
  --apply \
  --profiles security \
  actinia-org/actinia-core
```

If you cannot push directly to a target repository, Multi-Gitter can instead work through a fork, where permitted:

```bash
./scripts/run_sync.sh \
  --apply \
  --fork \
  --profiles security \
  actinia-org/actinia-core
```

The `--fork` option uses forks of the target repositories. Your token still needs the necessary access, and organization policies may restrict forking.

### Command-line options

| Option | Description |
| --- | --- |
| `--dry-run` | Preview changes without pushing or creating PRs (default). |
| `--apply` | Push branches and create PRs for changed repositories. |
| `--profiles name1,name2` | Select profiles (comma-separated). |
| `--templates name1,name2` | Select individual templates (comma-separated). |
| `--fork` | Use Multi-Gitter's fork mode for target repositories. |
| `--list-profiles` | Show profiles and their templates. |
| `--list-templates` | Show available template names. |
| `--help` | Show command usage. |
| `OWNER/REPO ...` | One or more target repositories, separated by spaces. |

Provide at least one profile or template and at least one repository when synchronizing.

## Available profiles

See [`config/templates.yml`](config/templates.yml) for the current configuration. You can combine profiles and individual templates; duplicate selections are processed only once.

| Profile | Included templates |
| --- | --- |
| `general` | CodeQL, Linting, SBOM Vulnerability Scan, Third-Party Licenses |
| `grass` | General + GRASS Manual and GRASS Test |
| `python` | General + Post PR Reviews and Python Publish |
| `quality` | CodeQL, Linting, Post PR Reviews |
| `security` | CodeQL, SBOM Vulnerability Scan, Third-Party Licenses |
| `all` | All nine templates |

Individual template names:

```text
codeql                    grass-manual              grass-test
linting                   post-pr-reviews           python-publish
python-test-publish       sbom-vulnerability-scan   third-party-licenses
```

## What happens to existing workflows?

The distributor updates only workflows matching the configured detection rules. Depending on the template, it may replace a workflow, merge selected settings, or preserve repository-specific dependency inputs. A custom workflow may be skipped; replacement can also fail safely if additional jobs are detected.

Multi-Gitter uses a deterministic branch name for each selection. If a branch already exists, its default conflict strategy is to **skip** it rather than overwrite the existing branch. Re-running the same selection does not automatically update an open PR. Resolve the existing PR or branch as appropriate before applying a new update.

## Updating or adding templates (maintainers)

1. Update the source workflow in [mundialis/github-templates](https://github.com/mundialis/github-templates).
2. Add or update its configuration in [`config/templates.yml`](config/templates.yml), including the detection and synchronization rules.
3. Update the appropriate profiles and, if needed, the individual-template checkboxes in [`.github/workflows/distribute-templates.yml`](.github/workflows/distribute-templates.yml).
4. Test against a disposable local repository or personal fork, then use a local `--dry-run` and inspect the output before proposing changes.

For `replace` templates, use `detect_by` when possible to match an existing reusable workflow rather than trusting a filename alone.
