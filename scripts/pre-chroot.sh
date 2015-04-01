#! /bin/bash

#Allows for Internet in chroot
cp /etc/resolv.conf ../filesystem/etc/

#Mount /dev
mount --bind /dev/ ../filesystem/dev
mount --bind /proc/ ../filesystem/proc
mount --bind /sys/ ../filesystem/sys

#Symlink chroot scripts
ln ./chroot-setup.sh ../filesystem/root/chroot-setup.sh
ln ./chroot-taredown.sh ../filesystem/root/chroot-taredown.sh
