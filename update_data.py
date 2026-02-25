"""
update_data.py - Runs on GitHub Actions every hour
===================================================
1. Fetches Pump.fun daily revenue from DefiLlama API
2. Fetches Pump token daily prices from CoinGecko API
3. Merges and exports as data.json for the frontend
"""

import requests
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
}

def fetch_with_retry(url, headers, timeout=30, retries=3, delay=5):
    """带重试的 HTTP GET 请求"""
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r
            elif r.status_code == 429:
                wait = delay * (attempt + 1) * 2  # 指数退避
                print(f"    Rate limited (429), waiting {wait}s before retry...")
                time.sleep(wait)
            else:
                print(f"    HTTP {r.status_code}, attempt {attempt+1}/{retries}")
                time.sleep(delay)
        except Exception as e:
            print(f"    Error: {e}, attempt {attempt+1}/{retries}")
            time.sleep(delay)
    return None

def fetch_and_export():
    print("=== Pump Strategy Auto-Updater ===")
    now = datetime.now(timezone.utc)
    print(f"Running at: {now.isoformat()}")
    
    # --- 1. Fetch Revenue (Protocol Revenue: used for PUMP buybacks) ---
    print("Fetching Pump protocol revenue from DefiLlama (buyback-eligible income)...")
    
    # Try multiple endpoints with fallback
    endpoints = [
        ('Pump (parent)', 'https://api.llama.fi/summary/fees/Pump?dataType=dailyRevenue'),
        ('pump (slug)',   'https://api.llama.fi/summary/fees/pump?dataType=dailyRevenue'),
    ]
    
    res_revenue = None
    for name, url in endpoints:
        r = fetch_with_retry(url, HEADERS)
        if r is not None:
            res_revenue = r
            print(f"  ✓ Success via {name}")
            break
        else:
            print(f"  ✗ {name} failed after retries, trying next...")
    
    # Fallback: merge sub-protocols individually
    if res_revenue is None:
        print("  Trying fallback: merging pump.fun + PumpSwap + Padre sub-protocols...")
        sub_protocols = ['pump.fun', 'PumpSwap', 'Padre']
        merged = {}
        for sp in sub_protocols:
            r = fetch_with_retry(f'https://api.llama.fi/summary/fees/{sp}?dataType=dailyRevenue', HEADERS)
            if r is not None:
                for ts, rev in r.json().get('totalDataChart', []):
                    d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d')
                    merged[d] = merged.get(d, 0) + rev
                print(f"    ✓ {sp}: OK")
            else:
                print(f"    ✗ {sp}: failed after retries")
        if merged:
            revenue_by_date = merged
            print(f"  Merged {len(revenue_by_date)} days from sub-protocols")
        else:
            print("WARN: All revenue endpoints failed, using existing data")
            return False
    else:
        revenue_data = res_revenue.json().get('totalDataChart', [])
        revenue_by_date = {}
        for ts, rev in revenue_data:
            d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d')
            revenue_by_date[d] = rev
    print(f"  Fetched {len(revenue_by_date)} days of revenue")
    
    # --- 2. Fetch Price ---
    print("Fetching Pump token prices from CoinGecko...")
    price_url = 'https://api.coingecko.com/api/v3/coins/pump-fun/market_chart?vs_currency=usd&days=3'
    res_price = fetch_with_retry(price_url, HEADERS, retries=5, delay=15)
    
    price_by_date = {}
    if res_price is None:
        print(f"  WARN: Price fetch failed after all retries, will use existing data")
    else:
        price_data = res_price.json().get('prices', [])
        for ts_ms, price in price_data:
            d = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
            price_by_date[d] = price
        print(f"  Fetched {len(price_by_date)} days of price data")
    
    # --- 3. Merge ---
    # Load existing data.json to keep historical data
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.json')
    data_dict = {}
    if os.path.exists(out_path):
        try:
            with open(out_path, 'r', encoding='utf-8') as f:
                old_payload = json.load(f)
                for row in old_payload.get('raw_data', []):
                    if 'date' in row:
                        data_dict[row['date']] = row
            print(f"  Loaded {len(data_dict)} existing days from data.json")
        except Exception as e:
            print(f"  Could not load existing data: {e}")

    # Update with new data: use all price dates, fill missing revenue with 0
    if price_by_date:
        all_dates = sorted(price_by_date.keys())
        for d in all_dates:
            data_dict[d] = {
                'date': d,
                'price': price_by_date[d],
                'revenue': revenue_by_date.get(d, data_dict.get(d, {}).get('revenue', 0))
            }
    else:
        # No new price data, just update revenue for existing dates
        for d in data_dict:
            if d in revenue_by_date:
                data_dict[d]['revenue'] = revenue_by_date[d]
    
    raw_data = [data_dict[k] for k in sorted(data_dict.keys())]
    
    print(f"  Merged update: total {len(raw_data)} rows now")
    if len(raw_data) == 0:
        print("ERROR: No merged data, aborting")
        return False
    
    print(f"  Date range: {raw_data[0]['date']} ~ {raw_data[-1]['date']}")
    
    # --- 4. Export ---
    payload = {
        'last_updated': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S') + ' UTC',
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
        print("❌ Data update FAILED, check logs above")
        sys.exit(1)  # 非零退出码让 GitHub Actions 正确标记为失败
