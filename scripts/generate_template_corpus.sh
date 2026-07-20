#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE_ROOT="$PROJECT_ROOT/corpus/template"
mkdir -p "$TEMPLATE_ROOT"

finish_template() {
  local directory="$1"
  if [[ ! -d "$directory" ]]; then
    echo "generator failed to create: $directory" >&2
    return 1
  fi
  rm -rf "$directory/.git" "$directory/node_modules"
  git -C "$directory" init --quiet
  git -C "$directory" add .
  git -C "$directory" \
    -c user.name="GitZero Fixture Builder" \
    -c user.email="fixtures@gitzero.local" \
    commit --quiet -m "Initial generated scaffold"
  echo "created template: ${directory#"$TEMPLATE_ROOT/"}"
}

generate() {
  local name="$1"
  shift
  local directory="$TEMPLATE_ROOT/$name"
  if [[ -e "$directory" ]]; then
    echo "kept existing template: $name"
    return
  fi
  "$@" "$directory"
  finish_template "$directory"
}

astro_minimal() {
  npx --yes create-astro@latest "$1" --template minimal --no-install --no-git --yes
}

astro_blog() {
  npx --yes create-astro@latest "$1" --template blog --no-install --no-git --yes
}

nuxt_default() {
  CI=1 npx --yes nuxi@latest init "$1" --template minimal --no-install \
    --gitInit=false --packageManager=npm
}

svelte_minimal_ts() {
  npx --yes sv@latest create "$1" --template minimal --types ts --no-add-ons --no-install
}

svelte_demo_js() {
  npx --yes sv@latest create "$1" --template demo --types jsdoc --no-add-ons --no-install
}

svelte_library_ts() {
  npx --yes sv@latest create "$1" --template library --types ts --no-add-ons --no-install
}

react_router_default() {
  npx --yes create-react-router@latest "$1" --no-install --no-git-init --no-agent-skills --yes
}

vue_default() {
  (cd "$TEMPLATE_ROOT" && npm create vue@latest "$(basename "$1")" -- --default)
}

vue_ts_router() {
  (
    cd "$TEMPLATE_ROOT"
    npm create vue@latest "$(basename "$1")" -- \
      --ts --router --pinia --vitest --eslint --prettier
  )
}

hono_node() {
  (
    cd "$TEMPLATE_ROOT"
    printf 'n\n' | npx --yes create-hono@latest "$(basename "$1")" --template nodejs
  )
}

hono_cloudflare() {
  (
    cd "$TEMPLATE_ROOT"
    printf 'n\n' | npx --yes create-hono@latest "$(basename "$1")" \
      --template cloudflare-workers
  )
}

docusaurus_classic_ts() {
  npx --yes create-docusaurus@latest "$1" classic --typescript --skip-install --git-strategy copy
}

fastify_js() {
  npx --yes fastify-cli@latest generate "$1" --esm
}

fastify_ts() {
  npx --yes fastify-cli@latest generate "$1" --lang=ts
}

django_default() {
  local directory="$1"
  local tools_dir
  tools_dir="$(mktemp -d /tmp/gitzero-django-tools.XXXXXX)"
  python3 -m pip install --quiet --target "$tools_dir" "Django>=5,<6"
  mkdir -p "$directory"
  PYTHONPATH="$tools_dir" python3 -m django startproject config "$directory"
  rm -rf "$tools_dir"
}

swift_executable() {
  mkdir -p "$1"
  (cd "$1" && swift package init --type executable --name starter)
}

swift_library() {
  mkdir -p "$1"
  (cd "$1" && swift package init --type library --name starter)
}

generate "astro-minimal" astro_minimal
generate "astro-blog" astro_blog
generate "nuxt-default" nuxt_default
generate "sveltekit-minimal-ts" svelte_minimal_ts
generate "sveltekit-demo-js" svelte_demo_js
generate "sveltekit-library-ts" svelte_library_ts
generate "react-router-default" react_router_default
generate "create-vue-default" vue_default
generate "create-vue-ts-router" vue_ts_router
generate "hono-node" hono_node
generate "hono-cloudflare-worker" hono_cloudflare
generate "docusaurus-classic-ts" docusaurus_classic_ts
generate "fastify-default-js" fastify_js
generate "fastify-default-ts" fastify_ts
generate "python-django-default" django_default
generate "swift-executable-starter" swift_executable
generate "swift-library-starter" swift_library

echo "Template corpus now contains $(find "$TEMPLATE_ROOT" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ') repos."
