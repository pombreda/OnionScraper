#! /bin/bash

# Script to automatically produce a LiveCD ISO from a filesystem
chmod a+w ../extract-cd/casper/filesystem.manifest
chroot ../filesystem dpkg-query -W --showformat='${Package} ${Version}\n' > ../extract-cd/casper/filesystem.manifest
cp ../extract-cd/casper/filesystem.manifest ../extract-cd/casper/filesystem.manifest-desktop
sed -i '/ubiquity/d' ../extract-cd/casper/filesystem.manifest-desktop
sed -i '/casper/d' ../extract-cd/casper/filesystem.manifest-desktop

rm ../extract-cd/casper/filesystem.squashfs
mksquashfs ../filesystem ../extract-cd/casper/filesystem.squashfs 

printf $(du -sx --block-size=1 ../filesystem | cut -f1) > ../extract-cd/casper/filesystem.size

cd ../extract-cd/
rm ./md5sum.txt
find -type f -print0 | xargs -0 md5sum | grep -v isolinux/boot.cat | tee ./md5sum.txt

mkisofs -D -r -V "$IMAGE_NAME" -cache-inodes -J -l -b isolinux/isolinux.bin -c isolinux/boot.cat -no-emul-boot -boot-load-size 4 -boot-info-table -o ../onion_scraper-9.04.1-desktop.iso .

cd ../scripts/
