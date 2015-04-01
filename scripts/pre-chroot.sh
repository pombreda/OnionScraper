#! /bin/bash

#Allows for Internet in chroot
cp /etc/resolv.conf ../filesystem/etc/

#Mount /dev
mount --bind /dev/ ../filesystem/dev

#Symlink chroot scripts
ln -s ./chroot-setup.sh ../filesystem/root/chroot-setup.sh
ln -s ./chroot-taredown.sh ../filesystem/root/chroot-taredown.sh
