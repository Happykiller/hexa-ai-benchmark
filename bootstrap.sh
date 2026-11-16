#!/usr/bin/env bash
# Bootstrap de la distro KoA hexa-ai-benchmark.
# Rejouable : KoA le relance à chaque reprovisionnement. Ne journalise jamais la valeur d'un secret.
# Le socle dev fournit déjà Python 3 (venv, pip), Node 24, gh et Docker sans root : rien de cela ici.
set -euo pipefail

SEED_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$HOME/bootstrap.log"
: > "$LOG"
log() { echo "bootstrap : $*" | tee -a "$LOG"; }

[ -f "$HOME/.agent-env" ] && source "$HOME/.agent-env"
log "distro=${WSL_DISTRO_NAME:-?} utilisateur=$(whoami) seed=$SEED_DIR"

# --- 1. Accès GitHub par la deploy key (secret ssh « cle_github ») ----------------------------
KEY="$HOME/.ssh/cle_github"
GITHUB_REPO_SSH="git@github.com:Happykiller/hexa-ai-benchmark.git"
mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
if [ -f "$KEY" ]; then
  chmod 600 "$KEY"
  touch "$HOME/.ssh/config" && chmod 600 "$HOME/.ssh/config"
  sed -i '/^# >>> koa hexa-ai-benchmark/,/^# <<< koa hexa-ai-benchmark/d' "$HOME/.ssh/config"
  cat >> "$HOME/.ssh/config" <<EOF
# >>> koa hexa-ai-benchmark
Host github.com
  HostName github.com
  User git
  IdentityFile $KEY
  IdentitiesOnly yes
# <<< koa hexa-ai-benchmark
EOF
  # Empreinte publiée par GitHub (docs « GitHub's SSH key fingerprints »), épinglée plutôt que scannée.
  GH_HOSTKEY="github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"
  touch "$HOME/.ssh/known_hosts"
  grep -qxF "$GH_HOSTKEY" "$HOME/.ssh/known_hosts" || echo "$GH_HOSTKEY" >> "$HOME/.ssh/known_hosts"
  # On ne touche qu'à l'URL de push : la récupération reste celle avec laquelle KoA a cloné.
  git -C "$SEED_DIR" remote set-url --push origin "$GITHUB_REPO_SSH"
  log "git : push par la deploy key ($GITHUB_REPO_SSH)"
else
  log "git : clé cle_github absente, l'agent ne pourra pas pousser"
fi

# --- 2. Blender 4.5 LTS (hors PATH, comme sur la machine de référence) -------------------------
# L'auditeur le trouve par ~/.local/bin/blender45 (hexa/benches/blender/auditor/runner.py).
BLENDER_VERSION="4.5.11"
BLENDER_SHA256="05ed7bd41bf3e61ae4f4a7cdc364c43088bf8b3fed702c2269c018fdf63a2188"
BLENDER_DIR="$HOME/.local/opt/blender-$BLENDER_VERSION"
BLENDER_URL="https://download.blender.org/release/Blender4.5/blender-$BLENDER_VERSION-linux-x64.tar.xz"
if [ ! -x "$BLENDER_DIR/blender" ]; then
  log "blender : téléchargement de $BLENDER_VERSION"
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  curl -fsSL -o "$tmp/blender.tar.xz" "$BLENDER_URL"
  echo "$BLENDER_SHA256  $tmp/blender.tar.xz" | sha256sum -c --quiet -
  tar -xJf "$tmp/blender.tar.xz" -C "$tmp"
  mkdir -p "$HOME/.local/opt"
  rm -rf "$BLENDER_DIR"
  mv "$tmp/blender-$BLENDER_VERSION-linux-x64" "$BLENDER_DIR"
  rm -rf "$tmp"
  trap - EXIT
fi
mkdir -p "$HOME/.local/bin"
ln -sfn "$BLENDER_DIR/blender" "$HOME/.local/bin/blender45"
blender_version="$("$HOME/.local/bin/blender45" --version 2>/dev/null | head -1)"
[ -n "$blender_version" ] || { log "blender : ne démarre pas (bibliothèque manquante ?)"; exit 1; }
log "blender : $blender_version"

# --- 3. Venv Python de l'auditeur ---------------------------------------------------------------
# PyYAML 6.0 (épinglé) n'a pas de wheel au-delà de Python 3.11 : son sdist ne se construit
# qu'avec Cython < 3. La contrainte ne touche que le build, requirements.txt reste la référence.
cd "$SEED_DIR"
[ -x venv/bin/python ] || python3 -m venv venv
constraint="$(mktemp)"
echo "cython<3" > "$constraint"
PIP_CONSTRAINT="$constraint" venv/bin/pip install -q --disable-pip-version-check -r requirements.txt
rm -f "$constraint"
venv/bin/python -m hexa --help >/dev/null
log "python : $(venv/bin/python --version), auditeur importable"

# --- 4. Frontend de la KB -----------------------------------------------------------------------
npm ci --no-audit --no-fund --loglevel=error
log "node : $(node --version), dépendances web installées"

# --- 5. Docker : l'audit Todo passe par docker compose (même en --skip-dynamic) -----------------
docker compose version >/dev/null || { log "docker compose introuvable : audit Todo impossible"; exit 1; }
log "docker : $(docker compose version --short 2>/dev/null)"

# --- 6. Plugins Claude Code hors koa-skills (marketplaces Happykiller) -------------------------
# Le champ « plugins » du profil ne couvre que koa-skills : les autres marketplaces s'installent ici.
# Rejouable : marketplace add et install ne font rien de plus si l'élément est déjà là.
for spec in "Happykiller/claude-cockpit:claude-cockpit:cockpit" "Happykiller/claude-chat-roles:claude-chat-roles:chat-roles"; do
  repo="${spec%%:*}"; rest="${spec#*:}"; market="${rest%%:*}"; plugin="${rest#*:}"
  claude plugin marketplace list 2>/dev/null | grep -q "$market" || claude plugin marketplace add "$repo" >/dev/null
  claude plugin list 2>/dev/null | grep -q "$plugin@$market" || claude plugin install "$plugin@$market" >/dev/null
  log "plugin : $plugin@$market"
done

# --- 7. Arborescence des données locales (gitignorée) -------------------------------------------
mkdir -p runs/todo/livrables runs/todo/cr_audits runs/blender/livrables runs/blender/cr_audits
log "terminé"
