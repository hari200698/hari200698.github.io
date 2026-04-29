"""
build_charts.py — Generates standalone interactive HTML chart files.
Run after build_data.py.

Reads CSVs from data/, writes HTML files to charts/.
Run from: projects/chicago-food-inspections/
"""
import os
import json
import pandas as pd
import altair as alt

alt.data_transformers.disable_max_rows()

# ============================================================
# PATHS — read from data/, write to charts/
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(SCRIPT_DIR, 'data')
CHARTS_DIR = os.path.join(SCRIPT_DIR, 'charts')
os.makedirs(CHARTS_DIR, exist_ok=True)

def data_path(filename):
    return os.path.join(DATA_DIR, filename)

def chart_path(filename):
    return os.path.join(CHARTS_DIR, filename)

# ============================================================
# LOAD DATA
# ============================================================
driver_data       = pd.read_csv(data_path('driver_data.csv'))
yearly_pass       = pd.read_csv(data_path('yearly_pass.csv'))
before_after      = pd.read_csv(data_path('before_after.csv'))
pictograph_df     = pd.read_csv(data_path('pictograph_first_inspection.csv'))
active_uninsp     = pd.read_csv(data_path('active_uninspected.csv'))
zip_coverage      = pd.read_csv(data_path('zip_coverage.csv'))
uninspected_dots  = pd.read_csv(data_path('uninspected_dots.csv'))

facility_order = [
    'Restaurant', 'Grocery Store', 'School', "Children's Services Facility",
    'Bakery', 'Daycare Above and Under 2 Years', 'Daycare (2 - 6 Years)', 'Long Term Care'
]
facility_colors = alt.Scale(
    domain=facility_order,
    range=['#4E79A7', '#F28E2B', '#59A14F', '#E15759',
           '#76B7B2', '#EDC948', '#B07AA1', '#FF9DA7']
)

# ============================================================
# CHART 1 — CENTRAL VIZ: Small multiples + linked annotated timeline
# ============================================================
year_brush = alt.selection_interval(encodings=['x'])

small_mults = (
    alt.Chart(yearly_pass)
    .mark_line(strokeWidth=2.5, point=alt.OverlayMarkDef(size=40))
    .encode(
        x=alt.X('Year:O', title=None,
                axis=alt.Axis(labelAngle=-45, labelFontSize=8, labelOverlap=False)),
        y=alt.Y('Pass Rate:Q', title='Pass Rate (%)',
                scale=alt.Scale(domain=[0, 100])),
        color=alt.Color('Facility Type:N', scale=facility_colors, legend=None),
        opacity=alt.condition(year_brush, alt.value(1.0), alt.value(0.25)),
        tooltip=[
            alt.Tooltip('Facility Type:N'),
            alt.Tooltip('Year:O'),
            alt.Tooltip('Pass Rate:Q', format='.1f'),
            alt.Tooltip('Total:Q', title='Inspections', format=',')
        ]
    )
    .properties(width=280, height=180)
    .facet(
        facet=alt.Facet('Facility Type:N', title=None,
                        header=alt.Header(labelFontSize=11, labelFontWeight='bold')),
        columns=4
    )
    .resolve_scale(y='shared')
)

agg = (
    yearly_pass.assign(weighted=yearly_pass['Pass Rate'] * yearly_pass['Total'])
    .groupby('Year', as_index=False)
    .agg(weighted_sum=('weighted', 'sum'), total_sum=('Total', 'sum'))
)
agg['Pass Rate'] = agg['weighted_sum'] / agg['total_sum']
agg = agg[['Year', 'Pass Rate']]

base_overview = alt.Chart(agg).encode(
    x=alt.X('Year:O', title='Year (drag on this chart to filter the panels above)'),
    y=alt.Y('Pass Rate:Q', title='Avg Pass Rate (%)', scale=alt.Scale(domain=[0, 100]))
)
overview_line = base_overview.mark_line(color='#2c3e50', strokeWidth=3, point=True)

annotations = pd.DataFrame([
    {'Year': 2018, 'label': '2018: New CDPH violation rules', 'y_pos': 92},
    {'Year': 2020, 'label': '2020: COVID-19', 'y_pos': 78}
])
ann_rules = alt.Chart(annotations).mark_rule(
    color='#c0392b', strokeDash=[4, 4], strokeWidth=1.5
).encode(x='Year:O')
ann_text = alt.Chart(annotations).mark_text(
    align='left', dx=6, color='#c0392b', fontSize=11, fontWeight='bold'
).encode(x='Year:O', y=alt.Y('y_pos:Q'), text='label:N')

