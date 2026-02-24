import os
import sys
import json

sys.path.append(r'd:\AI')
import backtest

def generate_json():
    filepath = r'd:\AI\pump_data.csv'
    
    print("Loading data for export...")
    data = backtest.load_csv_data(filepath)

    # Prepare standard JSON payload
    payload = {
        'last_updated': data[-1]['date'].strftime('%Y-%m-%d %H:%M:%S'),
        'raw_data': [
            {
                'date': d['date'].strftime('%Y-%m-%d'),
                'price': d['close'],
                'revenue': d['income']
            } for d in data
        ]
    }

    # Write to the root folder directly
    output_dir = r'd:\AI\pump_strategy'
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    out_path = os.path.join(output_dir, 'data.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        
    print(f"Exported data payload to {out_path}")

if __name__ == "__main__":
    generate_json()
