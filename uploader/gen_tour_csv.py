"""
Generate tour.csv from a tour-config.json (connections) + EXIF GPS in the photos.

Usage:
  python gen_tour_csv.py --config <tour-config.json> --folder <photos_dir> --out <output.csv>
"""

import argparse, json, os, csv
import piexif

def dms_to_decimal(dms, ref):
    d = dms[0][0] / dms[0][1]
    m = dms[1][0] / dms[1][1]
    s = dms[2][0] / dms[2][1]
    val = d + m / 60 + s / 3600
    if ref in [b'S', b'W', 'S', 'W']:
        val = -val
    return val

def read_exif_gps(filepath):
    try:
        exif = piexif.load(filepath)
        gps = exif.get("GPS", {})
        if not gps:
            return None, None, None
        lat = dms_to_decimal(gps[piexif.GPSIFD.GPSLatitude], gps[piexif.GPSIFD.GPSLatitudeRef])
        lng = dms_to_decimal(gps[piexif.GPSIFD.GPSLongitude], gps[piexif.GPSIFD.GPSLongitudeRef])
        heading = None
        if piexif.GPSIFD.GPSImgDirection in gps:
            n, d = gps[piexif.GPSIFD.GPSImgDirection]
            heading = round(n / d, 2) if d else None
        return round(lat, 7), round(lng, 7), heading
    except Exception as e:
        print(f"  EXIF read failed {os.path.basename(filepath)}: {e}")
        return None, None, None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="tour-config.json exported by the editor")
    ap.add_argument("--folder", required=True, help="Folder containing the 360 photos")
    ap.add_argument("--out", default=None, help="Output CSV path (defaults to <folder>/tour.csv)")
    args = ap.parse_args()

    out_path = args.out or os.path.join(args.folder, "tour.csv")

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)

    nodes = cfg["nodes"]

    # nodeId -> panorama filename
    id_to_file = {n["id"]: n["panorama"] for n in nodes}

    rows = []
    for node in nodes:
        filename = node["panorama"]
        filepath = os.path.join(args.folder, filename)

        lat, lng, heading = read_exif_gps(filepath)

        connects = [id_to_file[lnk["nodeId"]] for lnk in node.get("links", [])]
        connects_to = ";".join(connects)

        rows.append({
            "filename": filename,
            "lat": lat if lat is not None else "",
            "lng": lng if lng is not None else "",
            "heading": heading if heading is not None else "",
            "connects_to": connects_to,
            "memo": "",
        })

        gps_str = f"({lat}, {lng})" if lat is not None else "no GPS"
        print(f"  {filename}: {gps_str}  heading={heading}  connections={len(connects)}")

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["filename","lat","lng","heading","connects_to","memo"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDone: {len(rows)} rows -> {out_path}")
    print("Note: photos without GPS have empty lat/lng. Fill them in manually.")

if __name__ == "__main__":
    main()
