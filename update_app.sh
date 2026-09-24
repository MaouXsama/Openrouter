#!/usr/bin/env bash
set -Eeuo pipefail

dockerhub_namespace="${1:?Docker Hub namespace is required}"
image_tag="${2:?Image tag is required}"
app_dir="${APP_DIR:-/home/azureuser/Openrouter}"

[[ "$dockerhub_namespace" =~ ^[a-z0-9][a-z0-9_-]*$ ]]
[[ "$image_tag" =~ ^[A-Za-z0-9._-]+$ ]]

cd "$app_dir"

if [[ "$(id -u)" -eq 0 ]]; then
  runuser -u azureuser -- git -C "$app_dir" pull --ff-only origin main
else
  git pull --ff-only origin main
fi

previous_tag="$(sed -n 's/^IMAGE_TAG=//p' .env | tail -n 1)"
previous_tag="${previous_tag:-latest}"

set_env_value() {
  local key="$1"
  local value="$2"

  if grep -q "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}

if docker info >/dev/null 2>&1; then
  compose=(docker compose)
else
  compose=(sudo docker compose)
fi

rollback() {
  local exit_code=$?
  trap - ERR
  set_env_value IMAGE_TAG "$previous_tag"
  "${compose[@]}" up -d --no-build backend chatbot || true
  exit "$exit_code"
}

trap rollback ERR

set_env_value DOCKERHUB_NAMESPACE "$dockerhub_namespace"
set_env_value IMAGE_TAG "$image_tag"

"${compose[@]}" pull backend chatbot
"${compose[@]}" up -d --no-build backend chatbot

backend_ready=false
for _ in {1..30}; do
  if curl -fsS http://localhost:5000/load_chat/ >/dev/null; then
    backend_ready=true
    break
  fi
  sleep 2
done
"$backend_ready"

frontend_ready=false
for _ in {1..30}; do
  if curl -fsS http://localhost:8501/_stcore/health >/dev/null; then
    frontend_ready=true
    break
  fi
  sleep 2
done
"$frontend_ready"

trap - ERR
echo "Deployment completed for image tag $image_tag"
