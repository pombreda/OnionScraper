#! /bin/bash

# Compress file over 100M
FILE=../filesystem/usr/share/icons/HighContrast/icon-theme.cache
if [ -f $FILE ]; then
	xz -z $FILE
fi
