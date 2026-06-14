# GeoTagged Photo Mapper - Streamlit Web App
# Developer: Dr. Sachchidanand Singh / NIH-WHRC style workflow

import base64
import io
import json
import math
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import folium
import pandas as pd
import streamlit as st
from folium import plugins
from PIL import Image, ImageEnhance, ExifTags
from streamlit_folium import st_folium


# -----------------------------
# Page configuration
# -----------------------------
st.set_page_config(
    page_title="GeoTagged Photo Mapper",
    page_icon="📍",
    layout="wide",
    initial_sidebar_state="expanded",
)


# -----------------------------
# Styling
# -----------------------------
st.markdown(
    """
    <style>
    .main {
        background: linear-gradient(180deg, #f7fbff 0%, #eef7f1 100%);
    }
    .block-container {
        padding-top: 1.4rem;
        padding-bottom: 2rem;
    }
    .hero-card {
        background: linear-gradient(135deg, #063b35 0%, #0f766e 45%, #0ea5e9 100%);
        color: white;
        border-radius: 22px;
        padding: 26px 30px;
        box-shadow: 0 18px 40px rgba(2, 44, 34, 0.20);
        margin-bottom: 18px;
    }
    .hero-card h1 {
        font-size: 2.25rem;
        font-weight: 800;
        margin-bottom: 6px;
        color: #ffffff;
    }
    .hero-card p {
        font-size: 1.04rem;
        line-height: 1.55;
        margin: 0;
        color: rgba(255,255,255,0.94);
    }
    .metric-card {
        background: #ffffff;
        border: 1px solid rgba(15, 118, 110, 0.12);
        border-radius: 18px;
        padding: 18px 20px;
        box-shadow: 0 10px 26px rgba(15, 23, 42, 0.06);
        min-height: 112px;
    }
    .metric-card .label {
        color: #64748b;
        font-size: 0.88rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .metric-card .value {
        color: #0f172a;
        font-size: 1.85rem;
        font-weight: 850;
        margin-top: 6px;
    }
    .metric-card .hint {
        color: #475569;
        font-size: 0.9rem;
        margin-top: 4px;
    }
    .section-title {
        color: #0f172a;
        font-weight: 850;
        font-size: 1.22rem;
        margin: 12px 0 8px 0;
    }
    .small-muted {
        color: #64748b;
        font-size: 0.9rem;
    }
    .stDownloadButton > button, .stButton > button {
        border-radius: 12px;
        font-weight: 700;
    }
    div[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #052e2b 0%, #064e3b 100%);
    }
    div[data-testid="stSidebar"] * {
        color: #ffffff !important;
    }
    div[data-testid="stSidebar"] input, div[data-testid="stSidebar"] textarea,
    div[data-testid="stSidebar"] select, div[data-testid="stSidebar"] option {
        color: #0f172a !important;
    }
    div[data-testid="stSidebar"] .stSelectbox div, div[data-testid="stSidebar"] .stMultiSelect div,
    div[data-testid="stSidebar"] .stNumberInput div, div[data-testid="stSidebar"] .stTextInput div {
        color: #0f172a !important;
    }
    .leaflet-popup-content-wrapper {
        border-radius: 14px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------
# Basemap configuration
# -----------------------------
BASEMAPS: Dict[str, Dict[str, str]] = {
    "OpenStreetMap": {
        "tiles": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attr": "© OpenStreetMap contributors",
    },
    "CartoDB Positron": {
        "tiles": "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        "attr": "© OpenStreetMap contributors © CARTO",
    },
    "CartoDB Dark Matter": {
        "tiles": "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        "attr": "© OpenStreetMap contributors © CARTO",
    },
    "Esri World Imagery": {
        "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attr": "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
    },
    "Esri World Street Map": {
        "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
        "attr": "Tiles © Esri",
    },
    "OpenTopoMap": {
        "tiles": "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        "attr": "Map data © OpenStreetMap contributors, SRTM | Map style © OpenTopoMap",
    },
}


# -----------------------------
# Helper functions
# -----------------------------
def safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        val = float(value)
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    except Exception:
        return None


def rational_to_float(value: Any) -> float:
    """Convert PIL EXIF rational values into float."""
    try:
        return float(value)
    except Exception:
        pass

    try:
        num, den = value
        return float(num) / float(den)
    except Exception:
        return float(value.numerator) / float(value.denominator)


def dms_to_decimal(dms: Any, ref: str) -> Optional[float]:
    try:
        degrees = rational_to_float(dms[0])
        minutes = rational_to_float(dms[1])
        seconds = rational_to_float(dms[2])
        decimal = degrees + minutes / 60.0 + seconds / 3600.0
        if ref in ["S", "W"]:
            decimal = -decimal
        return decimal
    except Exception:
        return None


def parse_text_for_coordinates(text: str) -> Tuple[Optional[float], Optional[float]]:
    """Parse coordinates from visible stamp/OCR text such as 'Lat: 32.69646° N Long: 74.84309° E'."""
    if not text:
        return None, None

    clean = text.replace("\n", " ").replace("|", " ")
    clean = re.sub(r"\s+", " ", clean)

    lat_patterns = [
        r"(?:Lat|Latitude|Lati)[\s\.:=]*([-+]?\d{1,3}(?:\.\d+)?)[\s°]*([NSns])?",
        r"([-+]?\d{1,2}\.\d+)[\s°]*([NSns])",
    ]
    lon_patterns = [
        r"(?:Long|Lon|Longitude|Lng)[\s\.:=]*([-+]?\d{1,3}(?:\.\d+)?)[\s°]*([EWew])?",
        r"([-+]?\d{1,3}\.\d+)[\s°]*([EWew])",
    ]

    lat = None
    lon = None

    for pattern in lat_patterns:
        match = re.search(pattern, clean, re.IGNORECASE)
        if match:
            lat = safe_float(match.group(1))
            ref = match.group(2).upper() if len(match.groups()) > 1 and match.group(2) else ""
            if lat is not None and ref == "S":
                lat = -abs(lat)
            break

    for pattern in lon_patterns:
        match = re.search(pattern, clean, re.IGNORECASE)
        if match:
            lon = safe_float(match.group(1))
            ref = match.group(2).upper() if len(match.groups()) > 1 and match.group(2) else ""
            if lon is not None and ref == "W":
                lon = -abs(lon)
            break

    if lat is not None and not (-90 <= lat <= 90):
        lat = None
    if lon is not None and not (-180 <= lon <= 180):
        lon = None

    return lat, lon


def extract_exif_gps(image: Image.Image) -> Tuple[Optional[float], Optional[float], Dict[str, Any]]:
    """Extract latitude/longitude from EXIF GPSInfo."""
    metadata: Dict[str, Any] = {}
    try:
        exif = image.getexif()
        if not exif:
            return None, None, metadata

        decoded: Dict[str, Any] = {}
        for tag_id, value in exif.items():
            tag = ExifTags.TAGS.get(tag_id, tag_id)
            decoded[tag] = value
            if tag in ["DateTime", "DateTimeOriginal", "ImageDescription", "Make", "Model", "Software"]:
                metadata[tag] = str(value)

        # Primary EXIF GPS read
        gps_info = decoded.get("GPSInfo") or exif.get(34853)
        if gps_info:
            gps_data: Dict[str, Any] = {}
            for key, value in gps_info.items():
                gps_tag = ExifTags.GPSTAGS.get(key, key)
                gps_data[gps_tag] = value

            lat = dms_to_decimal(gps_data.get("GPSLatitude"), gps_data.get("GPSLatitudeRef", "N"))
            lon = dms_to_decimal(gps_data.get("GPSLongitude"), gps_data.get("GPSLongitudeRef", "E"))
            if lat is not None and lon is not None:
                metadata["GPSAltitude"] = str(gps_data.get("GPSAltitude", ""))
                return lat, lon, metadata

        # Fallback: parse coordinates embedded in EXIF text fields
        exif_text = " ".join([str(v) for v in decoded.values()])
        lat, lon = parse_text_for_coordinates(exif_text)
        return lat, lon, metadata

    except Exception:
        return None, None, metadata


def extract_ocr_gps(image: Image.Image) -> Tuple[Optional[float], Optional[float], str]:
    """Optional OCR fallback for GeoTag Camera style coordinate stamp."""
    try:
        import pytesseract  # type: ignore
    except Exception:
        return None, None, "OCR skipped: pytesseract is not installed."

    try:
        w, h = image.size
        crop_boxes = [
            (0, int(h * 0.55), int(w * 0.68), h),  # lower-left coordinate stamp area
            (0, int(h * 0.45), int(w * 0.75), h),
            (0, 0, w, h),
        ]

        all_text = []
        for box in crop_boxes:
            crop = image.crop(box).convert("L")
            crop = ImageEnhance.Contrast(crop).enhance(2.2)
            crop = crop.resize((crop.width * 2, crop.height * 2))
            text = pytesseract.image_to_string(crop, config="--psm 6")
            all_text.append(text)
            lat, lon = parse_text_for_coordinates(text)
            if lat is not None and lon is not None:
                return lat, lon, text

        return None, None, "\n".join(all_text)
    except Exception as exc:
        return None, None, f"OCR failed: {exc}"


def make_thumbnail_b64(image: Image.Image, max_size: int = 360) -> str:
    img = image.copy().convert("RGB")
    img.thumbnail((max_size, max_size))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=78, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def process_uploaded_photos(uploaded_files: List[Any], use_ocr: bool) -> List[Dict[str, Any]]:
    photos: List[Dict[str, Any]] = []

    for idx, uploaded_file in enumerate(uploaded_files):
        raw_bytes = uploaded_file.getvalue()
        try:
            image = Image.open(io.BytesIO(raw_bytes))
            image.load()
        except Exception as exc:
            photos.append(
                {
                    "id": f"{idx}_{uploaded_file.name}",
                    "file_name": uploaded_file.name,
                    "lat": None,
                    "lon": None,
                    "source": "Unreadable",
                    "status": f"Could not read image: {exc}",
                    "metadata": {},
                    "thumb_b64": "",
                }
            )
            continue

        lat, lon, metadata = extract_exif_gps(image)
        source = "EXIF GPS"
        status = "Coordinates found from EXIF."

        if (lat is None or lon is None) and use_ocr:
            ocr_lat, ocr_lon, ocr_text = extract_ocr_gps(image)
            if ocr_lat is not None and ocr_lon is not None:
                lat, lon = ocr_lat, ocr_lon
                source = "OCR from visible stamp"
                status = "Coordinates found from visible GeoTag Camera stamp."
            else:
                source = "Missing"
                status = "No EXIF GPS found. OCR could not detect coordinates. Add them manually in the table."
                metadata["OCR_Text"] = ocr_text[:600]
        elif lat is None or lon is None:
            source = "Missing"
            status = "No EXIF GPS found. Enable OCR or add coordinates manually in the table."

        thumb_b64 = make_thumbnail_b64(image)

        photos.append(
            {
                "id": f"{idx}_{uploaded_file.name}",
                "file_name": uploaded_file.name,
                "lat": lat,
                "lon": lon,
                "source": source,
                "status": status,
                "metadata": metadata,
                "thumb_b64": thumb_b64,
            }
        )

    return photos


def create_map(photos: List[Dict[str, Any]], default_basemap: str, marker_color: str, show_heatmap: bool) -> folium.Map:
    valid = [p for p in photos if p.get("lat") is not None and p.get("lon") is not None]

    if valid:
        center_lat = sum(float(p["lat"]) for p in valid) / len(valid)
        center_lon = sum(float(p["lon"]) for p in valid) / len(valid)
        zoom_start = 16 if len(valid) <= 5 else 12
    else:
        center_lat, center_lon = 32.69646, 74.84309
        zoom_start = 13

    fmap = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom_start,
        tiles=None,
        control_scale=True,
        prefer_canvas=True,
    )

    # Add all basemaps; selected one is shown by default.
    for name, cfg in BASEMAPS.items():
        folium.TileLayer(
            tiles=cfg["tiles"],
            attr=cfg["attr"],
            name=name,
            overlay=False,
            control=True,
            show=(name == default_basemap),
        ).add_to(fmap)

    marker_cluster = plugins.MarkerCluster(name="Geotagged Photo Points", control=True).add_to(fmap)

    for i, p in enumerate(valid, start=1):
        lat = float(p["lat"])
        lon = float(p["lon"])
        meta_rows = ""
        if p.get("metadata"):
            for k, v in p["metadata"].items():
                if str(v).strip() and k != "OCR_Text":
                    meta_rows += f"<tr><td><b>{k}</b></td><td>{str(v)[:120]}</td></tr>"

        popup_html = f"""
        <div style="width: 300px; font-family: Arial, sans-serif;">
            <div style="font-size: 15px; font-weight: 800; color: #064e3b; margin-bottom: 6px;">📷 {p['file_name']}</div>
            <img src="data:image/jpeg;base64,{p['thumb_b64']}" style="width:100%; border-radius: 12px; border: 1px solid #e2e8f0;" />
            <table style="width:100%; margin-top:8px; font-size:12px; border-collapse:collapse;">
                <tr><td><b>Latitude</b></td><td>{lat:.6f}</td></tr>
                <tr><td><b>Longitude</b></td><td>{lon:.6f}</td></tr>
                <tr><td><b>Source</b></td><td>{p.get('source', '')}</td></tr>
                {meta_rows}
            </table>
        </div>
        """

        folium.Marker(
            location=[lat, lon],
            tooltip=f"{i}. {p['file_name']} | {lat:.5f}, {lon:.5f}",
            popup=folium.Popup(popup_html, max_width=340),
            icon=folium.Icon(color=marker_color, icon="camera", prefix="fa"),
        ).add_to(marker_cluster)

    if show_heatmap and len(valid) >= 3:
        heat_data = [[float(p["lat"]), float(p["lon"])] for p in valid]
        plugins.HeatMap(heat_data, name="Photo Density Heatmap", radius=22, blur=18).add_to(fmap)

    if valid:
        bounds = [[float(p["lat"]), float(p["lon"])] for p in valid]
        fmap.fit_bounds(bounds, padding=(30, 30))

    plugins.Fullscreen(position="topleft", title="Fullscreen", title_cancel="Exit fullscreen").add_to(fmap)
    plugins.MeasureControl(position="topleft", primary_length_unit="kilometers").add_to(fmap)
    plugins.LocateControl(position="topleft").add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)

    return fmap


def photos_to_geojson(photos: List[Dict[str, Any]]) -> Dict[str, Any]:
    features = []
    for p in photos:
        if p.get("lat") is None or p.get("lon") is None:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(p["lon"]), float(p["lat"])],
                },
                "properties": {
                    "file_name": p.get("file_name", ""),
                    "latitude": float(p["lat"]),
                    "longitude": float(p["lon"]),
                    "source": p.get("source", ""),
                    "status": p.get("status", ""),
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def make_download_df(photos: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for p in photos:
        rows.append(
            {
                "file_name": p.get("file_name"),
                "latitude": p.get("lat"),
                "longitude": p.get("lon"),
                "source": p.get("source"),
                "status": p.get("status"),
            }
        )
    return pd.DataFrame(rows)


# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    st.markdown("## ⚙️ Map Settings")
    default_basemap = st.selectbox(
        "Default basemap",
        list(BASEMAPS.keys()),
        index=list(BASEMAPS.keys()).index("Esri World Imagery"),
    )
    marker_color = st.selectbox(
        "Photo marker colour",
        ["blue", "green", "red", "purple", "orange", "darkred", "cadetblue", "darkgreen"],
        index=1,
    )
    show_heatmap = st.checkbox("Show photo density heatmap", value=False)
    use_ocr = st.checkbox(
        "Use OCR fallback for stamped GeoTag Camera photos",
        value=True,
        help="Useful when photos are PNG/screenshots without EXIF GPS but coordinates are printed on the image.",
    )
    st.markdown("---")
    st.markdown("### Supported inputs")
    st.markdown("JPG/JPEG with EXIF GPS, PNG/WebP with visible coordinate stamp, or manual lat-long entry.")


# -----------------------------
# Header
# -----------------------------
st.markdown(
    """
    <div class="hero-card">
        <h1>📍 GeoTagged Photo Mapper</h1>
        <p>
        Upload field photographs captured with GPS/GeoTag Camera. The app extracts coordinates, places every photo on an interactive map,
        supports multiple basemaps, displays image popups, and exports CSV/GeoJSON/HTML outputs for field reporting.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


# -----------------------------
# Upload area
# -----------------------------
uploaded_files = st.file_uploader(
    "Upload geotagged photos",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True,
    help="Upload multiple field photos. EXIF GPS is preferred. OCR can read visible Lat/Long stamps like your GeoTag Camera examples.",
)

if not uploaded_files:
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.markdown("""<div class="metric-card"><div class="label">Step 1</div><div class="value">Upload</div><div class="hint">Select JPG/PNG field photos.</div></div>""", unsafe_allow_html=True)
    with col_b:
        st.markdown("""<div class="metric-card"><div class="label">Step 2</div><div class="value">Extract</div><div class="hint">EXIF GPS or OCR coordinates.</div></div>""", unsafe_allow_html=True)
    with col_c:
        st.markdown("""<div class="metric-card"><div class="label">Step 3</div><div class="value">Map</div><div class="hint">View photo markers on basemaps.</div></div>""", unsafe_allow_html=True)
    st.info("Upload your geotagged photos to start mapping.")
    st.stop()

with st.spinner("Reading photos and extracting coordinates..."):
    photos = process_uploaded_photos(uploaded_files, use_ocr=use_ocr)

# Coordinate editor
st.markdown('<div class="section-title">1. Extracted Photo Coordinates</div>', unsafe_allow_html=True)
raw_df = make_download_df(photos)

editable_df = raw_df.copy()
editable_df.insert(0, "include", True)

edited_df = st.data_editor(
    editable_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "include": st.column_config.CheckboxColumn("Include", default=True),
        "file_name": st.column_config.TextColumn("Photo", disabled=True),
        "latitude": st.column_config.NumberColumn("Latitude", format="%.6f"),
        "longitude": st.column_config.NumberColumn("Longitude", format="%.6f"),
        "source": st.column_config.TextColumn("Source", disabled=True),
        "status": st.column_config.TextColumn("Status", disabled=True),
    },
)

