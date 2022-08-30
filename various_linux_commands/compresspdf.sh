#!/bin/bash

# This script compress pdf by converting each pages into jpeg.
# Arg 1: jpeg dpi
# Arg 2: fileName

# chmod +x compresspdf.sh
# usage: ./compresspdf.sh 150 test.pdf

filename=$2

number=`pdftk LayerCompare.pdf dump_data | grep NumberOfPages | sed 's/[^0-9]*//'`
echo 'number of pages: '$number

pages=''
pages1=''

# convert each pages to jpeg and then to pdf
for i in $(seq $number)
do
    printf -v j "%05d" $i

    exec='pdftk A='$filename' cat A'$j' output '$j'.pdf' 
    echo $exec
    echo $exec | sh
    
    exec='convert -verbose -density '$1' -trim '$j'.pdf -quality 100 '$j'.jpg'
    echo $exec
    echo $exec | sh

    exec='convert '$j'.jpg '$j'.pdf'
    echo $exec
    echo $exec | sh

    pages+=' '$j'.pdf'
    pages1+=' '$j'.jpg'
done

exec='pdftk '$pages' cat output output.pdf' 
echo $exec
echo $exec | sh

exec='rm -rf '$pages' '$pages1
echo $exec
echo $exec | sh
