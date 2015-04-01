#! /bin/bash

# Remove chroot scripts from filesystem
rm ../filesystem/root/chroot-setup.sh
rm ../filesystem/root/chroot-taredown.sh

# Unmount local dev
umount ../filesystem/dev/
