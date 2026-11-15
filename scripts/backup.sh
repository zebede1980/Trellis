#!/usr/bin/env bash
# Nightly SQLite backup for Trellis. Uses SQLite's online backup API (via Python, so no sqlite3 binary is needed),
# which is safe while the app is running. Keeps 14 days.
#
# Install on the server (crontab -e):
#   15 3 * * * /home/ubuntu/DockerSource/trellis/scripts/backup.sh >> /home/ubuntu/DockerSource/trellis/backups/backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
stamp=$(date +%Y%m%d-%H%M%S)
docker exec trellis-web python -c "
import sqlite3
src = sqlite3.connect('/data/trellis.db')
dst = sqlite3.connect('/tmp/trellis-backup.db')
src.backup(dst)
dst.close(); src.close()
"
# data/ belongs to the container user, so copy out of the container rather than moving on the host
docker cp trellis-web:/tmp/trellis-backup.db "backups/trellis-$stamp.db"
docker exec trellis-web rm -f /tmp/trellis-backup.db
gzip "backups/trellis-$stamp.db"
find backups -name 'trellis-*.db.gz' -mtime +14 -delete
echo "$(date -Is) backup ok: backups/trellis-$stamp.db.gz"
