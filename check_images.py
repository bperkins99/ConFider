import requests
import pdfplumber
import io
import re
from bs4 import BeautifulSoup
import os

URL = "https://www.richlandcountyoh.gov/departments/jail/WhosinJail"

print("Fetching URL...")
response = requests.get(URL)
soup = BeautifulSoup(response.content, 'html.parser')
iframe = soup.find('iframe')
src = iframe.get('src')
match = re.search(r'/d/([a-zA-Z0-9_-]+)', src)
file_id = match.group(1)
download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

print("Downloading PDF...")
pdf_response = requests.get(download_url)
pdf_content = io.BytesIO(pdf_response.content)

print("Analyzing PDF...")
with pdfplumber.open(pdf_content) as pdf:
    total_images = 0
    for i, page in enumerate(pdf.pages):
        num_images = len(page.images)
        total_images += num_images
        print(f"Page {i+1} has {num_images} images.")
        
        # Print details of images on the first page as a sample
        if i == 0 and num_images > 0:
            print("Sample image details on Page 1:")
            for img in page.images:
                print(f"  - Size: {img['width']}x{img['height']}, bbox: ({img['x0']}, {img['top']}, {img['x1']}, {img['bottom']})")
                
    print(f"\nTotal images found in the entire PDF: {total_images}")
