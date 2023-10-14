#!/bin/bash

function fetch_main () {
    url="https://yaqwsx.github.io/jlcparts/data/cache.zip"
    rm -f "$url"
    wget "$url"
}
function fetch_part () {
    url="https://yaqwsx.github.io/jlcparts/data/cache.z0$i"
    rm -f "$url"
    wget "$url"
}

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR"

fetch_main &
for i in {1..7}; do
    fetch_part $i &
done

wait
7z x cache.zip