overview = (overview_line + ann_rules + ann_text).add_params(year_brush).properties(
    width=1240, height=180,
    title=alt.TitleParams(
        text='Citywide Average Pass Rate (2010–2025)',
        subtitle='Drag to highlight a year range — the panels above will dim outside your selection',
        fontSize=14
    )
)

central_viz = alt.vconcat(small_mults, overview, spacing=15).properties(
    title=alt.TitleParams(
        text='Pass Rates Across 8 Chicago Facility Types, 2010–2025',
        subtitle='Each panel shows one facility type. Hover for details. Drag the bottom timeline to focus on a year range.',
        fontSize=18, anchor='start', color='#2c3e50'
    )
).configure_view(stroke=None).configure_axis(
    labelFontSize=10, titleFontSize=11, grid=True, gridColor='#EEE'
)
central_viz.save(chart_path('main_dashboard.html'))
print("[OK] main_dashboard.html")

# ============================================================
# CHART 2 — Dumbbell chart (2017 vs 2019)
# ============================================================
ba_long = before_after.melt(
    id_vars=['Facility Type', 'Drop'],
    value_vars=['Pass_2017', 'Pass_2019'],
    var_name='Year', value_name='Pass Rate'
)
ba_long['Year'] = ba_long['Year'].map({'Pass_2017': '2017', 'Pass_2019': '2019'})

bars = alt.Chart(before_after).mark_bar(height=4, color='#bbb').encode(
    y=alt.Y('Facility Type:N', sort=alt.SortField('Drop', order='descending'), title=None),
    x=alt.X('Pass_2019:Q', title='Pass Rate (%)', scale=alt.Scale(domain=[0, 100])),
    x2='Pass_2017:Q'
)
dots = alt.Chart(ba_long).mark_circle(size=200, opacity=1).encode(
    y=alt.Y('Facility Type:N', sort=alt.SortField('Drop', order='descending'), title=None),
    x=alt.X('Pass Rate:Q'),
    color=alt.Color('Year:N',
                    scale=alt.Scale(domain=['2017', '2019'], range=['#27ae60', '#c0392b']),
                    legend=alt.Legend(title='Year', orient='top')),
    tooltip=['Facility Type:N', 'Year:N', alt.Tooltip('Pass Rate:Q', format='.1f')]
)
labels = alt.Chart(before_after).mark_text(
    align='left', dx=8, fontSize=11, fontWeight='bold', color='#c0392b'
).encode(
    y=alt.Y('Facility Type:N', sort=alt.SortField('Drop', order='descending')),
    x='Pass_2017:Q',
    text=alt.Text('Drop:Q', format='.1f')
)

dumbbell = (bars + dots + labels).properties(
    width=900, height=320,
    title=alt.TitleParams(
        text='Two Years, One Rule Change',
        subtitle='Pass rates collapsed across every facility type between 2017 and 2019. Numbers show percentage-point drop.',
        fontSize=16, anchor='start', color='#2c3e50'
    )
).configure_view(stroke=None).configure_axis(grid=True, gridColor='#EEE')
dumbbell.save(chart_path('before_after.html'))
print("[OK] before_after.html")

