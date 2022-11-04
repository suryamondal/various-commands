# Various useful tricks and commands in linux

### stopping computer to go into sleep mode:
```
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

https://hushup.app/rmaji

Specials:
```
find . -type f | grep root | grep sim01 | xargs -I {} mv {} .
```
```
rsync -au --progress suryanarayan@158.144.55.146:/home/suryanarayan/Documents/Gobinda .

rsync -au suryanarayan@sim01.ino.tifr.res.in:/home/suryanarayan/Documents/Gobinda/IICHEP/RPCStackSim20180516_rpcDaq/temp/*root /media/surya/Surya_1/DaqMadurai/maduraiCorsikaData/20170804/geantOutput/

rsync -au src/* suryanarayan@sim01.ino.tifr.res.in:/home/suryanarayan/Documents/Gobinda/IICHEP/RPCStackSim20180516_rpcDaq/src/
rsync -au include/* suryanarayan@sim01.ino.tifr.res.in:/home/suryanarayan/Documents/Gobinda/IICHEP/RPCStackSim20180516_rpcDaq/include/
```

### copy from ftp:
```
wget -c --user=android --ask-password ftp://192.168.1.135:2221/Camera/IMG_20190824*
```

### git: lost and found
```
git fsck --cache --no-reflogs --lost-found --dangling HEAD
```

### Compress PDF Document: Two ways
```
gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 -dPDFSETTINGS=/ebook -dNOPAUSE -dBATCH -dQUIET -sOutputFile=output.pdf input.pdf
```
**/screen /ebook /printer /prepress /default**

Otherwise, use this custom made [script](https://github.com/suryamondal/various_commands/blob/main/various_linux_commands/compresspdf.sh) by me.

### convert: PDF to JPEG
```
convert -verbose -density 300 -trim test.pdf -quality 100 test.jpg
```

### Join two consecutive A5 pages into A4. (All are in potrait mode.)
pdf2ps -dLanguageLevel=3 A5.pdf - | psnup -2 -Pa5 -pa4 | ps2pdf -dCompatibility=1.4 - A4.pdf

### For time lapse:
```
ffmpeg -f image2 -r 30 -i %*.JPG -s hd720 -vcodec libx264 ../out.mp4
```
```
ls -1 | awk '{print "file '\''"$1"'\''"}' > test.txt
ffmpeg -f image2 -r 5 -f concat -i test.txt -c:v libx264 -r 30 ../../Videos/20200517_test.mp4
```
For joining audio:
```
ffmpeg -i XX.mp4 -i XX.mp3 -shortest XX.mp4
```
For Rescaling Video:
```
ffmpeg -i out0.mp4 -vf scale=640:360 out00.mp4
```
For Cutting Video:
```
ffmpeg -ss [start] -i in.mp4 -t [duration] -c copy out.mp4
```
For Joining Video:
```
ffmpeg -f concat -i inputs.txt -vcodec copy hd320 -acodec copy out.mp4
MP4Box -add file1.mp4 -add file2.mp4 output.mp4
```
To create a GIF:
```
ffmpeg -i yesbuddy.mov -pix_fmt rgb24 -s 512x288 output.gif
```
To reverse video:
```
ffmpeg -i input.mp4 -vf reverse reversed.mp4
```

Insert at the end of the line:
```
sed -i -e 's/$/\t1000000/' XXX.log
sed -i -e 's/^/#/' XXX.log
```

Copy files from all subdirectories:
```
find . -type f -print0 | xargs -0 mv -t ../../20170804/output/geantOut/
```

### Replace whitespace with newline
```
cat example | xargs -n 1
```

Finding Missing File:

PDFTK:
```
pdftk full-pdf.pdf cat 12-15 output outfile_p12-15.pdf
```

https://pacoup.com/2011/06/12/list-of-true-169-resolutions/
