# 360 Tour Uploader for Google Street View

Upload equirectangular 360 photos from cameras such as RICOH THETA, Insta360, and GoPro MAX to Google Street View, with a browser-based editor for map layout, connections, heading alignment, and local walkthrough preview.

## Features

- Browser-based tour editor built on OpenStreetMap and Leaflet
- Drag and drop 360 JPG files with automatic GPS placement from EXIF/XMP
- Manual heading alignment with pano preview and EXIF reset
- In-editor walkthrough between linked nodes
- Overlay compare view for visually checking orientation between two nodes
- Export to `tour-config.json`, `tour-project.json`, `tour-viewer.html`, and `tour.csv`
- Google Street View Publish API uploader and heading patch utilities

## Repository Layout

```text
streetview-tour-uploader/
├── editor/
│   └── editor.html
├── example/
│   ├── tour.csv.example
│   └── tour-meta.json.example
├── uploader/
│   ├── find_place_id.py
│   ├── gen_tour_csv.py
│   ├── restore_exif.py
│   ├── restore_xmp.py
│   ├── retry_failed.py
│   └── upload_tour.py
├── LICENSE
├── README.md
└── requirements.txt
```

## Requirements

- Python 3.9+
- A Google account
- Street View Publish API enabled in Google Cloud Console
- OAuth desktop client credentials saved as `uploader/client_secrets.json`

## Installation

```bash
git clone https://github.com/takadakoji-jp/streetview-tour-uploader.git
cd streetview-tour-uploader
pip install -r requirements.txt
```

## Workflow

### 1. Prepare photos

Blur faces and license plates before upload. The Street View Publish API does not blur them automatically.

### 2. Design the tour

Open `editor/editor.html` in a browser.

- Drop your 360 JPG files onto the map
- Move markers if GPS is missing or needs correction
- Switch to Connect mode and link nodes
- Select a node to edit heading, compare with neighbors, and test the walkthrough
- Export when the tour looks correct

### 3. Generate the CSV manifest

```bash
python uploader/gen_tour_csv.py \
  --config path/to/tour-config.json \
  --folder path/to/photos \
  --out path/to/photos/tour.csv
```

To associate the upload with a Google Maps place, add a `tour-meta.json` file in the photo folder:

```json
{
  "place_id": "ChIJxxxxxxxxxxxxxxxx",
  "note": "Venue name"
}
```

### 4. Upload to Google Street View

```bash
python uploader/upload_tour.py \
  --folder path/to/photos \
  --manifest path/to/photos/tour.csv
```

Use `--dry-run` to validate first, or `--connect-only` to retry connections after Google finishes processing.

## Notes

- Uploaded photos are public under your Google account
- Google Maps updates can take minutes to days depending on processing state
- Do not commit `client_secrets.json` or `token.json`

## License

MIT
