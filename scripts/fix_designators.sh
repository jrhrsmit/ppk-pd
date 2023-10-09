#!/bin/bash

match="unlocked"
replace=""

files=$(find . -iname "*.kicad_pcb")

for f in $files; do
    #sed -i "s/ unlocked)/)/g" $f 
    sed -i "s/effects (font (size 0.7 0.7)/effects (font (size 0.6 0.6)/g" $f 
    sed -i "s/effects (font (size 1 1)/effects (font (size 0.6 0.6)/g" $f 
    sed -i "s/\(fp_text reference .*\)/\1 hide/" $f
    sed -i "s/hide hide/hide/" $f
    sed -i "s/\(fp_text reference \"TP.*\) hide/\1/" $f
    #sed -E -i "{N; s//\1right mirror/ ; D}" $f
    #perl -0777 -i -pe 's/(fp_text reference \"TP.*\n.*justify )mirror/$1right mirror\nBe/igs' $f
    sed -i "s/\(fp_text reference \"TP.*(at [\.0-9]\+ [\.0-9]\+\))/\1 90)/" $f
done

   # (fp_text reference "TP1002" (at 0 1.648) (layer "B.SilkS")
   #   (effects (font (size 0.6 0.6) (thickness 0.15)) (justify mirror))
   # 
   #   (fp_text reference "TP1002" (at 0 1.648 90) (layer "B.SilkS")
   #   (effects (font (size 0.6 0.6) (thickness 0.15)) (justify right mirror))
