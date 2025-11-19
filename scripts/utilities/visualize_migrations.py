#!/usr/bin/env python3
"""
Create an interactive map visualization of historical migration patterns.
Shows birth-to-death place connections for all people in the database.
"""

import os
from neo4j import GraphDatabase
from dotenv import load_dotenv
import plotly.graph_objects as go
from collections import defaultdict
import json

load_dotenv()

driver = GraphDatabase.driver(
    os.getenv('NEO4J_URI'),
    auth=(os.getenv('NEO4J_USER'), os.getenv('NEO4J_PASSWORD'))
)

print("\n" + "="*80)
print("CREATING MIGRATION PATTERN VISUALIZATION")
print("="*80)

with driver.session(database='neo4j') as session:

    # Get all people with both birth and death locations
    print("\nQuerying database for migration data...")

    query = """
    MATCH (person:HistoricalPerson)-[:BORN_IN]->(birthPlace:Place)
    MATCH (person)-[:DIED_IN]->(deathPlace:Place)
    WHERE birthPlace.latitude IS NOT NULL
      AND birthPlace.longitude IS NOT NULL
      AND deathPlace.latitude IS NOT NULL
      AND deathPlace.longitude IS NOT NULL
    RETURN person.name AS name,
           birthPlace.name AS birthName,
           birthPlace.latitude AS birthLat,
           birthPlace.longitude AS birthLon,
           birthPlace.countryCode AS birthCountry,
           deathPlace.name AS deathName,
           deathPlace.latitude AS deathLat,
           deathPlace.longitude AS deathLon,
           deathPlace.countryCode AS deathCountry
    """

    result = session.run(query)
    migrations = list(result)

    print(f"Found {len(migrations)} people with complete birth/death location data")

# Analyze the data
print("\nAnalyzing migration patterns...")

# Group by country-to-country flows
country_flows = defaultdict(lambda: {"count": 0, "people": []})
city_flows = defaultdict(lambda: {"count": 0, "people": []})

# Track all unique locations
birth_locations = {}
death_locations = {}

for m in migrations:
    # Country-level aggregation
    flow_key = (m['birthCountry'], m['deathCountry'])
    country_flows[flow_key]["count"] += 1
    country_flows[flow_key]["people"].append(m['name'])

    # City-level for mapping
    birth_key = (m['birthName'], m['birthLat'], m['birthLon'], m['birthCountry'])
    death_key = (m['deathName'], m['deathLat'], m['deathLon'], m['deathCountry'])

    birth_locations[birth_key] = birth_locations.get(birth_key, 0) + 1
    death_locations[death_key] = death_locations.get(death_key, 0) + 1

    # City-to-city flow (for detailed view)
    city_key = (birth_key, death_key)
    city_flows[city_key]["count"] += 1
    city_flows[city_key]["people"].append(m['name'])

# Filter to interesting flows (cross-border only)
cross_border = {k: v for k, v in country_flows.items() if k[0] != k[1]}

print(f"\nStatistics:")
print(f"  Total migrations: {len(migrations)}")
print(f"  Unique birth locations: {len(birth_locations)}")
print(f"  Unique death locations: {len(death_locations)}")
print(f"  Cross-border flows: {len(cross_border)}")
print(f"  Domestic moves: {len(country_flows) - len(cross_border)}")

# Country name mapping
country_names = {
    'CA': 'Canada', 'US': 'United States', 'GB': 'United Kingdom',
    'CN': 'China', 'IN': 'India', 'JP': 'Japan', 'FR': 'France',
    'DE': 'Germany', 'IT': 'Italy', 'AU': 'Australia', 'NZ': 'New Zealand',
    'IE': 'Ireland', 'LK': 'Sri Lanka', 'PK': 'Pakistan', 'SG': 'Singapore',
    'HK': 'Hong Kong', 'TW': 'Taiwan', 'MY': 'Malaysia', 'TH': 'Thailand',
    'TR': 'Turkey', 'LB': 'Lebanon', 'NL': 'Netherlands', 'BE': 'Belgium',
    'CH': 'Switzerland', 'ES': 'Spain', 'PT': 'Portugal', 'MX': 'Mexico'
}

# Print top flows
print("\nTop 20 cross-border migration flows:")
sorted_flows = sorted(cross_border.items(), key=lambda x: x[1]["count"], reverse=True)
for i, ((src, dst), data) in enumerate(sorted_flows[:20], 1):
    src_name = country_names.get(src, src)
    dst_name = country_names.get(dst, dst)
    print(f"  {i:2d}. {src_name:20s} → {dst_name:20s}: {data['count']:3d} people")

