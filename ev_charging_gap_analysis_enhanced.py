import pandas as pd
import geopandas as gpd
from pyproj import Transformer
from shapely.geometry import Point
import folium
from folium.plugins import MarkerCluster, HeatMap
from scipy.spatial import cKDTree
import numpy as np
import os
import warnings
import osmnx as ox
import networkx as nx
warnings.filterwarnings('ignore')

def load_data():
    ev_df = pd.read_csv('data/Electric_Vehicle_Charging_Points_Jan 2026.csv')
    hdb_df = pd.read_csv('data/HDBCarparkInformation.csv')
    return ev_df, hdb_df

def svy21_to_wgs84(x, y):
    transformer = Transformer.from_crs("EPSG:3414", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(x, y)
    return lon, lat

def preprocess_data(ev_df, hdb_df):
    ev_public = ev_df[ev_df['Is the charger publicly accessible?'] == 'Yes'].copy()
    ev_public = ev_public.drop_duplicates(subset=['longitude', 'latitude'])
    
    hdb_df[['longitude', 'latitude']] = hdb_df.apply(
        lambda row: pd.Series(svy21_to_wgs84(row['x_coord'], row['y_coord'])),
        axis=1
    )
    
    return ev_public, hdb_df

def create_geodataframes(ev_public, hdb_df):
    ev_gdf = gpd.GeoDataFrame(
        ev_public,
        geometry=gpd.points_from_xy(ev_public.longitude, ev_public.latitude),
        crs="EPSG:4326"
    )
    
    hdb_gdf = gpd.GeoDataFrame(
        hdb_df,
        geometry=gpd.points_from_xy(hdb_df.longitude, hdb_df.latitude),
        crs="EPSG:4326"
    )
    
    return ev_gdf, hdb_gdf

def calculate_nearest_distance(hdb_gdf, ev_gdf):
    ev_coords = np.array(list(zip(ev_gdf.geometry.x, ev_gdf.geometry.y)))
    hdb_coords = np.array(list(zip(hdb_gdf.geometry.x, hdb_gdf.geometry.y)))
    
    tree = cKDTree(ev_coords)
    distances, indices = tree.query(hdb_coords, k=1)
    
    hdb_gdf['nearest_charger_distance_m'] = distances * 111000
    hdb_gdf['nearest_charger_idx'] = indices
    
    return hdb_gdf

def load_singapore_road_network():
    print("Loading Singapore road network (this may take a few minutes)...")
    place_name = "Singapore, Singapore"
    G = ox.graph_from_place(place_name, network_type='drive')
    print("Road network loaded successfully!")
    return G

def calculate_road_distance_optimized(hdb_gdf, ev_gdf, G, max_euclidean_dist=3000, top_k_chargers=3, process_all=True):
    print("Calculating road distances (optimized)...")
    
    hdb_gdf['road_distance_m'] = np.nan
    hdb_gdf['nearest_charger_road_idx'] = np.nan
    hdb_gdf['road_path_coords'] = None
    
    if process_all:
        target_mask = pd.Series([True] * len(hdb_gdf), index=hdb_gdf.index)
        print(f"Processing ALL {len(hdb_gdf)} car parks...")
    else:
        target_mask = hdb_gdf['gap_category'].isin(['Moderate Gap', 'High Gap', 'Severe Gap'])
        target_hdb = hdb_gdf[target_mask].copy()
        print(f"Processing {len(target_hdb)} car parks (Moderate/High/Severe Gap)...")
    
    target_hdb = hdb_gdf[target_mask].copy()
    
    if len(target_hdb) == 0:
        print("No target areas found, skipping road distance calculation")
        return hdb_gdf
    
    ev_coords = np.array(list(zip(ev_gdf.geometry.y, ev_gdf.geometry.x)))
    tree = cKDTree(ev_coords)
    
    print("Optimization 1: Batch finding nearest nodes for all HDB car parks...")
    hdb_nodes = ox.nearest_nodes(G, target_hdb.geometry.x, target_hdb.geometry.y)
    hdb_node_dict = dict(zip(target_hdb.index, hdb_nodes))
    
    print("Optimization 2: Batch finding nearest nodes for all EV chargers...")
    ev_nodes = ox.nearest_nodes(G, ev_gdf.geometry.x, ev_gdf.geometry.y)
    
    print(f"Starting route calculations for {len(target_hdb)} car parks...")
    
    from tqdm import tqdm
    
    for idx, hdb_row in tqdm(target_hdb.iterrows(), total=len(target_hdb), desc="Calculating routes"):
        hdb_point = (hdb_row.geometry.y, hdb_row.geometry.x)
        
        euclidean_dist, nearest_indices = tree.query(hdb_point, k=top_k_chargers)
        
        valid_chargers = []
        for i, dist in zip(nearest_indices, euclidean_dist):
            if dist * 111000 <= max_euclidean_dist:
                valid_chargers.append(i)
        
        if not valid_chargers:
            valid_chargers = [nearest_indices[0]]
        
        try:
            orig_node = hdb_node_dict[idx]
            
            min_road_dist = float('inf')
            best_charger_idx = None
            best_path = None
            
            for charger_idx in valid_chargers:
                dest_node = ev_nodes[charger_idx]
                
                try:
                    path_nodes = nx.shortest_path(G, orig_node, dest_node, weight='length')
                    
                    road_dist = 0
                    for u, v in zip(path_nodes[:-1], path_nodes[1:]):
                        edge_data = G.get_edge_data(u, v, 0)
                        road_dist += edge_data.get('length', 0)
                    
                    if road_dist < min_road_dist:
                        min_road_dist = road_dist
                        best_charger_idx = charger_idx
                        
                        path_coords = []
                        for node in path_nodes:
                            path_coords.append((G.nodes[node]['y'], G.nodes[node]['x']))
                        best_path = path_coords
                except Exception as e:
                    continue
            
            if min_road_dist != float('inf') and min_road_dist > 0:
                hdb_gdf.at[idx, 'road_distance_m'] = round(min_road_dist, 1)
                hdb_gdf.at[idx, 'nearest_charger_road_idx'] = best_charger_idx
                hdb_gdf.at[idx, 'road_path_coords'] = best_path
                
        except Exception as e:
            continue
    
    calculated_count = hdb_gdf['road_distance_m'].notna().sum()
    print(f"Road distances calculated for {calculated_count} car parks")
    
    return hdb_gdf

def classify_gap_category(distance):
    if distance < 100:
        return 'Excellent'
    elif distance < 300:
        return 'Good'
    elif distance < 600:
        return 'Moderate Gap'
    elif distance < 1000:
        return 'High Gap'
    else:
        return 'Severe Gap'

def get_gap_color(category):
    colors = {
        'Excellent': '#43A047',
        'Good': '#7CB342',
        'Moderate Gap': '#FDD835',
        'High Gap': '#FB8C00',
        'Severe Gap': '#E53935'
    }
    return colors.get(category, '#9E9E9E')

def generate_planning_areas():
    print("Creating grid-based planning areas...")
    from shapely.geometry import Polygon
    
    min_lon, max_lon = 103.6, 104.0
    min_lat, max_lat = 1.2, 1.5
    n_cols, n_rows = 5, 5
    
    lon_step = (max_lon - min_lon) / n_cols
    lat_step = (max_lat - min_lat) / n_rows
    
    polygons = []
    names = []
    for i in range(n_cols):
        for j in range(n_rows):
            lon1 = min_lon + i * lon_step
            lon2 = min_lon + (i + 1) * lon_step
            lat1 = min_lat + j * lat_step
            lat2 = min_lat + (j + 1) * lat_step
            polygons.append(Polygon([(lon1, lat1), (lon2, lat1), (lon2, lat2), (lon1, lat2)]))
            names.append(f"Zone {i*n_rows + j + 1}")
    
    planning_areas = gpd.GeoDataFrame({'name': names, 'geometry': polygons}, crs='EPSG:4326')
    
    return planning_areas

def spatial_aggregate(hdb_gdf, ev_gdf, planning_areas):
    if planning_areas is None:
        print("Planning areas not available, skipping spatial aggregation")
        return None
    
    hdb_with_area = gpd.sjoin(hdb_gdf, planning_areas, how='left', predicate='within')
    hdb_with_area = hdb_with_area.rename(columns={'name': 'area_name'})
    ev_with_area = gpd.sjoin(ev_gdf, planning_areas, how='left', predicate='within')
    ev_with_area = ev_with_area.rename(columns={'name': 'area_name'})
    
    area_stats = hdb_with_area.groupby('area_name').agg({
        'car_park_no': 'count',
        'nearest_charger_distance_m': ['mean', 'median']
    }).round(2)
    
    area_stats.columns = ['total_carparks', 'avg_distance_m', 'median_distance_m']
    
    ev_count = ev_with_area.groupby('area_name').size().rename('charger_count')
    area_stats = area_stats.join(ev_count, how='left').fillna(0)
    
    gap_counts = hdb_with_area.groupby(['area_name', 'gap_category']).size().unstack(fill_value=0)
    area_stats = area_stats.join(gap_counts, how='left')
    
    for cat in ['Excellent', 'Good', 'Moderate Gap', 'High Gap', 'Severe Gap']:
        if cat not in area_stats.columns:
            area_stats[cat] = 0
    
    area_stats['high_gap_rate'] = (area_stats['High Gap'] + area_stats['Severe Gap']) / area_stats['total_carparks']
    
    return hdb_with_area, area_stats.sort_values('high_gap_rate', ascending=False)

def calculate_priority_scores(hdb_gdf, area_stats):
    hdb_gdf['priority_score'] = 0.0
    
    dist_norm = hdb_gdf['nearest_charger_distance_m'] / hdb_gdf['nearest_charger_distance_m'].max()
    hdb_gdf['priority_score'] += dist_norm * 40
    
    if area_stats is not None and 'area_name' in hdb_gdf.columns:
        area_rate = area_stats['high_gap_rate'].to_dict()
        hdb_gdf['area_gap_rate'] = hdb_gdf['area_name'].map(area_rate).fillna(0)
        hdb_gdf['priority_score'] += hdb_gdf['area_gap_rate'] * 30
    
    if 'car_park_decks' in hdb_gdf.columns:
        size_norm = hdb_gdf['car_park_decks'] / hdb_gdf['car_park_decks'].max()
        hdb_gdf['priority_score'] += size_norm * 30
    
    hdb_gdf['priority_score'] = hdb_gdf['priority_score'].round(2)
    
    return hdb_gdf

def create_enhanced_map(ev_gdf, hdb_gdf, planning_areas, area_stats):
    center_lat = 1.3521
    center_lon = 103.8198
    m = folium.Map(location=[center_lat, center_lon], zoom_start=12)

    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri',
        name='Satellite View'
    ).add_to(m)

    folium.TileLayer(
        tiles='CartoDB positron',
        attr='CartoDB',
        name='Light Map'
    ).add_to(m)
    
    ev_layer = folium.FeatureGroup(name='EV Chargers (Public)')
    marker_cluster = MarkerCluster()
    
    for idx, row in ev_gdf.iterrows():
        popup_text = f"""
        <strong>Operator:</strong> {row['operator']}<br>
        <strong>Charging Speed:</strong> {row['chargingSpeed']} kW<br>
        <strong>Plug Type:</strong> {row['plugType']}<br>
        <strong>Location:</strong> {row['Building Name'] if pd.notna(row['Building Name']) else row['Street Name']}
        """
        folium.CircleMarker(
            location=[row.latitude, row.longitude],
            radius=6,
            color='#1E88E5',
            fill=True,
            fill_color='#1E88E5',
            fill_opacity=0.8,
            popup=folium.Popup(popup_text, max_width=300)
        ).add_to(marker_cluster)
    
    marker_cluster.add_to(ev_layer)
    ev_layer.add_to(m)
    
    categories = {
        'Excellent': {'color': '#43A047', 'label': 'Excellent (<200m)', 'show': False},
        'Good': {'color': '#7CB342', 'label': 'Good (200-500m)', 'show': False},
        'Moderate Gap': {'color': '#FDD835', 'label': 'Moderate Gap (500-1000m)', 'show': True},
        'High Gap': {'color': '#FB8C00', 'label': 'High Gap (1000-2000m)', 'show': True},
        'Severe Gap': {'color': '#E53935', 'label': 'Severe Gap (>2000m)', 'show': True}
    }
    
    for cat, props in categories.items():
        layer = folium.FeatureGroup(name=props['label'], show=props['show'])
        cat_data = hdb_gdf[hdb_gdf['gap_category'] == cat]
        
        for idx, row in cat_data.iterrows():
            dist_text = f"{row['nearest_charger_distance_m']:.1f} m (straight line)"
            if pd.notna(row.get('road_distance_m')):
                dist_text = f"{row['nearest_charger_distance_m']:.1f} m<br><strong>Road:</strong> {row['road_distance_m']:.1f} m"
            
            popup_text = f"""
            <strong>Car Park:</strong> {row['car_park_no']}<br>
            <strong>Address:</strong> {row['address']}<br>
            <strong>Distance:</strong> {dist_text}<br>
            <strong>Category:</strong> {row['gap_category']}<br>
            <strong>Priority Score:</strong> {row.get('priority_score', 'N/A')}
            """
            folium.CircleMarker(
                location=[row.latitude, row.longitude],
                radius=6,
                color=props['color'],
                fill=True,
                fill_color=props['color'],
                fill_opacity=0.8,
                popup=folium.Popup(popup_text, max_width=300)
            ).add_to(layer)
        
        layer.add_to(m)
    
    road_path_layer = folium.FeatureGroup(name='Road Paths (All Categories)', show=True)
    
    path_colors = {
        'Excellent': '#43A047',
        'Good': '#7CB342',
        'Moderate Gap': '#FDD835',
        'High Gap': '#FB8C00',
        'Severe Gap': '#E53935'
    }
    
    for idx, row in hdb_gdf.iterrows():
        path_coords = row.get('road_path_coords')
        
        if path_coords is not None:
            if isinstance(path_coords, str):
                import ast
                try:
                    path_coords = ast.literal_eval(path_coords)
                except:
                    continue
            
            if isinstance(path_coords, list) and len(path_coords) > 1:
                color = path_colors.get(row['gap_category'], '#9E9E9E')
                
                dist_text = f"{row['nearest_charger_distance_m']:.1f} m"
                if pd.notna(row.get('road_distance_m')):
                    dist_text = f"Euclidean: {row['nearest_charger_distance_m']:.1f} m<br>Road: {row['road_distance_m']:.1f} m"
                
                popup_text = f"""
                <strong>Car Park:</strong> {row['car_park_no']}<br>
                <strong>Category:</strong> {row['gap_category']}<br>
                <strong>{dist_text}</strong>
                """
                
                folium.PolyLine(
                    locations=path_coords,
                    color=color,
                    weight=4,
                    opacity=0.8,
                    popup=folium.Popup(popup_text, max_width=300)
                ).add_to(road_path_layer)
    
    road_path_layer.add_to(m)
    
    priority_layer = folium.FeatureGroup(name='Top Priority Areas', show=False)
    top_priority = hdb_gdf.nlargest(50, 'priority_score')
    
    for idx, row in top_priority.iterrows():
        radius = 8 + (row['priority_score'] / 100) * 12
        dist_text = f"{row['nearest_charger_distance_m']:.1f} m"
        if pd.notna(row.get('road_distance_m')):
            dist_text = f"Road: {row['road_distance_m']:.1f} m"
        
        popup_text = f"""
        <strong>Priority Rank:</strong> #{idx + 1}<br>
        <strong>Car Park:</strong> {row['car_park_no']}<br>
        <strong>Priority Score:</strong> {row['priority_score']}<br>
        <strong>Distance:</strong> {dist_text}
        """
        folium.Circle(
            location=[row.latitude, row.longitude],
            radius=radius * 5,
            color='#FF6F00',
            fill=True,
            fill_color='#FF6F00',
            fill_opacity=0.3,
            popup=folium.Popup(popup_text, max_width=300)
        ).add_to(priority_layer)
    
    priority_layer.add_to(m)
    
    heat_layer = folium.FeatureGroup(name='Charger Density Heatmap', show=False)
    heat_data = [[row.latitude, row.longitude] for idx, row in ev_gdf.iterrows()]
    HeatMap(heat_data, radius=15, blur=10).add_to(heat_layer)
    heat_layer.add_to(m)
    
    folium.LayerControl().add_to(m)
    
    legend_html = '''
    <div style="position: fixed; 
                bottom: 50px; left: 50px; width: 220px; height: 230px; 
                background-color: white; border:2px solid grey; z-index:9999; 
                font-size:13px; padding: 10px; border-radius: 5px;">
    <p style="margin: 0; font-weight: bold;">Legend</p>
    <p style="margin: 5px 0;"><span style="color: #1E88E5; font-weight: bold;">●</span> EV Charger</p>
    <p style="margin: 5px 0;"><span style="color: #43A047; font-weight: bold;">●</span> Excellent</p>
    <p style="margin: 5px 0;"><span style="color: #7CB342; font-weight: bold;">●</span> Good</p>
    <p style="margin: 5px 0;"><span style="color: #FDD835; font-weight: bold;">●</span> Moderate</p>
    <p style="margin: 5px 0;"><span style="color: #FB8C00; font-weight: bold;">●</span> High</p>
    <p style="margin: 5px 0;"><span style="color: #E53935; font-weight: bold;">●</span> Severe</p>
    <p style="margin: 8px 0 0 0; font-size: 11px; color: #666;">Lines = Road Paths</p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    
    return m

def generate_summary_statistics(hdb_gdf, ev_gdf, area_stats):
    print("\n" + "="*70)
    print("ENHANCED EV CHARGING GAP ANALYSIS SUMMARY")
    print("="*70)
    
    print(f"\nTotal HDB Car Parks: {len(hdb_gdf)}")
    print(f"Total Public EV Chargers: {len(ev_gdf)}")
    
    category_counts = hdb_gdf['gap_category'].value_counts().sort_index()
    print("\nGap Category Distribution:")
    for cat, count in category_counts.items():
        pct = (count / len(hdb_gdf)) * 100
        print(f"  {cat}: {count} ({pct:.1f}%)")
    
    print(f"\nAverage Euclidean Distance: {hdb_gdf['nearest_charger_distance_m'].mean():.1f} meters")
    print(f"Median Euclidean Distance: {hdb_gdf['nearest_charger_distance_m'].median():.1f} meters")
    
    if 'road_distance_m' in hdb_gdf.columns:
        road_count = hdb_gdf['road_distance_m'].notna().sum()
        if road_count > 0:
            print(f"\nRoad Distance Statistics (for {road_count} high-gap car parks):")
            print(f"  Average Road Distance: {hdb_gdf['road_distance_m'].mean():.1f} meters")
            print(f"  Median Road Distance: {hdb_gdf['road_distance_m'].median():.1f} meters")
            print(f"  Max Road Distance: {hdb_gdf['road_distance_m'].max():.1f} meters")
    
    if area_stats is not None:
        print(f"\nTop 5 Areas by High Gap Rate:")
        top_areas = area_stats.head(5)
        for area_name, row in top_areas.iterrows():
            print(f"  {area_name}: {row['high_gap_rate']*100:.1f}%")
    
    if 'priority_score' in hdb_gdf.columns:
        print(f"\nTop Priority Car Park: {hdb_gdf.nlargest(1, 'priority_score')['car_park_no'].values[0]}")
        print(f"  Priority Score: {hdb_gdf['priority_score'].max():.2f}")
    
    print("="*70 + "\n")

def export_results(hdb_gdf, ev_gdf, area_stats):
    output_df = hdb_gdf.copy()
    output_df = output_df.drop(columns=['geometry'], errors='ignore')
    output_df.to_csv('data/HDB_Carpark_Charging_Gap_Analysis_Enhanced.csv', index=False)
    print("Enhanced results exported to: data/HDB_Carpark_Charging_Gap_Analysis_Enhanced.csv")
    
    hdb_gdf.to_file('outputs/reports/hdb_carparks.geojson', driver='GeoJSON')
    ev_gdf.to_file('outputs/reports/ev_chargers.geojson', driver='GeoJSON')
    print("GeoJSON files exported to: outputs/reports/")
    
    if area_stats is not None:
        area_stats.to_excel('outputs/reports/area_statistics.xlsx')
        print("Area statistics exported to: outputs/reports/area_statistics.xlsx")

def main():
    print("="*70)
    print("ENHANCED EV CHARGING GAP ANALYSIS")
    print("="*70)
    
    print("\n[1/9] Loading data...")
    ev_df, hdb_df = load_data()
    
    print("[2/9] Preprocessing data...")
    ev_public, hdb_df = preprocess_data(ev_df, hdb_df)
    
    print("[3/9] Creating GeoDataFrames...")
    ev_gdf, hdb_gdf = create_geodataframes(ev_public, hdb_df)
    
    print("[4/9] Calculating nearest distances...")
    hdb_gdf = calculate_nearest_distance(hdb_gdf, ev_gdf)
    
    print("[5/9] Classifying gap categories...")
    hdb_gdf['gap_category'] = hdb_gdf['nearest_charger_distance_m'].apply(classify_gap_category)
    
    print("[6/9] Generating planning areas...")
    planning_areas = generate_planning_areas()
    
    print("[7/9] Spatial aggregation...")
    hdb_gdf, area_stats = spatial_aggregate(hdb_gdf, ev_gdf, planning_areas)
    
    print("[8/9] Calculating priority scores...")
    hdb_gdf = calculate_priority_scores(hdb_gdf, area_stats)
    
    print("[9/9] Calculating road distances (optimized)...")
    try:
        G = load_singapore_road_network()
        hdb_gdf = calculate_road_distance_optimized(hdb_gdf, ev_gdf, G, process_all=True)
    except Exception as e:
        print(f"Warning: Could not calculate road distances: {e}")
        print("Continuing with Euclidean distances only...")
    
    generate_summary_statistics(hdb_gdf, ev_gdf, area_stats)
    
    print("Creating enhanced interactive map...")
    m = create_enhanced_map(ev_gdf, hdb_gdf, planning_areas, area_stats)
    
    map_path = 'outputs/ev_charging_gap_map_enhanced.html'
    m.save(map_path)
    print(f"Enhanced map saved to: {map_path}")
    
    print("Exporting results...")
    export_results(hdb_gdf, ev_gdf, area_stats)
    
    print("\n" + "="*70)
    print("ANALYSIS COMPLETE!")
    print("="*70)

if __name__ == "__main__":
    main()
