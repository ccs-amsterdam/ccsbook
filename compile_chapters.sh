set -e
for CHAPTER in `seq -w 1 18`; do
    if ! [[ "$CHAPTER" =~ ^(05|16)$ ]]; then
	echo $CHAPTER
	pdflatex -jobname=chapters/chapter$CHAPTER "\includeonly{chapter$CHAPTER/chapter$CHAPTER}\input{main}"
	bibtex chapters/chapter$CHAPTER
	pdflatex -jobname=chapters/chapter$CHAPTER "\includeonly{chapter$CHAPTER/chapter$CHAPTER}\input{main}"
	pdflatex -jobname=chapters/chapter$CHAPTER "\includeonly{chapter$CHAPTER/chapter$CHAPTER}\input{main}"
fi
done
rm chapters/*.{aux,bbl,blg,idx,log,out}
