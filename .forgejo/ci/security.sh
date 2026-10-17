#!/usr/bin/env bash
# Sicherheitsprüfung für Familienhub (CI und lokal): fertige Werkzeuge, feste Versionen, geprüfte Prüfsummen.
#   gitleaks     – keine Geheimnisse im Repo (ganze Historie)
#   osv-scanner  – bekannte Lücken in Abhängigkeiten (Python requirements.txt, Flutter pubspec.lock)
#   pip-audit    – bekannte Lücken in den Python-Abhängigkeiten (PyPI-Advisories)
#   trivy        – Fehlkonfigurationen in Dockerfile/Compose (HIGH/CRITICAL)
#   bandit       – unsichere Muster im Python-Code (ab mittlerer Schwere)
#   semgrep      – Sicherheitsregeln für Python
# Aufruf: .forgejo/ci/security.sh [werkzeug …]   (ohne Angabe: alle)
set -euo pipefail
cd "$(dirname "$0")/../.."
BIN="${TOOLS_DIR:-/tmp/security-tools}"; mkdir -p "$BIN"; export PATH="$BIN:$PATH"

fetch() { # name url sha256 [tar-member]
  local name=$1 url=$2 sum=$3 member=${4:-}
  [ -x "$BIN/$name" ] && return 0
  local tmp; tmp=$(mktemp)
  curl -fsSL "$url" -o "$tmp"
  echo "$sum  $tmp" | sha256sum -c --quiet - || { echo "Prüfsumme falsch: $name" >&2; exit 1; }
  if [ -n "$member" ]; then tar -xzf "$tmp" -C "$BIN" "$member"; else install -m 0755 "$tmp" "$BIN/$name"; fi
  rm -f "$tmp"
}

python_tools() {
  [ -x "$BIN/venv/bin/semgrep" ] && "$BIN/venv/bin/python" -c 1 2>/dev/null && return 0
  rm -rf "$BIN/venv"
  # Python 3.12 wie das Backend (cookidoo-api braucht ≥ 3.12); uv holt es bei Bedarf
  command -v uv >/dev/null || { curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null; export PATH="$HOME/.local/bin:$PATH"; }
  uv venv -q --python 3.12 --python-preference only-managed "$BIN/venv"
  uv pip install -q -p "$BIN/venv" pip pip-audit==2.10.1 bandit==1.9.4 semgrep==1.181.0
}

run_gitleaks() {
  fetch gitleaks https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz \
    551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb gitleaks
  gitleaks git . --redact --no-banner --exit-code 1
}

run_osv() {
  fetch osv-scanner https://github.com/google/osv-scanner/releases/download/v2.7.0/osv-scanner_linux_amd64 \
    160c6253e2922e9e0a6a9771c5c4c40a4b3c6090b34a3cdd5e80c96cc2e4218b
  # Nur Flutter: für requirements.txt rät OSV die Versionen indirekter Pakete; Python prüft pip-audit
  osv-scanner scan source --lockfile app/pubspec.lock
}

run_pip_audit() {
  python_tools
  "$BIN/venv/bin/pip-audit" -r backend/requirements.txt --progress-spinner off --strict
}

run_trivy() {
  fetch trivy https://github.com/aquasecurity/trivy/releases/download/v0.76.0/trivy_0.76.0_Linux-64bit.tar.gz \
    e24b1c51293c1b15e4ba8d45bbc7891ba053f90278ec2698f3562c993e145fe7 trivy
  # .forgejo/ci: Hilfs-Images nur für die CI, werden nie ausgeliefert
  trivy config --quiet --severity HIGH,CRITICAL --exit-code 1 --skip-dirs .forgejo/ci .
}

run_bandit() {
  python_tools
  "$BIN/venv/bin/bandit" -q -r backend/app backend/scripts -ll
}

run_semgrep() {
  python_tools
  "$BIN/venv/bin/semgrep" scan --metrics=off --quiet --error --config p/python --config p/security-audit \
    --exclude 'backend/tests' backend/app backend/scripts
}

TOOLS=("$@"); [ ${#TOOLS[@]} -eq 0 ] && TOOLS=(gitleaks osv pip_audit trivy bandit semgrep)
FAILED=()
for t in "${TOOLS[@]}"; do
  echo "::group::$t"
  if "run_$t"; then echo "✔ $t"; else echo "✘ $t"; FAILED+=("$t"); fi
  echo "::endgroup::"
done
[ ${#FAILED[@]} -eq 0 ] || { echo "Sicherheitsprüfung fehlgeschlagen: ${FAILED[*]}" >&2; exit 1; }
echo "Sicherheitsprüfung bestanden."
