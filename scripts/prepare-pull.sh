#! /bin/bash

# Decompress file over 100M
FILE=../filesystem/usr/share/icons/HighContrast/icon-theme.cache.xz
if [ -f $FILE ]; then
	xz -d $FILE
fi
