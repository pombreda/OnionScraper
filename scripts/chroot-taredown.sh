#! /bin/bash

# Clean filesystem
apt-get autoclean
rm -rf /tmp/* ~/.bash_history

# Considerations for apt-get in chroot
rm /sbin/initctl
dpkg-divert --rename --remove /sbin/initctl

# Taredown filesystem
cd
umount /proc || umount -lf /proc
umount /sys
#umount /dev/pts

