import sqlite3
import csv
import os

def setup_database():
    conn = sqlite3.connect('bins.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bins (
        bin TEXT PRIMARY KEY,
        brand TEXT,
        type TEXT,
        category TEXT,
        issuer TEXT,
        issuer_phone TEXT,
        issuer_url TEXT,
        iso_code2 TEXT,
        iso_code3 TEXT,
        country_name TEXT
    )
    ''')
    
    # Read CSV and insert data
    with open('bin-list-data.csv', 'r', encoding='utf-8') as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            cursor.execute('''
            INSERT OR REPLACE INTO bins VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                row['BIN'],
                row['Brand'],
                row['Type'],
                row['Category'],
                row['Issuer'],
                row['IssuerPhone'],
                row['IssuerUrl'],
                row['isoCode2'],
                row['isoCode3'],
                row['CountryName']
            ))
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    setup_database()
    print("Database setup completed successfully!")