# Create the visualization
print("\nCreating interactive map...")

fig = go.Figure()

# Add birth location markers
birth_lats = []
birth_lons = []
birth_texts = []
birth_sizes = []

for (name, lat, lon, country), count in birth_locations.items():
    birth_lats.append(lat)
    birth_lons.append(lon)
    country_name = country_names.get(country, country)
    birth_texts.append(f"{name}, {country_name}<br>{count} births")
    birth_sizes.append(min(count * 3 + 5, 30))  # Scale marker size

fig.add_trace(go.Scattergeo(
    lon=birth_lons,
    lat=birth_lats,
    text=birth_texts,
    mode='markers',
    name='Birth Places',
    marker=dict(
        size=birth_sizes,
        color='green',
        opacity=0.6,
        line=dict(width=0.5, color='white')
    ),
    hovertemplate='<b>Birth:</b> %{text}<extra></extra>'
))

# Add death location markers
death_lats = []
death_lons = []
death_texts = []
death_sizes = []

for (name, lat, lon, country), count in death_locations.items():
    death_lats.append(lat)
    death_lons.append(lon)
    country_name = country_names.get(country, country)
    death_texts.append(f"{name}, {country_name}<br>{count} deaths")
    death_sizes.append(min(count * 3 + 5, 30))

fig.add_trace(go.Scattergeo(
    lon=death_lons,
    lat=death_lats,
    text=death_texts,
    mode='markers',
    name='Death Places',
    marker=dict(
        size=death_sizes,
        color='red',
        opacity=0.6,
        line=dict(width=0.5, color='white')
    ),
    hovertemplate='<b>Death:</b> %{text}<extra></extra>'
))

# Function to add flow lines for a given threshold
def add_flow_lines(threshold):
    """Add migration flow lines for flows with count >= threshold"""
    significant_flows = [(k, v) for k, v in city_flows.items() if v["count"] >= threshold]
    traces = []

    for (birth_key, death_key), data in significant_flows:
        birth_name, birth_lat, birth_lon, birth_country = birth_key
        death_name, death_lat, death_lon, death_country = death_key

        # Skip if same location
        if birth_lat == death_lat and birth_lon == death_lon:
            continue

        count = data["count"]
        people_list = "<br>".join([f"  • {p}" for p in data["people"][:10]])
        if len(data["people"]) > 10:
            people_list += f"<br>  ... and {len(data['people']) - 10} more"

        birth_country_name = country_names.get(birth_country, birth_country)
        death_country_name = country_names.get(death_country, death_country)

        hover_text = (f"<b>{birth_name}, {birth_country_name}</b><br>"
                      f"→ <b>{death_name}, {death_country_name}</b><br>"
                      f"{count} people:<br>{people_list}")

        # Color based on destination region
        if death_country == 'CA':
            color = 'blue'
        elif death_country in ['CN', 'IN', 'JP', 'LK', 'PK', 'SG', 'HK', 'TW', 'MY', 'TH']:
            color = 'orange'
        elif death_country in ['GB', 'FR', 'DE', 'IT', 'IE', 'NL', 'BE', 'CH', 'ES', 'PT']:
            color = 'purple'
        elif death_country == 'US':
            color = 'red'
        else:
            color = 'gray'

        # Line width based on count
        width = min(count * 0.5 + 0.5, 5)

        traces.append(go.Scattergeo(
            lon=[birth_lon, death_lon],
            lat=[birth_lat, death_lat],
            mode='lines',
            line=dict(width=width, color=color),
            opacity=0.4,
            showlegend=False,
            hovertemplate=hover_text + '<extra></extra>'
        ))

    return traces, len(significant_flows)

# Create frames for different threshold values
thresholds = [1, 2, 3, 4, 5, 10, 15, 20, 25, 30, 40, 50]
frames = []

print(f"\nGenerating interactive frames for thresholds: {thresholds}")

for threshold in thresholds:
    flow_traces, flow_count = add_flow_lines(threshold)
    print(f"  Threshold {threshold:2d}: {flow_count:4d} flows")

    # Create frame data (markers + flows for this threshold)
    frame_data = [
        fig.data[0],  # Birth markers
        fig.data[1],  # Death markers
    ] + flow_traces

    frames.append(go.Frame(
        data=frame_data,
        name=str(threshold),
        layout=go.Layout(
            title_text=f'Historical Migration Patterns: Birth → Death Locations<br>'
                      f'<sub>Showing flows with {threshold}+ people ({flow_count} routes)</sub>'
        )
    ))

