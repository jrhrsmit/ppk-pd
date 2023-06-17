#!/bin/bash

wget https://yaqwsx.github.io/jlcparts/data/cache.zip
for i in {1..7}; do
	wget "https://yaqwsx.github.io/jlcparts/data/cache.z0$i"
done
7z x cache.zip
