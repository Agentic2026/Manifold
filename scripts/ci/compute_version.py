#!/usr/bin/env python3
"""Compute version metadata for Manifold releases.

Outputs key=value pairs suitable for ``$GITHUB_OUTPUT``:

    version=0.3.0
    tag=v0.3.0
    image_tag=0.3.0
    dev_tag=sha-abc1234

Usage (CI):
    python scripts/ci/compute_version.py >> "$GITHUB_OUTPUT"

The version is derived from:
  1. A git tag matching ``v*`` on the current commit (release build)
  2. Otherwise, a dev tag based on the short SHA
"""
from __future__ import annotations

import os
import subprocess
import sys


def _run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True).strip()


def main() -> None:
    sha = os.environ.get("GITHUB_SHA") or _run(["git", "rev-parse", "HEAD"])
    short_sha = sha[:7]

    # Check for a release tag on the current commit
    try:
        tag = _run(["git", "describe", "--exact-match", "--tags", "HEAD"])
    except subprocess.CalledProcessError:
        tag = ""

    if tag.startswith("v"):
        version = tag.lstrip("v")
        image_tag = version
    else:
        version = f"0.0.0-dev+{short_sha}"
        image_tag = f"sha-{short_sha}"

    lines = [
        f"version={version}",
        f"tag=v{version}" if not tag else f"tag={tag}",
        f"image_tag={image_tag}",
        f"dev_tag=sha-{short_sha}",
        f"sha={sha}",
        f"short_sha={short_sha}",
    ]

    for line in lines:
        print(line)

    # Write to GITHUB_OUTPUT if available
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a") as f:
            for line in lines:
                f.write(line + "\n")


if __name__ == "__main__":
    main()
