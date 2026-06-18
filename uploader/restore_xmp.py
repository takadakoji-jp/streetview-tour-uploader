"""
Restore the XMP segment (e.g. GPano:ProjectionType=equirectangular) that an image
editor like GIMP strips out on save, by copying it back from the original photos.
Without this metadata Google rejects the upload as "not a 360 photo".

Usage:
  python restore_xmp.py --src <original_folder> --dst <edited_folder>
"""

import argparse
import os
import struct

XMP_NS = b'http://ns.adobe.com/xap/1.0/\x00'


def find_xmp_segment(data):
    i = 2
    while i < len(data) - 4:
        if data[i] != 0xFF:
            break
        marker = data[i + 1]
        if marker == 0xDA:
            break
        seg_len = struct.unpack('>H', data[i + 2:i + 4])[0]
        if marker == 0xE1:
            seg_content = data[i + 4:i + 2 + seg_len]
            if seg_content.startswith(XMP_NS):
                return data[i:i + 2 + seg_len]
        i += 2 + seg_len
    return None


def inject_xmp(jpeg_bytes, xmp_segment):
    """Insert the XMP segment right after SOI (removing any existing XMP)."""
    result = bytearray(jpeg_bytes[:2])  # SOI
    result.extend(xmp_segment)

    i = 2
    while i < len(jpeg_bytes):
        if jpeg_bytes[i] != 0xFF:
            result.extend(jpeg_bytes[i:])
            break
        marker = jpeg_bytes[i + 1]
        if marker == 0xDA:  # copy everything from SOS onward as-is
            result.extend(jpeg_bytes[i:])
            break
        if i + 4 > len(jpeg_bytes):
            result.extend(jpeg_bytes[i:])
            break
        seg_len = struct.unpack('>H', jpeg_bytes[i + 2:i + 4])[0]
        seg_end = i + 2 + seg_len
        if marker == 0xE1:
            seg_content = jpeg_bytes[i + 4:seg_end]
            if seg_content.startswith(XMP_NS):
                i = seg_end  # skip the old XMP
                continue
        result.extend(jpeg_bytes[i:seg_end])
        i = seg_end

    return bytes(result)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="Original photos folder (XMP intact)")
    ap.add_argument("--dst", required=True, help="Edited photos folder (XMP restore target)")
    args = ap.parse_args()

    jpgs = sorted(f for f in os.listdir(args.dst) if f.upper().endswith(".JPG"))
    print(f"Target: {len(jpgs)} photos")

    ok = skip = err = 0
    for fname in jpgs:
        src_path = os.path.join(args.src, fname)
        dst_path = os.path.join(args.dst, fname)

        if not os.path.exists(src_path):
            print(f"  skip (no original): {fname}")
            skip += 1
            continue

        try:
            with open(src_path, 'rb') as f:
                src_data = f.read()
            xmp = find_xmp_segment(src_data)
            if not xmp:
                print(f"  no XMP in original: {fname}")
                skip += 1
                continue

            with open(dst_path, 'rb') as f:
                dst_data = f.read()
            new_data = inject_xmp(dst_data, xmp)
            with open(dst_path, 'wb') as f:
                f.write(new_data)
            print(f"  OK: {fname}")
            ok += 1
        except Exception as e:
            print(f"  ERR: {fname}: {e}")
            err += 1

    print(f"\nDone: {ok} restored / {skip} skipped / {err} errors")


if __name__ == "__main__":
    main()
