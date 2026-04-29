"""
build_data.py — Generates all CSVs for the GitHub Pages site.
Requires internet access to data.cityofchicago.org.

All output files are written to the data/ subdirectory.
Run from: projects/chicago-food-inspections/
"""
import os
import urllib.request
import pandas as pd
from urllib.parse import urlencode

# ============================================================
# PATHS — everything goes into the data/ folder
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(SCRIPT_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)

def data_path(filename):
    """Return the full path to a file inside data/."""
    return os.path.join(DATA_DIR, filename)

# ============================================================
# PRIMARY DATASET — Chicago Food Inspections
# ============================================================
URL = "https://data.cityofchicago.org/api/views/4ijn-s7e5/rows.csv?accessType=DOWNLOAD"
print("Loading Food Inspections dataset (~323 MB, may take a minute)...")
df = pd.read_csv(URL)
print(f"Raw shape: {df.shape}")

df['Inspection Date'] = pd.to_datetime(df['Inspection Date'])
df['Year'] = df['Inspection Date'].dt.year

df_filtered = df[
    df['Results'].isin(['Pass', 'Fail', 'Pass w/ Conditions']) &
    df['Risk'].isin(['Risk 1 (High)', 'Risk 2 (Medium)', 'Risk 3 (Low)']) &
    df['Facility Type'].notna() &
    (df['Year'] >= 2010) & (df['Year'] <= 2025)
].copy()

top_facilities = df_filtered['Facility Type'].value_counts().head(8).index.tolist()
df_filtered = df_filtered[df_filtered['Facility Type'].isin(top_facilities)]
print(f"Filtered shape: {df_filtered.shape}")

# ---- 1. driver_data.csv ----
driver_data = (
    df_filtered.groupby(['Facility Type', 'Results']).size().reset_index(name='Count')
)
driver_data['Total per Facility'] = driver_data.groupby('Facility Type')['Count'].transform('sum')
driver_data['Percentage'] = (driver_data['Count'] / driver_data['Total per Facility'] * 100).round(1)
driver_data.to_csv(data_path('driver_data.csv'), index=False)
print(f"[OK] driver_data.csv: {driver_data.shape}")

# ---- 2. yearly_pass.csv ----
yearly_total = df_filtered.groupby(['Facility Type', 'Year']).size().reset_index(name='Total')
yearly_pass_count = (
    df_filtered[df_filtered['Results'] == 'Pass']
    .groupby(['Facility Type', 'Year']).size().reset_index(name='Count')
)
yearly_pass = yearly_pass_count.merge(yearly_total, on=['Facility Type', 'Year'])
yearly_pass['Pass Rate'] = (yearly_pass['Count'] / yearly_pass['Total'] * 100).round(2)
yearly_pass = yearly_pass[['Facility Type', 'Year', 'Pass Rate', 'Total']]
yearly_pass.to_csv(data_path('yearly_pass.csv'), index=False)
print(f"[OK] yearly_pass.csv: {yearly_pass.shape}")

# ---- 3. before_after.csv ----
before = yearly_pass[yearly_pass['Year'] == 2017][['Facility Type', 'Pass Rate']].rename(
    columns={'Pass Rate': 'Pass_2017'}
)
after = yearly_pass[yearly_pass['Year'] == 2019][['Facility Type', 'Pass Rate']].rename(
    columns={'Pass Rate': 'Pass_2019'}
)
before_after = before.merge(after, on='Facility Type')
before_after['Drop'] = (before_after['Pass_2017'] - before_after['Pass_2019']).round(2)
before_after = before_after.sort_values('Drop', ascending=False)
before_after.to_csv(data_path('before_after.csv'), index=False)
print(f"[OK] before_after.csv: {before_after.shape}")

# ============================================================
# CONTEXTUAL DATASET — Chicago Business Licenses (Socrata API)
# ============================================================
print("\nQuerying Business Licenses dataset (server-side filtered)...")

food_categories = [
    "Retail Food Establishment",
    "Wholesale Food Establishment",
    "Mobile Food Dispenser",
    "Mobile Food License",
    "Mobile Frozen Desserts Dispenser - Non-Motorized",
    "Food - Shared Kitchen",
    "Food - Shared Kitchen - Supplemental",
    "Pop-Up Food Est. User - Tier I",
    "Pop-Up Food Est. User - Tier II",
    "Pop-Up Food Est. User - Tier III",
    "Peddler, food (fruits and vegtables only)",
    "Peddler,food - (fruits and vegetables only) - special",
    "Navy Pier Vendor (Food)",
    "Navy Pier Vendor (Food) 30 Day",
]

def soql_escape(s):
    return s.replace("'", "''")

in_clause = ", ".join(f"'{soql_escape(c)}'" for c in food_categories)

params = {
    "$select": "license_number,license_description,license_start_date,expiration_date,zip_code,latitude,longitude",
    "$where":  f"license_description in({in_clause})",
    "$limit":  "500000",
}
LIC_API = "https://data.cityofchicago.org/resource/r5kz-chrr.csv?" + urlencode(params)

