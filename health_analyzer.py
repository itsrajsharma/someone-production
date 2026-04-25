import argparse
import pandas as pd
import json
import os
from sklearn.ensemble import IsolationForest

def analyze_week(csv_path):
    df = pd.read_csv(csv_path)
    features = ['sleep_hours', 'stress_level', 'energy_level', 'mood_score', 'steps']
    
    # Fill any missing values with median
    for f in features:
        if df[f].isnull().any():
            df[f] = df[f].fillna(df[f].median())
    
    # Isolation Forest for anomalies
    clf = IsolationForest(contamination=0.15, random_state=42)
    df['anomaly'] = clf.fit_predict(df[features])
    
    avg_sleep = df['sleep_hours'].mean()
    avg_stress = df['stress_level'].mean()
    
    # Weekly Trend
    if len(df) >= 4:
        first_half = df['stress_level'].iloc[:len(df)//2].mean()
        second_half = df['stress_level'].iloc[len(df)//2:].mean()
        if second_half < first_half - 0.3:
            trend = "improving"
        elif second_half > first_half + 0.3:
            trend = "declining"
        else:
            trend = "stable"
    else:
        trend = "stable"
        
    # Extract anomalies
    anomaly_days = df[df['anomaly'] == -1]
    anomalies = []
    for _, row in anomaly_days.iterrows():
        reasons = []
        if row['sleep_hours'] < avg_sleep - 1.0:
            reasons.append("short sleep")
        if row['stress_level'] > avg_stress + 1.0:
            reasons.append("high stress")
        if row['energy_level'] < df['energy_level'].mean() - 1.0:
            reasons.append("low energy")
        if not reasons:
            reasons.append("unusual metrics")
            
        anomalies.append({
            "day": str(row['date']),
            "reason": ", ".join(reasons)
        })
        
    return {
        "avg_sleep": round(float(avg_sleep), 1),
        "avg_stress": round(float(avg_stress), 1),
        "trend": trend,
        "anomalies": anomalies,
        "sleep": df['sleep_hours'].astype(float).tolist(),
        "stress": df['stress_level'].astype(float).tolist(),
        "energy": df['energy_level'].astype(float).tolist(),
        "anomaly_indices": df.index[df['anomaly'] == -1].tolist()
    }

def analyze_month(data_dir):
    csv_files = [os.path.join(data_dir, f) for f in os.listdir(data_dir) 
                 if f.endswith('.csv') and 'week' in f.lower()]
    
    if not csv_files:
        return None
        
    week_stats = {}
    for f in sorted(csv_files):
        week_name = os.path.basename(f).replace('.csv', '')
        try:
            week_stats[week_name] = analyze_week(f)
        except Exception:
            pass
            
    if not week_stats:
        return None
        
    def score(stats):
        return stats['avg_stress'] - stats['avg_sleep']
        
    sorted_weeks = sorted(week_stats.items(), key=lambda x: score(x[1]))
    best_week = sorted_weeks[0][0]
    worst_week = sorted_weeks[-1][0]
    
    chron_weeks = sorted(week_stats.keys())
    if len(chron_weeks) >= 2:
        first = week_stats[chron_weeks[0]]
        last = week_stats[chron_weeks[-1]]
        if last['avg_stress'] < first['avg_stress']:
            overall = "stress improving"
        elif last['avg_stress'] > first['avg_stress']:
            overall = "stress worsening"
        else:
            overall = "relatively stable"
    else:
        overall = "insufficient history"
        
    latest_week = week_stats[chron_weeks[-1]]
    
    return {
        "week_summary": {
            "avg_sleep": latest_week['avg_sleep'],
            "avg_stress": latest_week['avg_stress'],
            "trend": latest_week['trend']
        },
        "anomalies": latest_week['anomalies'],
        "month_summary": {
            "best_week": best_week,
            "worst_week": worst_week,
            "overall_trend": overall
        }
    }

def main():
    parser = argparse.ArgumentParser(description="Analyze weekly health data.")
    parser.add_argument("--csv", type=str, help="Path to weekly CSV file")
    parser.add_argument("--month", action="store_true", help="Aggregate multiple weekly CSVs")
    args = parser.parse_args()
    
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)
    report = {}
    
    if args.month:
        report = analyze_month(data_dir)
        if not report:
            print("No valid weekly CSV data found.")
            return
    elif args.csv:
        stats = analyze_week(args.csv)
        report = {
            "week_summary": {
                "avg_sleep": stats["avg_sleep"],
                "avg_stress": stats["avg_stress"],
                "trend": stats["trend"]
            },
            "anomalies": stats["anomalies"]
        }
    else:
        print("Please provide --csv PATH or --month flag.")
        return
        
    out_path = os.path.join(data_dir, "health_report.json")
    with open(out_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"Health report generated -> {out_path}")

if __name__ == "__main__":
    main()