# Apply edited coordinates back to photo objects
updated_photos: List[Dict[str, Any]] = []
for i, row in edited_df.iterrows():
    if not bool(row.get("include", True)):
        continue
    p = photos[i].copy()
    p["lat"] = safe_float(row.get("latitude"))
    p["lon"] = safe_float(row.get("longitude"))
    if p["lat"] is not None and p["lon"] is not None and p.get("source") == "Missing":
        p["source"] = "Manual entry"
        p["status"] = "Coordinates added manually by user."
    updated_photos.append(p)

valid_count = sum(1 for p in updated_photos if p.get("lat") is not None and p.get("lon") is not None)
missing_count = len(updated_photos) - valid_count

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(f"""<div class="metric-card"><div class="label">Uploaded Photos</div><div class="value">{len(uploaded_files)}</div><div class="hint">Total selected files</div></div>""", unsafe_allow_html=True)
with col2:
    st.markdown(f"""<div class="metric-card"><div class="label">Mapped Photos</div><div class="value">{valid_count}</div><div class="hint">Valid coordinates found</div></div>""", unsafe_allow_html=True)
with col3:
    st.markdown(f"""<div class="metric-card"><div class="label">Missing GPS</div><div class="value">{missing_count}</div><div class="hint">Can be edited manually</div></div>""", unsafe_allow_html=True)
