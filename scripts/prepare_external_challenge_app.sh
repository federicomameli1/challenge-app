#!/usr/bin/env sh
# prepare_external_challenge_app.sh
#
# Utility script to fetch/update colleague repository and prepare local APCS docs
# for Agent 4 ingestion through the `apcs_doc_bundle` adapter.
#
# Default behavior:
# - clones/updates https://github.com/federicomameli1/challenge-app
# - stores it under ./external_sources/challenge-app
# - validates expected Dataset/APCS_* files
#
# Usage:
#   sh scripts/prepare_external_challenge_app.sh
#   sh scripts/prepare_external_challenge_app.sh --force
#   sh scripts/prepare_external_challenge_app.sh --branch main --dest external_sources/challenge-app
#   sh scripts/prepare_external_challenge_app.sh --repo https://github.com/federicomameli1/challenge-app --dest external_sources/challenge-app
#
# Notes:
# - Run from project root (Challange_agent1) for default paths to align.
# - This script is POSIX sh compatible.

set -eu

REPO_URL="https://github.com/federicomameli1/challenge-app"
BRANCH="main"
DEST_DIR="external_sources/challenge-app"
FORCE="0"
NO_UPDATE="0"

print_help() {
  cat <<'EOF'
prepare_external_challenge_app.sh

Options:
  --repo <url>        Git repository URL (default: federicomameli1/challenge-app)
  --branch <name>     Branch to checkout/update (default: main)
  --dest <path>       Local destination directory (default: external_sources/challenge-app)
  --force             Remove destination and re-clone from scratch
  --no-update         If repo exists, skip fetch/pull
  -h, --help          Show this help

Examples:
  sh scripts/prepare_external_challenge_app.sh
  sh scripts/prepare_external_challenge_app.sh --force
  sh scripts/prepare_external_challenge_app.sh --dest external_sources/challenge-app --branch main
EOF
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo)
      [ "$#" -ge 2 ] || fail "--repo requires a value"
      REPO_URL="$2"
      shift 2
      ;;
    --branch)
      [ "$#" -ge 2 ] || fail "--branch requires a value"
      BRANCH="$2"
      shift 2
      ;;
    --dest)
      [ "$#" -ge 2 ] || fail "--dest requires a value"
      DEST_DIR="$2"
      shift 2
      ;;
    --force)
      FORCE="1"
      shift
      ;;
    --no-update)
      NO_UPDATE="1"
      shift
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *)
      fail "Unknown argument: $1 (use --help)"
      ;;
  esac
done

need_cmd git

echo "==> Preparing colleague dataset source"
echo "    repo   : $REPO_URL"
echo "    branch : $BRANCH"
echo "    dest   : $DEST_DIR"

if [ "$FORCE" = "1" ] && [ -e "$DEST_DIR" ]; then
  echo "==> --force enabled: removing existing destination"
  rm -rf "$DEST_DIR"
fi

if [ -d "$DEST_DIR/.git" ]; then
  echo "==> Existing git repo detected at $DEST_DIR"
  if [ "$NO_UPDATE" = "1" ]; then
    echo "==> --no-update enabled: skipping fetch/pull"
  else
    echo "==> Updating repository"
    git -C "$DEST_DIR" fetch --all --prune
    git -C "$DEST_DIR" checkout "$BRANCH"
    git -C "$DEST_DIR" pull --ff-only origin "$BRANCH"
  fi
else
  if [ -e "$DEST_DIR" ] && [ ! -d "$DEST_DIR/.git" ]; then
    fail "Destination exists but is not a git repo: $DEST_DIR (use --force)"
  fi
  echo "==> Cloning repository"
  mkdir -p "$(dirname "$DEST_DIR")"
  git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$DEST_DIR"
fi

DATASET_DIR="$DEST_DIR/Dataset"
[ -d "$DATASET_DIR" ] || fail "Dataset directory not found: $DATASET_DIR"

echo "==> Validating expected APCS files"

REQUIRED_FILES="
APCS_Emails_v1.0.txt
"

OPTIONAL_FILES="
APCS_Requirements_v1.0.docx
APCS_Module_Version_Inventory_v1.0.docx
APCS_Test_Procedure_v1.0.docx
APCS_VDD_v1.0.docx
APCS_Inconsistencies_map_v1.0.docx
"

for f in $REQUIRED_FILES; do
  [ -f "$DATASET_DIR/$f" ] || fail "Missing required file: $DATASET_DIR/$f"
done

for f in $OPTIONAL_FILES; do
  if [ -f "$DATASET_DIR/$f" ]; then
    echo "    [+] $f"
  else
    echo "    [ ] $f (not found; adapter may fallback)"
  fi
done

echo "==> Preparation complete"
echo ""
echo "You can now run Agent 4 (LangChain pipeline) against colleague docs:"
echo "  python3 scripts/run_agent4_langchain.py \\"
echo "    --dataset-root \"$DATASET_DIR\" \\"
echo "    --source-adapter-kind apcs_doc_bundle \\"
echo "    --scenario-id APCS-S4-001 \\"
echo "    --pretty"
echo ""
echo "Or evaluate all available scenarios from this source:"
echo "  python3 scripts/run_agent4_langchain.py \\"
echo "    --dataset-root \"$DATASET_DIR\" \\"
echo "    --source-adapter-kind apcs_doc_bundle \\"
echo "    --evaluate-all \\"
echo "    --pretty"
