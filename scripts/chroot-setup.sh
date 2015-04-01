#! /bin/bash

# Mount non-standard files
#mount -t proc none /proc
#mount -t sysfs none /sys
# Devpts causes umount bug in chroot
#mount -t devpts none /dev/pts

# exports for GPG keys
export HOME=/root
export LC_ALL=C

# Considerations for apt-get while in chroot
dbus-uuidgen > /var/lib/dbus/machine-id
dpkg-divert --local --rename --add /sbin/initctl
ln -s /bin/true /sbin/initctl
