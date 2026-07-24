#!/usr/bin/env bash
# Delete unsigned release artifacts from v1.1.0 and v1.0.2-beta0
# This removes legacy release assets that lack GPG signatures to eliminate
# supply-chain ambiguity for OpenSSF Scorecard.

set -euo pipefail

REPO="${GH_REPO:-RichardSlater/skills}"
DRY_RUN="${DRY_RUN:-false}"

echo "Deleting unsigned release artifacts from $REPO"
echo "Dry run mode: $DRY_RUN"
echo ""

# Releases and their unsigned assets to delete
declare -A ASSETS_TO_DELETE=(
  ["v1.1.0"]="skills-1.1.0.zip"
  ["v1.0.2-beta0"]="skills-1.0.2-beta0.zip"
)

for release_tag in "${!ASSETS_TO_DELETE[@]}"; do
  asset_name="${ASSETS_TO_DELETE[$release_tag]}"
  echo "Processing release: $release_tag"
  echo "  Looking for asset: $asset_name"

  # Get release ID
  release_id=$(gh api "repos/$REPO/releases/tags/$release_tag" --jq '.id')
  if [[ -z "$release_id" ]]; then
    echo "  ⚠ Release $release_tag not found, skipping"
    continue
  fi

  # Get asset ID for the specific asset
  asset_id=$(gh api "repos/$REPO/releases/$release_id/assets" --jq ".[] | select(.name == \"$asset_name\") | .id")
  if [[ -z "$asset_id" ]]; then
    echo "  ⚠ Asset $asset_name not found in release $release_tag, skipping"
    continue
  fi

  echo "  Found asset ID: $asset_id"

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "  [DRY RUN] Would DELETE asset ID $asset_id ($asset_name)"
  else
    # Delete the asset
    echo "  Deleting asset..."
    gh api --method DELETE "repos/$REPO/releases/assets/$asset_id"
    echo "  ✓ Deleted $asset_name from $release_tag"
  fi

  echo ""
done

if [[ "$DRY_RUN" == "true" ]]; then
  echo "Dry run complete. No assets were deleted."
  echo "Set DRY_RUN=false to perform actual deletion."
else
  echo "Unsigned release artifacts deleted successfully."
  echo "Run Scorecard to verify improvements."
fi
