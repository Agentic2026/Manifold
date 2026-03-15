#!/usr/bin/env bash
# ── Package Frontend ────────────────────────────────────────
# Builds the Vite frontend and produces a compressed tarball
# (frontend.tar.xz) suitable for the web Docker image.
#
# Usage:
#   ./scripts/ci/package_frontend.sh [output_dir]
#
# The resulting archive contains a single top-level `dist/`
# directory.
# ────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WEB_DIR="$REPO_ROOT/web"
OUTPUT_DIR="${1:-$REPO_ROOT}"

echo "▸ Installing frontend dependencies …"
cd "$WEB_DIR"
npm ci --ignore-scripts

echo "▸ Building frontend …"
npm run build

echo "▸ Packaging frontend.tar.xz …"
tar -C "$WEB_DIR" -cJf "$OUTPUT_DIR/frontend.tar.xz" dist

echo "✓ Frontend artifact: $OUTPUT_DIR/frontend.tar.xz"
ls -lh "$OUTPUT_DIR/frontend.tar.xz"
