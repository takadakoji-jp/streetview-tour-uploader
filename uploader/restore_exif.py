"""
Restore GPS EXIF that was stripped by an image editor (e.g. GIMP) by copying it
back from the original photos.

Usage:
  python restore_exif.py --src <original_folder> --dst <edited_folder>
"""

import argparse
import os
import piexif


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="Original photos folder (EXIF intact)")
    ap.add_argument("--dst", required=True, help="Edited photos folder (EXIF restore target)")
    args = ap.parse_args()

    jpgs = sorted(f for f in os.listdir(args.dst) if f.upper().endswith(".JPG"))
    print(f"Target: {len(jpgs)} photos")

    ok = err = 0
    for fname in jpgs:
        src_path = os.path.join(args.src, fname)
        dst_path = os.path.join(args.dst, fname)

        if not os.path.exists(src_path):
            print(f"  skip (no original): {fname}")
            continue

        try:
            exif_dict = piexif.load(src_path)
            exif_bytes = piexif.dump(exif_dict)
            piexif.insert(exif_bytes, dst_path)
            print(f"  OK: {fname}")
            ok += 1
        except Exception as e:
            print(f"  ERR: {fname}: {e}")
            err += 1

    print(f"\nDone: {ok} restored / {err} errors")


if __name__ == "__main__":
    main()
