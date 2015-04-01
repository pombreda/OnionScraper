#! /bin/bash

# Remove chroot scripts from filesystem
rm ../filesystem/root/chroot-setup.sh
rm ../filesystem/root/chroot-taredown.sh

rm ../filesystem/root/.bash_history

# Unmount local dev
umount ../filesystem/dev/
umount ../filesystem/proc/
umount ../filesystem/sys/
