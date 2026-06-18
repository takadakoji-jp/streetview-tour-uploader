"""
Re-upload only the files that are missing from upload_result.json (i.e. failed),
merge the results, then re-run the connection step.

Usage:
  python retry_failed.py --folder <dir> --manifest <tour.csv>
"""

import argparse, json, os, sys, time, csv
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from upload_tour import (
    get_credentials, get_exif_gps,
    start_upload, push_bytes, create_photo,
    connect_photos_from_manifest, load_manifest, sync_photo_ids
)


def upload_photo(creds, path, lat, lng, alt, heading, place_id):
    """Upload a single photo and return its photoId, or None on failure."""
    try:
        session = requests.Session()
        session.headers.update({"Authorization": f"Bearer {creds.token}"})
        upload_url = start_upload(session)
        push_bytes(session, upload_url, path)
        return create_photo(session, upload_url, lat, lng, alt, heading, place_id)
    except Exception as e:
        print(f"    error: {e}")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder",   required=True, help="Folder containing the photos")
    ap.add_argument("--manifest", required=True, help="tour.csv path")
    args = ap.parse_args()

    folder = Path(args.folder)
    result_path = folder / "upload_result.json"

    with open(result_path, encoding="utf-8") as f:
        result = json.load(f)

    already = set(result.get("name_to_id", {}).keys())
    manifest_rows = load_manifest(Path(args.manifest))

    # Identify the failed ones
    failed = [r for r in manifest_rows if r["filename"].strip() not in already]
    print(f"To re-upload: {len(failed)} / already done: {len(already)}")

    if not failed:
        print("Nothing failed. Running --connect-only step only.")
    else:
        creds = get_credentials()
        session = requests.Session()
        session.headers.update({"Authorization": f"Bearer {creds.token}"})

        for i, row in enumerate(failed, 1):
            fname = row["filename"].strip()
            path = folder / fname
            lat = float(row["lat"]) if row.get("lat") else None
            lng = float(row["lng"]) if row.get("lng") else None
            heading = float(row["heading"]) if row.get("heading") else None

            if lat is None:
                lat, lng, _, heading2 = get_exif_gps(path)
                if heading is None: heading = heading2

            print(f"[{i}/{len(failed)}] {fname}")
            photo_id = upload_photo(creds, path, lat, lng, None, heading,
                                    result.get("place_id"))
            if photo_id:
                result["name_to_id"][fname] = photo_id
                result["photo_ids"] = list(result["name_to_id"].values())
                result["uploaded"] = len(result["name_to_id"])
                with open(result_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                print(f"  OK: {photo_id}")
            time.sleep(1)

    # Re-run connections
    print("\nRe-running connections...")
    creds = get_credentials()
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {creds.token}"})
    name_to_id = sync_photo_ids(session, result["name_to_id"])
    connect_photos_from_manifest(creds, name_to_id, manifest_rows)
    print("Done")


if __name__ == "__main__":
    main()
