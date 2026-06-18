# 360° Tour Uploader for Google Street View

Upload 360° photos from any equirectangular camera (RICOH THETA, Insta360, GoPro MAX, etc.) to Google Street View — with a browser-based tour editor to arrange photos on a map and define walkthrough connections.

## Features

- 🗺️ **Browser-based tour editor** — drag & drop photos onto an OpenStreetMap, draw connections between them
- 📍 **Auto GPS placement** — reads EXIF GPS from photos and places them on the map automatically
- 📤 **Batch upload** — uploads all photos via Google Street View Publish API in one command
- 🔗 **Auto-connect** — sets up navigation arrows between photos to create a walkthrough tour
- 🏢 **Place linking** — associates the tour with a Google Maps place (Place ID)
- 🛠️ **EXIF/XMP restore utilities** — recover GPS and 360° metadata lost after editing in GIMP etc.

## Requirements

### Hardware
- Any 360° camera that outputs equirectangular JPEG (RICOH THETA, Insta360, GoPro MAX, Samsung Gear 360, etc.)

### Accounts & APIs
- Google account
- [Street View Publish API](https://developers.google.com/streetview/publish) enabled in Google Cloud Console
- OAuth 2.0 client ID (Desktop app type) → download as `client_secrets.json`

### Software
- Python 3.9+

## Installation

```bash
git clone https://github.com/takadakoji-jp/streetview-tour-uploader.git
cd streetview-tour-uploader
pip install -r requirements.txt
```

Place your `client_secrets.json` in the `uploader/` folder (excluded from Git via `.gitignore`).

## Workflow

### Step 1: Blur faces and license plates (important)

**Do this before uploading.** The Street View Publish API does NOT apply automatic blurring. Use GIMP, Photoshop, or any photo editor to manually blur any faces or license plates in your photos.

### Step 2: Build your tour in the browser editor

Open `editor/editor.html` in a browser and drop your 360° photos onto it.

- Photos with GPS EXIF are placed on the map automatically
- Drag markers to fine-tune positions
- Switch to **Connect mode** to draw links between photos
- Click **Export** (📦) → saves `tour-viewer.html` (local preview) + `tour-config.json`

### Step 3: Generate the CSV manifest

```bash
python uploader/gen_tour_csv.py \
  --config path/to/tour-config.json \
  --folder path/to/photos/ \
  --out    path/to/photos/tour.csv
```

To link the tour to a Google Maps place, add a `tour-meta.json` file in your photo folder:

```json
{
  "place_id": "ChIJxxxxxxxxxxxxxxxx",
  "note": "Venue name (memo)"
}
```

### Step 4: Upload

```bash
# Dry run (no upload)
python uploader/upload_tour.py \
  --folder   path/to/photos/ \
  --manifest path/to/photos/tour.csv \
  --dry-run

# Upload
python uploader/upload_tour.py \
  --folder   path/to/photos/ \
  --manifest path/to/photos/tour.csv
```

A browser window will open for Google OAuth on first run.

### Step 5: Re-run connections if needed

Google needs a few minutes to process uploaded photos. If connection setup fails, run:

```bash
python uploader/upload_tour.py \
  --folder   path/to/photos/ \
  --manifest path/to/photos/tour.csv \
  --connect-only
```

## Utilities

### Restore EXIF/XMP after editing

Saving photos in GIMP or similar tools can strip GPS data and 360° metadata (XMP). Restore them from the originals:

```bash
# Restore GPS (lat/lng)
python uploader/restore_exif.py --src original/ --dst edited/

# Restore 360° XMP metadata (fixes "not a 360 photo" error)
python uploader/restore_xmp.py --src original/ --dst edited/
```

### Retry failed uploads

```bash
python uploader/retry_failed.py \
  --folder   path/to/photos/ \
  --manifest path/to/photos/tour.csv
```

### Find a Place ID

```bash
export GOOGLE_MAPS_API_KEY=your_key
python uploader/find_place_id.py --query "Venue name"
```

## File Structure

```
streetview-tour-uploader/
├── uploader/
│   ├── upload_tour.py      # Main uploader
│   ├── gen_tour_csv.py     # tour-config.json → tour.csv
│   ├── restore_exif.py     # Restore GPS EXIF after editing
│   ├── restore_xmp.py      # Restore 360° XMP metadata after editing
│   ├── retry_failed.py     # Retry failed uploads
│   └── find_place_id.py    # Look up Google Maps Place ID
├── editor/
│   ├── editor.html         # Browser-based tour editor (map + connections)
│   └── index.html          # Single 360° photo viewer
└── example/
    ├── tour.csv.example
    └── tour-meta.json.example
```

## Notes

- Uploaded photos are published publicly under your Google account
- It may take several hours to days for photos to appear in Street View
- **Never commit** `client_secrets.json` or `token.json` to Git

## License

MIT License
