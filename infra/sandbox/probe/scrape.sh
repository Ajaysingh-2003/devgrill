#!/bin/sh
# dg-scrape job=host:port/path ... : scrape every target in parallel, print each body under a
# "### job" header (the driver splits on these). A target that fails prints an empty body.
set -u
tmp=$(mktemp -d)
for target in "$@"; do
  job=${target%%=*}
  url=${target#*=}
  ( curl -sS -m 2 "http://$url" > "$tmp/$job" 2>/dev/null || : > "$tmp/$job" ) &
done
wait
for target in "$@"; do
  job=${target%%=*}
  echo "### $job"
  cat "$tmp/$job"
done
rm -rf "$tmp"
