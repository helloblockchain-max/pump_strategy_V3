"""
update_data.py - Runs on GitHub Actions every 6 hours
=====================================================
1. Fetches Pump.fun daily revenue from DefiLlama API
2. Fetches Pump token daily prices from CoinGecko API
3. Merges and exports as data.json for the frontend
"""

import requests
import csv
import json
import os
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
}

def fetch_and_export():
    print("=== Pump Strategy Auto-Updater ===")
    print(f"Running at: {datetime.utcnow().isoformat()}Z")
    
    # --- 1. Fetch Revenue (Protocol Revenue: used for PUMP buybacks) ---
    print("Fetching Pump protocol revenue from DefiLlama (buyback-eligible income)...")
    res_revenue = requests.get(
        'https://api.llama.fi/summary/fees/Pump?dataType=dailyRevenue',
        headers=HEADERS,
        timeout=30
    )
    if res_revenue.status_code != 200:
        print(f"WARN: Revenue fetch failed ({res_revenue.status_code}), using existing data")
        return False
    
    revenue_data = res_revenue.json().get('totalDataChart', [])
    revenue_by_date = {}
    for ts, rev in revenue_data:
        d = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d')
        revenue_by_date[d] = rev
    print(f"  Fetched {len(revenue_by_date)} days of revenue")
    
    # --- 2. Fetch Price ---
    print("Fetching Pump token prices from CoinGecko...")
    res_price = requests.get(
        'https://api.coingecko.com/api/v3/coins/pump-fun/market_chart?vs_currency=usd&days=365',
        headers=HEADERS,
        timeout=30
    )
    if res_price.status_code != 200:
        print(f"WARN: Price fetch failed ({res_price.status_code}), using existing data")
        return False
    
    price_data = res_price.json().get('prices', [])
    price_by_date = {}
    for ts_ms, price in price_data:
        d = datetime.utcfromtimestamp(ts_ms / 1000).strftime('%Y-%m-%d')
        price_by_date[d] = price
    print(f"  Fetched {len(price_by_date)} days of price data")
    
    # --- 3. Merge ---
    all_dates = sorted(set(price_by_date.keys()) & set(revenue_by_date.keys()))
    
    raw_data = []
    for d in all_dates:
        raw_data.append({
            'date': d,
            'price': price_by_date[d],
            'revenue': revenue_by_date[d]
        })
    
    print(f"  Merged: {len(raw_data)} rows")
    if len(raw_data) == 0:
        print("ERROR: No merged data, aborting")
        return False
    
    print(f"  Date range: {raw_data[0]['date']} ~ {raw_data[-1]['date']}")
    
    # --- 4. Export ---
    payload = {
        'last_updated': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S') + ' UTC',
        'raw_data': raw_data
    }
    
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    
    print(f"  Exported to {out_path}")
    return True

if __name__ == "__main__":
    success = fetch_and_export()
    if success:
        print("✅ Data update successful!")
    else:
        print("⚠️ Data update had issues, check logs above")
