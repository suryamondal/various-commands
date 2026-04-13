#!/bin/bash

# Run from the script's own directory regardless of where it is called from
cd "$(dirname "$0")"

TEX=main
OUT=git-presentation.pdf

mkdir -p tmp

echo "==> Pass 1 ..."
pdflatex -output-directory=tmp -interaction=nonstopmode "$TEX.tex"

echo "==> Pass 2 (resolving references) ..."
pdflatex -output-directory=tmp -interaction=nonstopmode "$TEX.tex"

if [ -f "tmp/$TEX.pdf" ]; then
    cp "tmp/$TEX.pdf" "$OUT"
    echo ""
    echo "Done: $(pwd)/$OUT"
else
    echo ""
    echo "ERROR: PDF not produced. Check tmp/$TEX.log for details."
    exit 1
fi