# Add initial flow lines (threshold=2)
initial_traces, initial_count = add_flow_lines(2)
print(f"\nAdding initial view: {initial_count} flows (threshold=2)")

for trace in initial_traces:
    fig.add_trace(trace)

# Add frames to figure
fig.frames = frames

# Create slider steps
slider_steps = []
for threshold in thresholds:
    slider_steps.append({
        'args': [
            [str(threshold)],
            {
                'frame': {'duration': 300, 'redraw': True},
                'mode': 'immediate',
                'transition': {'duration': 300}
            }
        ],
        'label': str(threshold),
        'method': 'animate'
    })

# Update layout with slider
fig.update_layout(
    title={
        'text': f'Historical Migration Patterns: Birth → Death Locations<br>'
                f'<sub>Showing flows with 2+ people ({initial_count} routes) - Use slider to adjust threshold</sub>',
        'x': 0.5,
        'xanchor': 'center'
    },
    showlegend=True,
    geo=dict(
        projection_type='natural earth',
        showland=True,
        landcolor='rgb(243, 243, 243)',
        coastlinecolor='rgb(204, 204, 204)',
        showocean=True,
        oceancolor='rgb(230, 245, 255)',
        showcountries=True,
        countrycolor='rgb(204, 204, 204)',
    ),
    height=850,
    width=1400,
    sliders=[{
        'active': 1,  # Start at threshold=2 (index 1 in thresholds list)
        'yanchor': 'top',
        'y': 0,
        'xanchor': 'left',
        'x': 0.1,
        'currentvalue': {
            'prefix': 'Minimum people per route: ',
            'visible': True,
            'xanchor': 'right'
        },
        'pad': {'b': 10, 't': 50},
        'len': 0.8,
        'transition': {'duration': 300},
        'steps': slider_steps
    }]
)

# Save to HTML
output_file = 'migration_visualization.html'
fig.write_html(output_file)

print(f"\n{'='*80}")
print(f"Visualization saved to: {output_file}")
print(f"Open this file in a web browser to explore the interactive map")
print(f"{'='*80}")

# Also create a summary statistics file
summary = {
    "total_migrations": len(migrations),
    "unique_birth_locations": len(birth_locations),
    "unique_death_locations": len(death_locations),
    "cross_border_flows": len(cross_border),
    "top_flows": [
        {
            "from": country_names.get(src, src),
            "to": country_names.get(dst, dst),
            "count": data["count"],
            "sample_people": data["people"][:5]
        }
        for (src, dst), data in sorted_flows[:20]
    ]
}

with open('migration_summary.json', 'w') as f:
    json.dump(summary, f, indent=2)

print(f"\nSummary statistics saved to: migration_summary.json")

# Print some interesting patterns
print("\n" + "="*80)
print("INTERESTING PATTERNS DISCOVERED")
print("="*80)

# Migrations to Canada
to_canada = {k: v for k, v in cross_border.items() if k[1] == 'CA'}
if to_canada:
    print("\nMigrations TO Canada:")
    sorted_to_ca = sorted(to_canada.items(), key=lambda x: x[1]["count"], reverse=True)
    for (src, _), data in sorted_to_ca[:10]:
        src_name = country_names.get(src, src)
        print(f"  {src_name:20s} → Canada: {data['count']:3d} people")

# Migrations from Canada
from_canada = {k: v for k, v in cross_border.items() if k[0] == 'CA'}
if from_canada:
    print("\nMigrations FROM Canada:")
    sorted_from_ca = sorted(from_canada.items(), key=lambda x: x[1]["count"], reverse=True)
    for (_, dst), data in sorted_from_ca[:10]:
        dst_name = country_names.get(dst, dst)
        print(f"  Canada → {dst_name:20s}: {data['count']:3d} people")

# Largest city hubs
print("\nTop birth places (emigration hubs):")
sorted_births = sorted(birth_locations.items(), key=lambda x: x[1], reverse=True)
for (name, lat, lon, country), count in sorted_births[:10]:
    country_name = country_names.get(country, country)
    print(f"  {name:30s}, {country_name:15s}: {count:3d} people")

print("\nTop death places (immigration destinations):")
sorted_deaths = sorted(death_locations.items(), key=lambda x: x[1], reverse=True)
for (name, lat, lon, country), count in sorted_deaths[:10]:
    country_name = country_names.get(country, country)
    print(f"  {name:30s}, {country_name:15s}: {count:3d} people")

driver.close()

print("\n" + "="*80)
print("COMPLETE! Open migration_visualization.html to explore the map")
print("="*80)
