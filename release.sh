#!/bin/bash
# ============================================================
# Release Script - Bump version, commit, tag, and push
# ============================================================
# Usage:
#   ./release.sh 1.3.0
#   ./release.sh 1.3.0 "Added new feature X"
# ============================================================

set -e

if [ -z "$1" ]; then
    echo ""
    echo "  Usage: ./release.sh <version> [message]"
    echo ""
    echo "  Examples:"
    echo "    ./release.sh 1.3.0"
    echo "    ./release.sh 1.3.0 \"Added dark mode and bug fixes\""
    echo ""
    exit 1
fi

VERSION="$1"
MESSAGE="${2:-Release v$VERSION}"

cd "$(dirname "$0")"

echo ""
echo "  Releasing v$VERSION..."
echo ""

# 1. Update APP_VERSION in app.py
sed -i.bak "s/^APP_VERSION = \".*\"/APP_VERSION = \"$VERSION\"/" app.py && rm -f app.py.bak
echo "  [1/4] APP_VERSION updated to $VERSION"

# 2. Commit
git add -A
git commit -m "v$VERSION - $MESSAGE"
echo "  [2/4] Committed"

# 3. Tag (replace if exists)
git tag -d "v$VERSION" 2>/dev/null || true
git tag "v$VERSION"
echo "  [3/4] Tagged v$VERSION"

# 4. Push
git push
git push origin "v$VERSION" --force
echo "  [4/4] Pushed"

echo ""
echo "  Done! v$VERSION released."
echo "  GitHub Actions will build binaries automatically."
echo "  Clients will see the update in-app."
echo ""