food_lic = pd.read_csv(LIC_API)
print(f"Food-related license rows downloaded: {food_lic.shape}")

food_lic['license_start_date'] = pd.to_datetime(food_lic['license_start_date'], errors='coerce')
food_lic['expiration_date']    = pd.to_datetime(food_lic['expiration_date'],    errors='coerce')

# ============================================================
# Build inspections-with-license-description join
# (used by both pictograph and active-uninspected analyses)
# ============================================================
df_join = df.copy()
df_join['Year'] = df_join['Inspection Date'].dt.year
df_join['License #'] = pd.to_numeric(df_join['License #'], errors='coerce')
df_join = df_join[
    (df_join['Year'] >= 2010) & (df_join['Year'] <= 2025) &
    df_join['Results'].isin(['Pass', 'Fail', 'Pass w/ Conditions']) &
    (df_join['License #'] > 0)
]

lic_desc_map = (
    food_lic.dropna(subset=['license_number'])
    .groupby('license_number')['license_description']
    .agg(lambda s: s.mode().iloc[0] if not s.mode().empty else None)
    .to_dict()
)
df_join['license_description'] = df_join['License #'].map(lic_desc_map)

inspected_license_nums = set(df_join['License #'].dropna().unique())

# ============================================================
# DATA FOR CHART 4 — Pictograph of first-inspection outcomes
# ============================================================
print("\nBuilding pictograph data...")

first_insp = (
    df_join.dropna(subset=['license_description'])
    .sort_values(['License #', 'Inspection Date'])
    .groupby('License #')
    .first()
    .reset_index()
)

pictograph_categories = {
    'Retail Food Establishment':    'Retail Food',
    'Mobile Food License':          'Mobile Food',
    'Mobile Food Dispenser':        'Mobile Food',
    'Wholesale Food Establishment': 'Wholesale Food',
}
first_insp['Pictograph Category'] = (
    first_insp['license_description'].map(pictograph_categories)
)

def make_pictograph_rows(label, subset):
    n = len(subset)
    if n == 0:
        return []
    counts = subset['Results'].value_counts()
    rows = []
    for result in ['Pass', 'Pass w/ Conditions', 'Fail']:
        pct = round(counts.get(result, 0) / n * 100)
        rows.append({'Group': label, 'Result': result, 'Percentage': pct, 'N': n})
    total = sum(r['Percentage'] for r in rows)
    if total != 100:
        biggest = max(rows, key=lambda r: r['Percentage'])
        biggest['Percentage'] += (100 - total)
    return rows

pictograph_data = []
pictograph_data += make_pictograph_rows('All Chicago Food Businesses', first_insp)
for raw_label, display_label in [
    ('Retail Food',    'Retail Food (restaurants, grocery, bakery)'),
    ('Mobile Food',    'Mobile Food (trucks & carts)'),
    ('Wholesale Food', 'Wholesale Food'),
]:
    subset = first_insp[first_insp['Pictograph Category'] == raw_label]
    pictograph_data += make_pictograph_rows(display_label, subset)

pictograph_rows = []
for r in pictograph_data:
    for i in range(r['Percentage']):
        pictograph_rows.append({
            'Group': r['Group'],
            'Result': r['Result'],
            'icon_index': i,
            'N_total': r['N'],
        })

pictograph_df = pd.DataFrame(pictograph_rows)

def assign_grid_position(group_df):
    group_df = group_df.sort_values('Result',
                                    key=lambda s: s.map({'Pass': 0,
                                                         'Pass w/ Conditions': 1,
                                                         'Fail': 2})).reset_index(drop=True)
    group_df['Position'] = group_df.index
    group_df['Row'] = group_df['Position'] // 10
    group_df['Col'] = group_df['Position'] % 10
    return group_df

result_parts = []
for group_name, group_df in pictograph_df.groupby('Group'):
    positioned = assign_grid_position(group_df.copy())
    positioned['Group'] = group_name
    result_parts.append(positioned)
pictograph_df = pd.concat(result_parts, ignore_index=True)
pictograph_df.to_csv(data_path('pictograph_first_inspection.csv'), index=False)
print(f"[OK] pictograph_first_inspection.csv: {pictograph_df.shape}")

# ============================================================
# DATA FOR CHART 5 — Active-mature uninspected (horizontal bars)
# ============================================================
print("\nBuilding active-mature uninspected data...")

today = pd.Timestamp.today().normalize()
two_years_ago = today - pd.Timedelta(days=730)

license_lifespan = (
    food_lic.dropna(subset=['license_number', 'license_start_date', 'expiration_date'])
    .groupby('license_number')
    .agg(
        first_start=('license_start_date', 'min'),
        last_expiration=('expiration_date', 'max'),
        license_description=('license_description',
                             lambda s: s.mode().iloc[0] if not s.mode().empty else None)
    )
    .reset_index()
)

active_mature = license_lifespan[
    (license_lifespan['last_expiration'] >= today) &
    (license_lifespan['first_start']    <= two_years_ago)
].copy()
active_mature['was_inspected'] = active_mature['license_number'].isin(inspected_license_nums)