# ============================================================
# CHART 3 — Heatmap (Facility × Year)
# ============================================================
heatmap = alt.Chart(yearly_pass).mark_rect().encode(
    x=alt.X('Year:O', title='Year'),
    y=alt.Y('Facility Type:N', sort=facility_order, title=None),
    color=alt.Color('Pass Rate:Q',
                    scale=alt.Scale(scheme='redyellowgreen', domain=[0, 100]),
                    legend=alt.Legend(title='Pass Rate (%)', orient='right')),
    tooltip=[
        alt.Tooltip('Facility Type:N'),
        alt.Tooltip('Year:O'),
        alt.Tooltip('Pass Rate:Q', format='.1f'),
        alt.Tooltip('Total:Q', title='Inspections', format=',')
    ]
).properties(
    width=1000, height=320,
    title=alt.TitleParams(
        text='Where the Failures Concentrated',
        subtitle='Red = low pass rate, green = high. The 2018–2019 column lights up red across nearly every row.',
        fontSize=16, anchor='start', color='#2c3e50'
    )
)
heatmap_text = alt.Chart(yearly_pass).mark_text(fontSize=9).encode(
    x='Year:O',
    y=alt.Y('Facility Type:N', sort=facility_order),
    text=alt.Text('Pass Rate:Q', format='.0f'),
    color=alt.condition(
        'datum["Pass Rate"] < 35 || datum["Pass Rate"] > 75',
        alt.value('white'), alt.value('black')
    )
)
heatmap_full = (heatmap + heatmap_text).configure_view(stroke=None).configure_axis(
    labelFontSize=11, titleFontSize=12, labelLimit=200
)
heatmap_full.save(chart_path('heatmap.html'))
print("[OK] heatmap.html")

# ============================================================
# CHART 4 — CONTEXTUAL VIZ #1: Pictograph of first-inspection outcomes
# ============================================================
group_order = [
    'All Chicago Food Businesses',
    'Retail Food (restaurants, grocery, bakery)',
    'Mobile Food (trucks & carts)',
    'Wholesale Food',
]
result_palette = alt.Scale(
    domain=['Pass', 'Pass w/ Conditions', 'Fail'],
    range=['#27ae60', '#f39c12', '#c0392b']
)

# Build the inner chart first (one panel)
inner = alt.Chart(pictograph_df).mark_point(
    filled=True, size=110, shape='square'
).encode(
    x=alt.X('Col:O', axis=None),
    y=alt.Y('Row:O', axis=None, sort='descending'),
    color=alt.Color('Result:N', scale=result_palette,
                    legend=alt.Legend(title=None, orient='top',
                                      labelFontSize=12, symbolSize=120)),
    tooltip=[
        alt.Tooltip('Group:N', title='Group'),
        alt.Tooltip('Result:N', title='Outcome'),
        alt.Tooltip('N_total:Q', title='Sample size', format=',')
    ]
).properties(width=240, height=240)

# Apply facet — and the title — in a single chained call.
# Key fix: don't call .properties() again after .facet()
pictograph = inner.facet(
    facet=alt.Facet('Group:N', title=None, sort=group_order,
                    header=alt.Header(labelFontSize=13, labelFontWeight='bold',
                                      labelLimit=300, labelPadding=10)),
    columns=2,
    title=alt.TitleParams(
        text='Of Every 100 New Chicago Food Businesses, How Many Pass on Day One?',
        subtitle=('Each square represents 1% of first-ever inspections in that category. '
                  'Green = clean pass, amber = pass with conditions, red = fail.'),
        fontSize=15, anchor='start', color='#2c3e50',
        subtitleFontSize=11, subtitleColor='#666'
    )
).resolve_scale(x='shared', y='shared').configure_view(stroke=None)

pictograph.save(chart_path('pictograph_first_inspection.html'))
print("[OK] pictograph_first_inspection.html (CONTEXTUAL VIZ #1)")

# ============================================================
# CHART 5 — CONTEXTUAL VIZ #2 (option A): Active-uninspected bars
# ============================================================
sort_order = active_uninsp.sort_values(
    'Pct Never Inspected', ascending=False
)['Display Label'].tolist()

uninsp_bars = alt.Chart(active_uninsp).mark_bar(color='#c0392b').encode(
    y=alt.Y('Display Label:N', sort=sort_order, title=None,
            axis=alt.Axis(labelLimit=320, labelFontSize=12)),
    x=alt.X('Pct Never Inspected:Q',
            title='% of active mature licenses never inspected',
            scale=alt.Scale(domain=[0, 100])),
    tooltip=[
        alt.Tooltip('Display Label:N', title='Category'),
        alt.Tooltip('Active Licenses:Q', title='Active mature licenses', format=','),
        alt.Tooltip('Inspected:Q', title='Inspected', format=','),
        alt.Tooltip('Never Inspected:Q', title='Never inspected', format=','),
        alt.Tooltip('Pct Never Inspected:Q', title='% never inspected', format='.1f')
    ]
)