with col4:
    st.markdown(f"""<div class="metric-card"><div class="label">Basemaps</div><div class="value">{len(BASEMAPS)}</div><div class="hint">Switch in layer control</div></div>""", unsafe_allow_html=True)

if missing_count > 0:
    st.warning("Some photos do not have valid coordinates. Enter latitude/longitude manually in the table above, or enable OCR if the coordinates are printed on the photo.")

# Map
st.markdown('<div class="section-title">2. Interactive Map</div>', unsafe_allow_html=True)
fmap = create_map(updated_photos, default_basemap=default_basemap, marker_color=marker_color, show_heatmap=show_heatmap)
st_folium(fmap, width=None, height=680, returned_objects=[])

# Downloads
st.markdown('<div class="section-title">3. Export Outputs</div>', unsafe_allow_html=True)
valid_photos = [p for p in updated_photos if p.get("lat") is not None and p.get("lon") is not None]
download_df = make_download_df(valid_photos)
geojson = photos_to_geojson(valid_photos)
map_html = fmap.get_root().render()

d1, d2, d3 = st.columns(3)
with d1:
    st.download_button(
        "⬇️ Download CSV",
        data=download_df.to_csv(index=False).encode("utf-8"),
        file_name="geotagged_photo_points.csv",
        mime="text/csv",
        use_container_width=True,
    )
