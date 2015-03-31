TARGETS = console-setup resolvconf alsa-utils mountkernfs.sh setserial ufw hostname.sh x11-common apparmor udev mountdevsubfs.sh udev-finish procps cryptdisks cryptdisks-early hwclock.sh checkroot.sh etc-setserial checkfs.sh urandom lvm2 networking bootmisc.sh mountall.sh mountnfs.sh checkroot-bootclean.sh mountnfs-bootclean.sh mountall-bootclean.sh kmod
INTERACTIVE = console-setup udev cryptdisks cryptdisks-early checkroot.sh checkfs.sh
udev: mountkernfs.sh
mountdevsubfs.sh: mountkernfs.sh udev
udev-finish: udev
procps: mountkernfs.sh udev
cryptdisks: checkroot.sh cryptdisks-early udev lvm2
cryptdisks-early: checkroot.sh udev
hwclock.sh: mountdevsubfs.sh
checkroot.sh: hwclock.sh mountdevsubfs.sh hostname.sh
etc-setserial: checkfs.sh
checkfs.sh: cryptdisks lvm2 checkroot.sh
urandom: hwclock.sh
lvm2: cryptdisks-early mountdevsubfs.sh udev
networking: resolvconf mountkernfs.sh urandom procps
bootmisc.sh: udev mountnfs-bootclean.sh mountall-bootclean.sh checkroot-bootclean.sh
mountall.sh: lvm2 checkfs.sh checkroot-bootclean.sh
mountnfs.sh: networking
checkroot-bootclean.sh: checkroot.sh
mountnfs-bootclean.sh: mountnfs.sh
mountall-bootclean.sh: mountall.sh
kmod: checkroot.sh