active_uninsp['count_label'] = (
    active_uninsp['Never Inspected'].astype(int).astype(str)
    + ' of '
    + active_uninsp['Active Licenses'].astype(int).map('{:,}'.format)
)
count_labels = alt.Chart(active_uninsp).mark_text(
    align='left', dx=8, fontSize=11, color='#444'
).encode(
    y=alt.Y('Display Label:N', sort=sort_order),
    x=alt.X('Pct Never Inspected:Q'),
    text='count_label:N'
)

uninspected_chart = alt.layer(uninsp_bars, count_labels).properties(
    width=800, height=280,
    title=alt.TitleParams(
        text='Where Chicago\'s Inspection Gaps Concentrate',
        subtitle='Share of long-active food licenses (2+ years) that have never received a CDPH inspection.',
        fontSize=15, anchor='start', color='#2c3e50',
        subtitleFontSize=11, subtitleColor='#666'
    )
).configure_view(stroke=None).configure_axis(
    grid=True, gridColor='#EEE', labelFontSize=11, titleFontSize=12
)
uninspected_chart.save(chart_path('active_uninspected.html'))
print("[OK] active_uninspected.html (CONTEXTUAL VIZ #2 — option A: bars)")

# ============================================================
# CHART 6 — CONTEXTUAL VIZ #2 (option B): ZIP map of Retail Food
# ============================================================
GEOJSON_PATH = data_path('chicago_zips.geojson')

with open(GEOJSON_PATH, 'r', encoding='utf-8') as f:
    chicago_geo = json.load(f)

# Print the first feature's property keys so we can verify the ZIP field name
print("GeoJSON property keys:", list(chicago_geo['features'][0]['properties'].keys()))

zip_coverage['zip_code'] = zip_coverage['zip_code'].astype(str)
uninspected_dots['latitude']  = pd.to_numeric(uninspected_dots['latitude'],  errors='coerce')
uninspected_dots['longitude'] = pd.to_numeric(uninspected_dots['longitude'], errors='coerce')
uninspected_dots = uninspected_dots.dropna(subset=['latitude', 'longitude'])

geo_data = alt.Data(values=chicago_geo['features'])

choropleth = alt.Chart(geo_data).mark_geoshape(
    stroke='white', strokeWidth=0.5
).encode(
    color=alt.Color('pct_uninspected:Q',
                    scale=alt.Scale(scheme='reds', domain=[0, 10], clamp=True),
                    legend=alt.Legend(title='% never inspected',
                                      orient='right', format='.0f')),
    tooltip=[
        alt.Tooltip('properties.ZIP:N',  title='ZIP code'),
        alt.Tooltip('total_active:Q',    title='Active Retail Food licenses', format=','),
        alt.Tooltip('uninspected:Q',     title='Never inspected', format=','),
        alt.Tooltip('pct_uninspected:Q', title='% never inspected', format='.1f')
    ]
).transform_lookup(
    lookup='properties.ZIP',
    from_=alt.LookupData(zip_coverage, 'zip_code',
                         ['total_active', 'uninspected', 'pct_uninspected'])
).project(type='mercator').properties(width=700, height=720)

dots_layer = alt.Chart(uninspected_dots).mark_circle(
    color='#2c3e50', opacity=0.7, size=18, stroke='white', strokeWidth=0.5
).encode(
    longitude='longitude:Q',
    latitude='latitude:Q',
    tooltip=[
        alt.Tooltip('zip_code:N', title='ZIP'),
        alt.Tooltip('license_number:Q', title='License #')
    ]
)

map_chart = alt.layer(choropleth, dots_layer).properties(
    title=alt.TitleParams(
        text='Where Chicago\'s Uninspected Restaurants Live',
        subtitle=('Each dot is a long-active retail food business that has never been inspected. '
                  'ZIP fill = share of that ZIP\'s licensed retail food businesses never inspected.'),
        fontSize=15, anchor='start', color='#2c3e50',
        subtitleFontSize=11, subtitleColor='#666'
    )
).configure_view(stroke=None)

map_chart.save(chart_path('chicago_inspection_map.html'))
print("[OK] chicago_inspection_map.html (CONTEXTUAL VIZ #2 — option B: map)")

print(f"\nDone — 6 HTML files written to: {CHARTS_DIR}")
print("Compare active_uninspected.html and chicago_inspection_map.html")
print("to pick your final contextual viz #2.")

