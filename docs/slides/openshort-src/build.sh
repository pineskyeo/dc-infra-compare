#!/usr/bin/env bash
# charts.py → deck.js → pptx → 슬라이드별 jpg
# 필요: python3(matplotlib, numpy), node + pptxgenjs, soffice(LibreOffice), pdftoppm(poppler)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SLIDES="$(cd "$HERE/.." && pwd)"
NAME=dc-openshort-log

SOFFICE="$(command -v soffice || echo /Applications/LibreOffice.app/Contents/MacOS/soffice)"

python3 "$HERE/charts.py" > /dev/null
NODE_PATH="$HERE/node_modules:$(npm root -g)" node "$HERE/deck.js"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
"$SOFFICE" --headless --convert-to pdf --outdir "$TMP" "$SLIDES/$NAME.pptx" > /dev/null
pdftoppm -jpeg -r 110 "$TMP/$NAME.pdf" "$TMP/p"
rm -f "$SLIDES/$NAME"-slide-*.jpg
i=0
for f in $(ls "$TMP"/p-*.jpg | sort -V); do
  i=$((i + 1))
  cp "$f" "$SLIDES/$(printf '%s-slide-%02d.jpg' "$NAME" "$i")"
done
echo "jpg $i 장 → $SLIDES/$NAME-slide-NN.jpg"
