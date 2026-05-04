#!/usr/bin/env python3
"""Simple script to check the number of BTC rows in the prices table."""

import sqlite3

DATABASE_PATH = r"d:\autonomus\generated_project\finance_bot\notes.db"

def count_btc_rows():
    """Count the number of rows for bitcoin in the prices table."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Count BTC rows
        cursor.execute("SELECT COUNT(*) FROM prices WHERE coin_id = 'bitcoin'")
        count = cursor.fetchone()[0]
        
        print(f"BTC (bitcoin) row count: {count}")
        
        conn.close()
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}")

if __name__ == "__main__":
    count_btc_rows()
