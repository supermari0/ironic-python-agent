#!/bin/bash

set -e

log() {
  echo "`basename $0`: $@"
}

usage() {
  [[ -z "$1" ]] || echo -e "USAGE ERROR: $@\n"
  echo "`basename $0`: CONFIGDRIVE DEVICE"
  echo "  - This script injects CONFIGDRIVE contents as an iso9660"
  echo "    filesystem on a partition at the end of DEVICE."
  exit 1
}

CONFIGDRIVE="$1"
DEVICE="$2"

[[ -f $CONFIGDRIVE ]] || usage "$CONFIGDRIVE (CONFIGDRIVE) is not a regular file"
[[ -b $DEVICE ]] || usage "$DEVICE (DEVICE) is not a block device"

# Create small partition at the end of the device
log "Adding configdrive partition to $DEVICE"
parted -a optimal -s -- $DEVICE mkpart primary ext2 -64MiB -0

# Find partition we just created
# Dump all partitions, ignore empty ones, then get the last partition ID
ISO_PARTITION=`sfdisk --dump $DEVICE | grep -v ' 0,' | tail -n1 | awk '{print $1}'`

# This generates the ISO image of the config drive.
log "Writing Configdrive contents in $CONFIGDRIVE to $ISO_PARTITION"
dd if=$CONFIGDRIVE of=$ISO_PARTITION bs=64K oflag=direct

log "${DEVICE} imaged successfully!"
