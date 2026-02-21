import requests
from bs4 import BeautifulSoup
import pdfplumber
import pandas as pd
import json
import os
import re
import logging
from datetime import datetime, timedelta
import io

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configuration
URL = "https://www.richlandcountyoh.gov/departments/jail/WhosinJail"
LEADS_FILE = "/home/brad/jail_roster_project/debug_leads.json"
# TARGET_CHARGES = ["OVI", "DUI", "Assault", "Domestic", "Felony"]
# EXCLUDE_TERMS = ["Theft", "Traffic", "Probation"]

def get_pdf_download_url(page_url):
    try:
        response = requests.get(page_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find the embedded Google Drive PDF
        iframe = soup.find('iframe')
        if not iframe:
            logging.error("No iframe found on page.")
            return None
            
        src = iframe.get('src')
        # Extract File ID (assuming format like .../d/FILE_ID/preview...)
        match = re.search(r'/d/([a-zA-Z0-9_-]+)', src)
        if match:
            file_id = match.group(1)
            download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
            return download_url
        else:
            logging.error(f"Could not extract file ID from src: {src}")
            return None
    except Exception as e:
        logging.error(f"Error fetching page: {e}")
        return None

def download_pdf(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return io.BytesIO(response.content)
    except Exception as e:
        logging.error(f"Error downloading PDF: {e}")
        return None

def process_inmate(inmate, leads):
    try:
        raw_date = inmate["booking_date_str"]
        # Handle potential random newlines or spaces
        raw_date = raw_date.strip()
        
        # Log everyone found
        logging.info(f"FOUND: {inmate['name']} | Date: {raw_date} | Charges: {inmate['charges']}")
        
        leads.append({
            "name": inmate["name"],
            "booking_date": raw_date,
            "charges": inmate["charges"],
            "all_charges": inmate["charges"],
        })
    except Exception as e:
        logging.error(f"Error processing inmate {inmate['name']}: {e}")

def extract_leads_from_pdf(pdf_file):
    leads = []
    current_inmate = None

    try:
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not any(row): continue
                        # Basic row validation
                        if len(row) < 3: continue 
                        
                        # Headers check
                        if "Booking Date" in str(row[0]) or "Inmate" in str(row[1]): continue

                        booking_date_str = row[0]
                        name = row[1]
                        # Charge is usually in column 6 or 7 depending on layout
                        # Based on previous robust logic, let's assume valid row if name exist
                        # Adjust index based on visual inspection if needed. usually col 6 (0-indexed) is charge
                        charge = row[6] if len(row) > 6 else ""

                        if booking_date_str and name:
                            # New Inmate
                            if current_inmate:
                                process_inmate(current_inmate, leads)
                            
                            current_inmate = {
                                "name": name,
                                "booking_date_str": booking_date_str,
                                "charges": [charge] if charge else []
                            }
                        elif current_inmate and charge:
                            # Continuation of charges for current inmate
                            current_inmate["charges"].append(charge)
            
            # Process last one
            if current_inmate:
                process_inmate(current_inmate, leads)

    except Exception as e:
        logging.error(f"Error parsing PDF: {e}")
        return leads
    return leads

def main():
    logging.info("Starting DEBUG scraper (No Filters)...")
    
    # 1. Get Download URL
    pdf_url = get_pdf_download_url(URL)
    if not pdf_url:
        logging.error("Could not find PDF URL.")
        return

    # 2. Download PDF
    logging.info(f"Downloading PDF from {pdf_url}...")
    pdf_content = download_pdf(pdf_url)
    if not pdf_content:
        return

    # 3. Extract Leads
    logging.info("Extracting ALL inmates...")
    leads = extract_leads_from_pdf(pdf_content)
    logging.info(f"Found {len(leads)} TOTAL inmates.")

    # 4. Save to JSON
    with open(LEADS_FILE, "w") as f:
        json.dump(leads, f, indent=4)
    logging.info(f"Saved ALL to {LEADS_FILE}")

if __name__ == "__main__":
    main()
