#!/usr/bin/env python3
"""
Look up a Google Place ID from a place name.
Requires the GOOGLE_MAPS_API_KEY environment variable.

Usage:
  python find_place_id.py "Place name"
  python find_place_id.py "Central Park"
"""

import sys
import os
import requests

API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY')

if not API_KEY:
    print("GOOGLE_MAPS_API_KEY is not set.")
    print("  export GOOGLE_MAPS_API_KEY=your_key")
    print("  (Windows) set GOOGLE_MAPS_API_KEY=your_key")
    sys.exit(1)


def find_place_id(query):
    url = 'https://maps.googleapis.com/maps/api/place/findplacefromtext/json'
    r = requests.get(url, params={
        'input': query,
        'inputtype': 'textquery',
        'fields': 'place_id,name,formatted_address,geometry',
        'key': API_KEY,
    })
    r.raise_for_status()
    data = r.json()

    candidates = data.get('candidates', [])
    if not candidates:
        print(f"No place matched '{query}'.")
        return

    for c in candidates:
        loc = c.get('geometry', {}).get('location', {})
        print(f"\n{c.get('name')}")
        print(f"  Address : {c.get('formatted_address', 'unknown')}")
        print(f"  Place ID: {c['place_id']}")
        print(f"  LatLng  : ({loc.get('lat')}, {loc.get('lng')})")
        print(f"\nUse it like this:")
        print(f"   python upload_tour.py --folder ./photos --place-id {c['place_id']}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python find_place_id.py "Place name"')
        sys.exit(1)
    find_place_id(' '.join(sys.argv[1:]))