breakdown = (
    active_mature.groupby('license_description')
    .agg(
        active_mature_total=('license_number', 'count'),
        inspected=('was_inspected', 'sum')
    )
    .reset_index()
)
breakdown['never_inspected']   = breakdown['active_mature_total'] - breakdown['inspected']
breakdown['% never inspected'] = (
    breakdown['never_inspected'] / breakdown['active_mature_total'] * 100
).round(1)
breakdown = breakdown.sort_values('never_inspected', ascending=False)

display_label_map = {
    'Retail Food Establishment':            'Retail Food (restaurants, grocery, bakery)',
    'Mobile Food License':                  'Mobile Food (trucks & carts)',
    'Wholesale Food Establishment':         'Wholesale Food *',
    'Food - Shared Kitchen':                'Shared Kitchen',
    'Food - Shared Kitchen - Supplemental': 'Shared Kitchen Supplemental *',
}
breakdown['Display Label'] = breakdown['license_description'].map(display_label_map)
breakdown['Display Label'] = breakdown['Display Label'].fillna(breakdown['license_description'])

# Filter to only the 5 categories we care about
keep_categories = list(display_label_map.keys())
lollipop_data = breakdown[breakdown['license_description'].isin(keep_categories)][[
    'Display Label', 'license_description',
    'active_mature_total', 'inspected', 'never_inspected', '% never inspected'
]].rename(columns={
    'active_mature_total': 'Active Licenses',
    'inspected':           'Inspected',
    'never_inspected':     'Never Inspected',
    '% never inspected':   'Pct Never Inspected'
})
lollipop_data.to_csv(data_path('active_uninspected.csv'), index=False)
print(f"[OK] active_uninspected.csv: {lollipop_data.shape}")

# ============================================================
# DATA FOR CHART 6 — Chicago ZIP-code map (Retail Food only)
# ============================================================
print("\nBuilding ZIP-level map data for Retail Food...")

GEOJSON_PATH = data_path('chicago_zips.geojson')
JSON_ALT     = data_path('chicago_zips.json')
GEOJSON_URL  = 'https://raw.githubusercontent.com/lseemann/Chicago_ZIP_Codes/master/chicago_zips.json'

if not os.path.exists(GEOJSON_PATH):
    if os.path.exists(JSON_ALT):
        import shutil
        shutil.copy2(JSON_ALT, GEOJSON_PATH)
        print(f"[OK] Copied {JSON_ALT} -> {GEOJSON_PATH}")
    else:
        print("Downloading Chicago ZIP boundaries from GitHub...")
        urllib.request.urlretrieve(GEOJSON_URL, GEOJSON_PATH)
        print(f"[OK] {GEOJSON_PATH}")
else:
    print(f"[OK] {GEOJSON_PATH} (already exists)")

retail_lifespan = (
    food_lic[food_lic['license_description'] == 'Retail Food Establishment']
    .dropna(subset=['license_number', 'license_start_date', 'expiration_date'])
    .groupby('license_number')
    .agg(
        first_start=('license_start_date', 'min'),
        last_expiration=('expiration_date', 'max'),
        zip_code=('zip_code', lambda s: s.mode().iloc[0] if not s.mode().empty else None),
        latitude=('latitude', 'first'),
        longitude=('longitude', 'first'),
    )
    .reset_index()
)

retail_active_mature = retail_lifespan[
    (retail_lifespan['last_expiration'] >= today) &
    (retail_lifespan['first_start']    <= two_years_ago) &
    retail_lifespan['zip_code'].notna()
].copy()
retail_active_mature['was_inspected'] = (
    retail_active_mature['license_number'].isin(inspected_license_nums)
)

retail_active_mature['zip_code'] = (
    retail_active_mature['zip_code'].astype(str).str.strip().str[:5]
)
retail_active_mature = retail_active_mature[
    retail_active_mature['zip_code'].str.match(r'^606\d\d$|^607\d\d$')
]

zip_coverage = (
    retail_active_mature.groupby('zip_code')
    .agg(
        total_active=('license_number', 'count'),
        uninspected=('was_inspected', lambda s: (~s).sum())
    )
    .reset_index()
)
zip_coverage['pct_uninspected'] = (
    zip_coverage['uninspected'] / zip_coverage['total_active'] * 100
).round(1)
zip_coverage['low_volume'] = zip_coverage['total_active'] < 20
zip_coverage.to_csv(data_path('zip_coverage.csv'), index=False)
print(f"[OK] zip_coverage.csv: {zip_coverage.shape}")

uninspected_dots = retail_active_mature[
    (~retail_active_mature['was_inspected']) &
    retail_active_mature['latitude'].notna() &
    retail_active_mature['longitude'].notna()
][['license_number', 'zip_code', 'latitude', 'longitude']].copy()
uninspected_dots.to_csv(data_path('uninspected_dots.csv'), index=False)
print(f"[OK] uninspected_dots.csv: {uninspected_dots.shape}")

print(f"\nAll CSVs and GeoJSON written to: {DATA_DIR}")
print("Now run build_charts.py to generate the HTML visualizations.")

