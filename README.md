# EV Charging Gap Analysis

Analysis of electric vehicle charging infrastructure gaps in Singapore HDB car parks.

## Project Overview

This project identifies areas with insufficient EV charging facilities and provides prioritized recommendations for infrastructure expansion across Singapore's public housing estates.

## Project Structure

```
GIS/
├── data/                  # Source data files
│   ├── HDB_Carpark_Charging_Gap_Analysis.csv
│   ├── HDBCarparkInformation.csv
│   └── Electric_Vehicle_Charging_Points_Jan 2026.csv
├── Image/                 # Generated visualization images
├── quick_stats.py         # Quick data statistics
├── ev_charging_gap_analysis_enhanced.py  # Main analysis script
└── requirements.txt       # Python dependencies
```

## Setup

1. Create and activate virtual environment:
```bash
python -m venv .venv
.venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

Run the main analysis:
```bash
python ev_charging_gap_analysis_enhanced.py
```

Generate quick statistics:
```bash
python quick_stats.py
```

## Requirements

See `requirements.txt` for full dependency list. Core libraries:
- geopandas
- folium
- matplotlib
- pandas
- seaborn
