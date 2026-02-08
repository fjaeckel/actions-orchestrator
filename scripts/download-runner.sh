#!/usr/bin/env bash
#
# download-runner.sh — Download and extract the GitHub Actions runner
# into a target directory. Skips download if already present and matching version.
#
set -euo pipefail

RUNNER_VERSION="${1:-}"
TARGET_DIR="${2:-./_runner_template}"

# ── Detect platform ────────────────────────────────────────────────
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"

case "$OS" in
  linux)  RUNNER_OS="linux" ;;
  darwin) RUNNER_OS="osx" ;;
  *)      echo "Unsupported OS: $OS"; exit 1 ;;
esac

case "$ARCH" in
  x86_64)       RUNNER_ARCH="x64" ;;
  aarch64|arm64) RUNNER_ARCH="arm64" ;;
  *)            echo "Unsupported architecture: $ARCH"; exit 1 ;;
esac

# ── Resolve version ────────────────────────────────────────────────
if [[ -z "$RUNNER_VERSION" ]]; then
  echo "Fetching latest runner version from GitHub…"
  RUNNER_VERSION=$(curl -sL \
    "https://api.github.com/repos/actions/runner/releases/latest" \
    | grep '"tag_name"' | head -1 | sed -E 's/.*"v([^"]+)".*/\1/')
  echo "Latest version: $RUNNER_VERSION"
fi

TARBALL="actions-runner-${RUNNER_OS}-${RUNNER_ARCH}-${RUNNER_VERSION}.tar.gz"
URL="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${TARBALL}"

# ── Check if already downloaded ────────────────────────────────────
VERSION_FILE="${TARGET_DIR}/.runner_version"
if [[ -d "$TARGET_DIR" && -f "$VERSION_FILE" ]]; then
  EXISTING="$(cat "$VERSION_FILE")"
  if [[ "$EXISTING" == "$RUNNER_VERSION" ]]; then
    echo "Runner $RUNNER_VERSION already present in $TARGET_DIR — skipping download."
    exit 0
  fi
fi

# ── Download & extract ─────────────────────────────────────────────
mkdir -p "$TARGET_DIR"

echo "Downloading $URL …"
curl -sL "$URL" -o "/tmp/${TARBALL}"

echo "Extracting to $TARGET_DIR …"
tar -xzf "/tmp/${TARBALL}" -C "$TARGET_DIR"
rm -f "/tmp/${TARBALL}"

echo "$RUNNER_VERSION" > "$VERSION_FILE"
echo "Runner $RUNNER_VERSION ready in $TARGET_DIR"
