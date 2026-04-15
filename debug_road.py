import pandas as pd
import geopandas as gpd
from pyproj import Transformer
from shapely.geometry import Point
import folium
from folium.plugins import MarkerCluster, HeatMap
from scipy.spatial import cKDTree
import numpy as np
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

def main():
    print("="*70)
    print("DEBUG: EV CHARGING GAP ANALYSIS")
    print("="*70)
    
    print("\n[1/5] Loading data...")
    ev_df, hdb_df = load_data()
    print(f"  - EV chargers: {len(ev_df)}")
    print(f"  - HDB car parks: {len(hdb_df)}")
    
    print("\n[2/5] Preprocessing data...")
    ev_public, hdb_df = preprocess_data(ev_df, hdb_df)
    print(f"  - Public EV chargers: {len(ev_public)}")
    
    print("\n[3/5] Creating GeoDataFrames...")
    ev_gdf, hdb_gdf = create_geodataframes(ev_public, hdb_df)
    
    print("\n[4/5] Calculating nearest distances...")
    hdb_gdf = calculate_nearest_distance(hdb_gdf, ev_gdf)
    
    print("\n[5/5] Classifying gap categories...")
    hdb_gdf['gap_category'] = hdb_gdf['nearest_charger_distance_m'].apply(classify_gap_category)
    
    print("\n" + "="*70)
    print("GAP CATEGORY DISTRIBUTION")
    print("="*70)
    category_counts = hdb_gdf['gap_category'].value_counts().sort_index()
    for cat, count in category_counts.items():
        pct = (count / len(hdb_gdf)) * 100
        print(f"  {cat}: {count} ({pct:.1f}%)")
    
    print("\n" + "="*70)
    print("DEBUG: LOADING ROAD NETWORK")
    print("="*70)
    try:
        print("Loading Singapore road network (this may take a few minutes)...")
        place_name = "Singapore, Singapore"
        G = ox.graph_from_place(place_name, network_type='drive')
        print(f"Road network loaded successfully!")
        print(f"  - Number of nodes: {G.number_of_nodes()}")
        print(f"  - Number of edges: {G.number_of_edges()}")
    except Exception as e:
        print(f"ERROR loading road network: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n" + "="*70)
    print("DEBUG: TESTING ROUTE CALCULATION")
    print("="*70)
    
    target_cats = ['Moderate Gap', 'High Gap', 'Severe Gap']
    test_hdb = hdb_gdf[hdb_gdf['gap_category'].isin(target_cats)].head(3)
    
    if len(test_hdb) == 0:
        print("No test car parks found in target categories")
        return
    
    print(f"Testing with {len(test_hdb)} car parks...")
    
    for idx, hdb_row in test_hdb.iterrows():
        print(f"\n--- Car Park {hdb_row['car_park_no']} ---")
        print(f"  Category: {hdb_row['gap_category']}")
        print(f"  Distance: {hdb_row['nearest_charger_distance_m']:.1f}m")
        print(f"  Location: {hdb_row.geometry.y:.6f}, {hdb_row.geometry.x:.6f}")
        
        charger_idx = hdb_row['nearest_charger_idx']
        charger_row = ev_gdf.iloc[charger_idx]
        print(f"  Nearest charger: {charger_row.geometry.y:.6f}, {charger_row.geometry.x:.6f}")
        
        try:
            orig_node = ox.nearest_nodes(G, hdb_row.geometry.x, hdb_row.geometry.y)
            dest_node = ox.nearest_nodes(G, charger_row.geometry.x, charger_row.geometry.y)
            print(f"  Orig node: {orig_node}")
            print(f"  Dest node: {dest_node}")
            
            try:
                path_nodes = nx.shortest_path(G, orig_node, dest_node, weight='length')
                print(f"  Path nodes: {len(path_nodes)}")
                
                edge_lengths = ox.utils_graph.get_route_edge_attributes(G, path_nodes, 'length')
                road_dist = sum(edge_lengths)
                print(f"  Road distance: {road_dist:.1f}m")
                
                path_coords = []
                for node in path_nodes:
                    path_coords.append((G.nodes[node]['y'], G.nodes[node]['x']))
                print(f"  Path coords: {len(path_coords)} points")
                print(f"  SUCCESS! Route calculated")
                
            except Exception as e:
                print(f"  ERROR calculating shortest path: {e}")
                import traceback
                traceback.print_exc()
                
        except Exception as e:
            print(f"  ERROR finding nearest nodes: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*70)
    print("DEBUG COMPLETE")
    print("="*70)

if __name__ == "__main__":
    main()
