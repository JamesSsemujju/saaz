#!/bin/bash
# ship.sh: put the newest Saaz zip from Downloads into the repo, build, check, and push.
# Working folder: /Users/james/Desktop/Saaz (zips go here, the repo is saaz/ inside it).
# Usage (from anywhere):  bash ~/Desktop/Saaz/saaz/tools/ship.sh
# Optional: SAAZ_REPO=/path/to/saaz  SAAZ_ZIP=/path/to/file.zip
set -euo pipefail

WORK="$HOME/Desktop/Saaz"
if [ -n "${SAAZ_REPO:-}" ]; then REPO="$SAAZ_REPO"
elif [ -d "$WORK/.git" ]; then REPO="$WORK"
else REPO="$WORK/saaz"; fi
ZIP="${SAAZ_ZIP:-$(ls -t "$WORK"/Saaz_Platform_*.zip "$HOME"/Downloads/Saaz_Platform_*.zip 2>/dev/null | head -1 || true)}"

[ -d "$REPO/.git" ] || { echo "No repo at $REPO. Clone it first (see README, Shipping)."; exit 1; }
[ -n "$ZIP" ] && [ -f "$ZIP" ] || { echo "No Saaz_Platform_*.zip in $WORK or Downloads."; exit 1; }

cd "$REPO"
echo "Zip:  $(basename "$ZIP")"
git pull --ff-only origin main
unzip -oq "$ZIP" -d .
python3 build.py
git add docs src supabase tools tests project-docs build.py README.md

if git diff --cached --quiet; then
  ahead=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)
  if [ "$ahead" -gt 0 ]; then
    echo "$ahead saved update(s) not on GitHub yet. Pushing now."
    git push origin main && echo "Pushed. The site updates in about a minute."
  else
    echo "Nothing changed. Nothing to push."
  fi
  exit 0
fi
git diff --cached --stat | tail -1
read -r -p "Push to the live site? (y/n) " answer
case "$answer" in [yY]|[yY][eE][sS]) answer=y;; esac
if [ "$answer" = "y" ]; then
  git commit -q -m "Update from $(basename "$ZIP")"
  git push origin main
  echo "Pushed. The site updates in about a minute."
else
  git reset -q
  echo "Not pushed. Files are unpacked in $REPO but not committed."
fi
