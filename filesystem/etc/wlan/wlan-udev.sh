#! /bin/bash


# script to start prism2 wlan for fedora FC5 udev 
#udev rule
#ACTION=="add",BUS=="usb",DRIVER=="prism2_usb",RUN+="/etc/wlan/wlan-udev.sh %k"

# 01-01-2007 (rsk) add check for wlan_wext_write
# 31-01-2007 (rsk) get the check right this time :)

# ifupdown udev rules or network-manager take care of configuration,
# only enable the card here (which also loads RAM firmware)

WEXT_PARAM=/sys/module/p80211/parameters/wlan_wext_write

DEVICE=$1
WLAN_UDEV=1

. /etc/wlan/shared

if [ -f $WEXT_PARAM ]; then
    WLAN_WEXT=`cat $WEXT_PARAM`
fi

wlan_enable $DEVICE

if [ $WLAN_WEXT = 1 ]; then
	# set encrypt on card not host
	result=`$WLANCTL $DEVICE lnxreq_hostwep decrypt="false" encrypt="false"`
	if [ $? != 0 ]; then
	    echo "Cannot enable wep $result"
	    exit 1
	fi
fi
exit 0