with d2:
    st.download_button(
        "⬇️ Download GeoJSON",
        data=json.dumps(geojson, indent=2).encode("utf-8"),
        file_name="geotagged_photo_points.geojson",
        mime="application/geo+json",
        use_container_width=True,
    )
with d3:
    st.download_button(
        "⬇️ Download HTML Map",
        data=map_html.encode("utf-8"),
        file_name="geotagged_photo_interactive_map.html",
        mime="text/html",
        use_container_width=True,
    )

# Gallery
st.markdown('<div class="section-title">4. Photo Gallery</div>', unsafe_allow_html=True)
if valid_photos:
    gallery_cols = st.columns(3)
    for i, p in enumerate(valid_photos):
        with gallery_cols[i % 3]:
            st.image(base64.b64decode(p["thumb_b64"]), caption=f"{p['file_name']} | {float(p['lat']):.5f}, {float(p['lon']):.5f}", use_container_width=True)
else:
    st.info("No photos with valid coordinates are available for the gallery/map yet.")

st.markdown(
    """
    <div class="small-muted">
    Note: Some mobile apps save GPS inside EXIF metadata, while some GeoTag Camera exports only print coordinates on the image. For stamped PNG photos,
    keep OCR enabled. On local systems, OCR requires Tesseract installation.
    </div>
    """,
    unsafe_allow_html=True,
)
