import geopandas as gpd
import pandas as pd

hdb = gpd.read_file('outputs/reports/hdb_carparks.geojson')
ev = gpd.read_file('outputs/reports/ev_chargers.geojson')

print('=== 基本统计 ===')
print(f'HDB停车场总数: {len(hdb)}')
print(f'公共充电桩总数: {len(ev)}')

print('\n=== 差距分类统计 ===')
gap_counts = hdb['gap_category'].value_counts()
for cat, count in gap_counts.items():
    pct = count/len(hdb)*100
    print(f'{cat}: {count} ({pct:.1f}%)')

print('\n=== 距离统计 ===')
print(f'平均距离: {hdb["nearest_charger_distance_m"].mean():.1f} 米')
print(f'中位距离: {hdb["nearest_charger_distance_m"].median():.1f} 米')

print('\n=== 高差距区域 ===')
high_gap = hdb[hdb['gap_category'].isin(['High Gap', 'Severe Gap', 'Moderate Gap'])]
print(f'Moderate及以上差距停车场: {len(high_gap)} ({len(high_gap)/len(hdb)*100:.1f}%)')

print('\n=== Top 10 高优先级停车场 ===')
top10 = hdb.nlargest(10, 'priority_score')[['car_park_no', 'address', 'priority_score']]
for i, row in top10.iterrows():
    print(f"  {row['address'][:60]}... (评分: {row['priority_score']})")
