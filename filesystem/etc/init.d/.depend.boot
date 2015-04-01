TARGETS = console-setup mountkernfs.sh alsa-utils resolvconf setserial ufw apparmor hostname.sh x11-common udev mountdevsubfs.sh procps udev-finish cryptdisks cryptdisks-early networking hwclock.sh checkroot.sh lvm2 etc-setserial checkfs.sh urandom mountall.sh checkroot-bootclean.sh bootmisc.sh mountnfs-bootclean.sh mountnfs.sh kmod mountall-bootclean.sh
INTERACTIVE = console-setup udev cryptdisks cryptdisks-early checkroot.sh checkfs.sh
udev: mountkernfs.sh
mountdevsubfs.sh: mountkernfs.sh udev
procps: mountkernfs.sh udev
udev-finish: udev
cryptdisks: checkroot.sh cryptdisks-early udev lvm2
cryptdisks-early: checkroot.sh udev
networking: resolvconf mountkernfs.sh urandom procps
hwclock.sh: mountdevsubfs.sh
checkroot.sh: hwclock.sh mountdevsubfs.sh hostname.sh
lvm2: cryptdisks-early mountdevsubfs.sh udev
etc-setserial: checkfs.sh
checkfs.sh: cryptdisks checkroot.sh lvm2
urandom: hwclock.sh
mountall.sh: checkfs.sh checkroot-bootclean.sh lvm2
checkroot-bootclean.sh: checkroot.sh
bootmisc.sh: udev mountnfs-bootclean.sh checkroot-bootclean.sh mountall-bootclean.sh
mountnfs-bootclean.sh: mountnfs.sh
mountnfs.sh: networking
kmod: checkroot.sh
mountall-bootclean.sh: mountall.sh
