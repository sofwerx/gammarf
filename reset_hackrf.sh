#!/bin/bash

out=`lsusb | grep -m 1 OpenMoko`
first=`echo $out | cut -d' ' -f2`
second=`echo $out | cut -d' ' -f4 | sed s/://`
cc 3rdparty/usbreset.c -o 3rdparty/usbreset
chmod +x 3rdparty/usbreset
3rdparty/usbreset /dev/bus/usb/$first/$second
