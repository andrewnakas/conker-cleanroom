#!/usr/bin/env bash
# Build the clean ROM, gate on the taint scan, assemble the EmulatorJS site and push it to gh-pages.
#   games/conker/publish.sh [--no-push]
# Never publishes when the taint scan fails. The retail ROM, dirty trees and practice clips stay on D:.
set -euo pipefail
cd "$(dirname "$0")/../.."
W=D:/n64work/conker
RETAIL=$W/baserom.us.z64
CLEAN=$W/build/conker.z64
SITE=$W/site
EJS=$W/devsite            # holds data/ (EmulatorJS 4.2.3 runtime + mupen64plus_next cores)
mkdir -p $W/build

python -m games.conker.generate $RETAIL $CLEAN | tail -12
python -m games.conker.taint $RETAIL $CLEAN | head -3
python -m games.conker.taint $RETAIL $CLEAN > /dev/null || { echo "TAINT FAILED: not publishing"; exit 1; }

if [ ! -d $SITE/.git ]; then
  mkdir -p $SITE && git -C $SITE init -q -b gh-pages
  git -C $SITE remote add origin https://github.com/andrewnakas/conker-cleanroom.git
fi
[ -f $EJS/LICENSE ] || cp /d/n64work/bk/site/data/LICENSE.EmulatorJS $EJS/LICENSE
python ports/ejs/make_site.py $CLEAN $EJS $SITE
python ports/ejs/patch_core.py $CLEAN $EJS/data/cores $SITE/data/cores
cp $CLEAN $W/devsite/clean.z64
[ "${1:-}" = "--no-push" ] && { echo "site ready (not pushed): $SITE"; exit 0; }
cd $SITE
git update-ref -d HEAD 2>/dev/null || true   # single-commit history: each push carries a 64 MB ROM (disk budget)
git add -A 2>/dev/null
git -c user.name="andrewnakas" -c user.email="andrewnakas@users.noreply.github.com" commit -qm "site: $(date +%F\ %H:%M)" || true
git push -f -q origin gh-pages
git reflog expire --expire=now --all && git gc -q --prune=now
echo "pushed gh-pages"
