#!/usr/bin/env python3
"""
Famly Deposit Excel Consolidator

A script to consolidate all individual child deposit CSV files into a single Excel file.
Takes the summary JSON file from the batch process as input.

Usage:
    python consolidate_deposits.py --summary <summary_file.json> --output <consolidated.xlsx>

Requirements:
    pip install pandas openpyxl
"""

import pandas as pd
import json
import os
import argparse
from datetime import datetime

def consolidate_deposits(summary_file, base_dir=None, output_excel=None, timestamp=None, username=None):
    """
    Consolidate all deposit information into a single Excel file.
    
    Args:
        summary_file (str): Path to the summary JSON file
        base_dir (str): Base directory for deposit CSV files (optional)
        output_excel (str): Path for the output Excel file (optional)
        timestamp (str): Current timestamp for the export
        username (str): Username of the person running the script
        
    Returns:
        bool: True if successful, False otherwise
    """
    print(f"📊 Consolidating deposits from summary: {summary_file}")
    
    # Set timestamp and username
    if not timestamp:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not username:
        username = "wolketich"  # Default username
    
    # Determine the base directory if not provided
    if not base_dir:
        base_dir = os.path.dirname(os.path.abspath(summary_file))
    
    # Read the summary JSON file
    try:
        with open(summary_file, 'r') as f:
            summary = json.load(f)
    except Exception as e:
        print(f"❌ Error reading summary file: {str(e)}")
        return False
    
    # List to store all deposit rows
    all_rows = []
    children_processed = 0
    children_with_deposits = 0
    
    # Process each result in the summary
    for result in summary.get('results', []):
        if not result.get('success', False):
            continue
        
        child_name = result.get('child_name', '')
        child_id = result.get('child_id', '')
        output_file = result.get('output_file', '')
        
        children_processed += 1
        
        # Handling relative paths
        if output_file and not os.path.isabs(output_file):
            output_file = os.path.join(base_dir, os.path.basename(output_file))
        
        if not output_file or not os.path.exists(output_file):
            print(f"⚠️ Warning: Cannot find file for {child_name} (ID: {child_id}): {output_file}")
            continue
        
        # Read the child's deposits CSV
        try:
            deposits_df = pd.read_csv(output_file)
            
            # Skip if no deposits
            if deposits_df.empty:
                print(f"ℹ️ No deposits found for {child_name} (ID: {child_id})")
                continue
            
            # Count deposits for this child
            deposit_count = len(deposits_df)
            children_with_deposits += 1
            
            print(f"✅ Processing {deposit_count} deposits for {child_name} (ID: {child_id})")
            
            # For each deposit, create a row
            for i, (_, deposit) in enumerate(deposits_df.iterrows(), 1):
                # Get deposit amount (try different fields)
                amount = ""
                for field in ['formAmount', 'amount']:
                    if field in deposit and deposit[field]:
                        amount = deposit[field]
                        break
                
                # Format amount with currency
                # currency = deposit.get('currency', '')
                formatted_amount = amount if amount else 0
                
                # Get date
                date = deposit.get('depositDate', '')
                
                # Get note
                note = deposit.get('note', '')
                
                # Deposit label (add number if there are multiple deposits)
                deposit_label = f"Deposit{i}" if deposit_count > 1 else "Deposit"
                
                # Add row
                all_rows.append({
                    'Name': child_name,
                    'Child ID': child_id,
                    'Deposit': deposit_label,
                    'Amount': formatted_amount,
                    'Date': date,
                    'Note': note,
                    'Is Returned': 'Yes' if deposit.get('hasBeenReturned', False) else 'No',
                    'Refund Status': deposit.get('refundState', ''),
                    'Deposit Status': deposit.get('depositStatus', ''),
                    'Bill Payer': deposit.get('billPayer', '')
                })
                
        except Exception as e:
            print(f"❌ Error processing {output_file}: {str(e)}")
    
    # Create DataFrame from all rows
    if not all_rows:
        print("❌ No deposits found to consolidate")
        return False
    
    df = pd.DataFrame(all_rows)
    
    # Generate output filename if not provided
    if not output_excel:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_excel = f"consolidated_deposits_{ts}.xlsx"
    
    # Save to Excel with export information
    try:
        # Create a Pandas Excel writer with openpyxl engine
        with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
            # Write the main data
            df.to_excel(writer, sheet_name='Deposits', index=False)
            
            # Create a summary sheet
            summary_data = {
                'Property': [
                    'Export Date', 
                    'Exported By', 
                    'Total Children Processed', 
                    'Children With Deposits', 
                    'Total Deposits'
                ],
                'Value': [
                    timestamp,
                    username,
                    children_processed,
                    children_with_deposits,
                    len(all_rows)
                ]
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Export Info', index=False)
        
        print(f"✅ Successfully consolidated {len(all_rows)} deposits into {output_excel}")
        print(f"📊 Summary: {children_with_deposits}/{children_processed} children had deposits")
        
        return True
        
    except Exception as e:
        print(f"❌ Error saving Excel file: {str(e)}")
        return False

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Consolidate Famly deposits into a single Excel file")
    parser.add_argument('-s', '--summary', required=True, help='Path to summary JSON file')
    parser.add_argument('-d', '--dir', help='Base directory for deposit CSV files')
    parser.add_argument('-o', '--output', help='Output Excel file path')
    parser.add_argument('-t', '--timestamp', default="2025-04-28 15:21:25", help='Current timestamp')
    parser.add_argument('-u', '--username', default="wolketich", help='Username')
    args = parser.parse_args()
    
    consolidate_deposits(
        args.summary, 
        args.dir, 
        args.output, 
        args.timestamp, 
        args.username
    )

if __name__ == '__main__':
    main()