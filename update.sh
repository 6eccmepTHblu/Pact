#!/bin/bash
# Обновление на сервере: /srv/pact/update.sh
# Тело в функции: git pull переписывает этот же файл, а bash дочитывает скрипт по ходу.
main() {
  set -euo pipefail
  cd "$(dirname "$0")"
  local start=$SECONDS
  git pull --ff-only
  docker compose up -d --build
  docker image prune -f >/dev/null

  local port
  port=$(grep -E '^APP_PORT=' .env | cut -d= -f2)
  for _ in $(seq 30); do
    if curl -fsS "http://127.0.0.1:${port:-8200}/api/health" >/dev/null 2>&1; then
      echo "OK за $((SECONDS - start)) с"
      return 0
    fi
    sleep 1
  done
  echo "Пакт не отвечает на /api/health" >&2
  docker compose logs --tail 30 app >&2
  return 1
}
main "$@"
