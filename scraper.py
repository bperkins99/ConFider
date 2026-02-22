import requests
from bs4 import BeautifulSoup
import pdfplumber
import os
import re
import logging
from datetime import datetime, timedelta
import io
from supabase import create_client, Client
import fitz
import base64
import argparse
import subprocess
import openpyxl

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Supabase Configuration
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    logging.error("Missing SUPABASE_URL or SUPABASE_KEY environment variables.")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Configuration
URL = "https://www.richlandcountyoh.gov/departments/jail/WhosinJail"
# Target keywords in charges
TARGET_CHARGES = [
    "OVI", "DUI", "FELONY", "ASSAULT", "DOMESTIC", "STRANGULATION",
    "POSSESSION", "TRAFFICKING", "PARAPHERNALIA", "DRUG", # Drugs
    "THEFT", "BURGLARY", "ROBBERY", "TRESPASS", "STOLEN", # Property
    "WEAPON", "FIREARM", "CONCEALED", "DISABILITY", # Weapons
    "RESISTING", "OBSTRUCTING", "FALSIFICATION", "KIDNAPPING", "RAPE", "MANSLAUGHTER" # Serious/Other
]
EXCLUDE_TERMS = ["Theft", "Traffic", "Probation"]

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
            # Format date for Supabase (YYYY-MM-DD)
            storage_date = booking_date.strftime("%Y-%m-%d")
            leads.append({
                "name": inmate["name"],
                "booking_date": storage_date,
                "charges": matched_charges,
                "all_charges": inmate["charges"],
                "mugshot_base64": inmate.get("mugshot_base64", None)
            })
    except ValueError as ve:
        logging.warning(f"Date parse error for {inmate['name']}: {inmate['booking_date_str']} - {ve}")
    except Exception as e:
        logging.error(f"Error processing inmate {inmate['name']}: {e}")

def extract_leads_from_pdf(pdf_file, historical_backfill=False):
    leads = []
    
    # Normally check 48 hours for new leads. If historical, accept the past 10 years.
    if historical_backfill:
        target_date_threshold = datetime.now() - timedelta(days=3650)
    else:
        target_date_threshold = datetime.now() - timedelta(hours=48) 

    try:
        # Load PDF with both libraries
        doc = fitz.open(stream=pdf_file, filetype="pdf")
        
        with pdfplumber.open(pdf_file) as pdf:
            for page_num, page in enumerate(pdf.pages):
                # 1. Extract Images from this page using PyMuPDF
                fitz_page = doc.load_page(page_num)
                image_list = fitz_page.get_images(full=True)
                page_images = []
                
                for img in image_list:
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    b64 = f"data:image/{image_ext};base64," + base64.b64encode(image_bytes).decode('utf-8')
                    
                    # Get coordinates of this image on the page
                    rects = fitz_page.get_image_rects(xref)
                    if rects:
                        # Use the first bounding box found for the image
                        rect = rects[0]
                        page_images.append({
                            "y0": rect.y0, # top
                            "y1": rect.y1, # bottom
                            "b64": b64
                        })

                # 2. Extract Text Rows and align images
                tables = page.find_tables()
                current_inmate = None

                for table in tables:
                    for r_idx, row_obj in enumerate(table.rows):
                        row_bbox = row_obj.bbox # (x0, top, x1, bottom)
                        row_top = row_bbox[1]
                        row_bottom = row_bbox[3]
                        
                        # Extract text for this row
                        row_texts = table.extract()[r_idx]
                        if not any(row_texts) or len(row_texts) < 3: 
                            continue 
                        if "Booking Date" in str(row_texts[0]) or "Inmate" in str(row_texts[1]): 
                            continue

                        booking_date_str = row_texts[0]
                        name = row_texts[1]
                        charge = row_texts[6] if len(row_texts) > 6 else ""

                        # Check if any image belongs to this row (image top falls inside row bbox top/bottom threshold)
                        # Give a slight padding (e.g. 5px) to be safe
                        matched_b64 = None
                        for img_data in page_images:
                            if row_top - 5 <= img_data["y0"] <= row_bottom + 5:
                                matched_b64 = img_data["b64"]
                                break

                        if booking_date_str and name:
                            if current_inmate:
                                process_inmate(current_inmate, leads, TARGET_CHARGES, target_date_threshold)
                            
                            current_inmate = {
                                "name": name,
                                "booking_date_str": booking_date_str,
                                "charges": [charge] if charge else [],
                                "mugshot_base64": matched_b64
                            }
                        elif current_inmate and charge:
                            current_inmate["charges"].append(charge)
                
                # Check for last inmate on the page
                if current_inmate:
                    process_inmate(current_inmate, leads, TARGET_CHARGES, target_date_threshold)


    except Exception as e:
        logging.error(f"Error parsing PDF: {e}")
        return leads
    return leads

def main():
    logging.info("Starting scraper (Supabase Mode)...")
    
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
    
    if not new_leads:
        logging.info("No new leads found to upload.")
        return

    logging.info(f"Uploading {len(new_leads)} leads to Supabase...")
    
    added_count = 0
    for lead in new_leads:
        try:
            # We use upsert with the 'unique_lead' constraint (name, booking_date)
            # which we asked the user to create.
            res = supabase.table("jail_leads").upsert(
                lead, 
                on_conflict="name, booking_date"
            ).execute()
            added_count += 1
        except Exception as e:
            logging.error(f"Error uploading lead {lead['name']}: {e}")

    logging.info(f"Successfully processed {added_count} leads in Supabase.")

if __name__ == "__main__":
    main()
