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
LEADS_FILE = "/home/brad/jail_roster_project/leads.json"
# Target keywords in charges
TARGET_CHARGES = [
    "OVI", "DUI", "FELONY", "ASSAULT", "DOMESTIC", "STRANGULATION",
    "POSSESSION", "TRAFFICKING", "PARAPHERNALIA", "DRUG", # Drugs
    "THEFT", "BURGLARY", "ROBBERY", "TRESPASS", "STOLEN", # Property
    "WEAPON", "FIREARM", "CONCEALED", "DISABILITY", # Weapons
    "RESISTING", "OBSTRUCTING", "FALSIFICATION", "KIDNAPPING", "RAPE", "MANSLAUGHTER" # Serious/Other
]
EXCLUDE_TERMS = ["Theft", "Traffic", "Probation"]

def load_existing_leads():
    try:
        if os.path.exists(LEADS_FILE):
            with open(LEADS_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"Error loading existing leads: {e}")
    return []

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

def process_inmate(inmate, leads, target_charges, date_threshold):
    try:
        raw_date = inmate["booking_date_str"]
        # Handle potential random newlines or spaces
        raw_date = raw_date.strip()
        booking_date = datetime.strptime(raw_date, "%m/%d/%Y")
        
        # Filter by Date (Last 24 hours) - using 24h as per requirement
        # For testing, we might want to be lenient, but for prod use strict
        if booking_date < date_threshold:
            return

        matched_charges = []
        for charge in inmate["charges"]:
            if not charge: continue
            charge_clean = charge.strip()
            charge_upper = charge_clean.upper()
            
            # Check for exclusions
            if any(ex.upper() in charge_upper for ex in EXCLUDE_TERMS):
                continue

            # Check for targets
            if any(t.upper() in charge_upper for t in target_charges):
                matched_charges.append(charge_clean)
        
        if matched_charges:
            leads.append({
                "name": inmate["name"],
                "booking_date": raw_date,
                "charges": matched_charges,
                "all_charges": inmate["charges"],
            })
    except ValueError as ve:
        logging.warning(f"Date parse error for {inmate['name']}: {inmate['booking_date_str']} - {ve}")
    except Exception as e:
        logging.error(f"Error processing inmate {inmate['name']}: {e}")

def extract_leads_from_pdf(pdf_file):
    leads = []
    current_inmate = None
    # 48 hour window to catch "yesterday" bookings regardless of UTC server time
    target_date_threshold = datetime.now() - timedelta(hours=48) 

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
                        charge = row[6] if len(row) > 6 else ""

                        # Debug Log for filtering
                        # logging.info(f"Checking: {name} | Date: {booking_date_str}")

                        if booking_date_str and name:
                            # New Inmate
                            if current_inmate:
                                process_inmate(current_inmate, leads, TARGET_CHARGES, target_date_threshold)
                            
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
                process_inmate(current_inmate, leads, TARGET_CHARGES, target_date_threshold)

    except Exception as e:
        logging.error(f"Error parsing PDF: {e}")
        return leads
    return leads

def main():
    logging.info("Starting scraper...")
    
    # 1. Get Download URL
    pdf_url = get_pdf_download_url(URL)
    if not pdf_url:
        logging.error("Could not find PDF URL.")
        return
    
    logging.info(f"Downloading PDF from {pdf_url}...")
    pdf_content = download_pdf(pdf_url)
    if not pdf_content:
        return
        
    logging.info("Extracting leads...")
    new_leads = extract_leads_from_pdf(pdf_content)
    
    # Historical Accumulation logic
    existing_leads = load_existing_leads()
    
    # Create a set of existing unique keys (name + date)
    existing_keys = {f"{lead['name']}_{lead['booking_date']}" for lead in existing_leads}
    
    added_count = 0
    for lead in new_leads:
        key = f"{lead['name']}_{lead['booking_date']}"
        if key not in existing_keys:
            existing_leads.append(lead)
            added_count += 1
            
    # Sort leads newest first (descending by date)
    try:
        existing_leads.sort(key=lambda x: datetime.strptime(x['booking_date'].strip(), "%m/%d/%Y"), reverse=True)
    except Exception as e:
        logging.warning(f"Could not sort leads: {e}")

    # Save back the complete list
    with open(LEADS_FILE, "w") as f:
        json.dump(existing_leads, f, indent=4)
    
    logging.info(f"Found {len(new_leads)} recent leads. Added {added_count} NEW leads to history.")
    logging.info(f"Total historical leads in database: {len(existing_leads)}")
    logging.info(f"Saved to {LEADS_FILE}")

if __name__ == "__main__":
    main()
