import requests
import pdfplumber
import fitz
import io
import re
from bs4 import BeautifulSoup

URL = "https://www.richlandcountyoh.gov/departments/jail/WhosinJail"
print("Fetching URL...")
response = requests.get(URL)
soup = BeautifulSoup(response.content, 'html.parser')
iframe = soup.find('iframe')
src = iframe.get('src')
file_id = re.search(r'/d/([a-zA-Z0-9_-]+)', src).group(1)
download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
print("Downloading PDF...")
pdf_response = requests.get(download_url)
pdf_content = io.BytesIO(pdf_response.content)

with pdfplumber.open(pdf_content) as pdf:
    # Get first page
    page = pdf.pages[8] # using page 9 since it had images based on earlier test
    
    print("Images on Page 9:")
    for j, img in enumerate(page.images):
        print(f"  Image {j+1}: Top: {img['top']}, Bottom: {img['bottom']}")
        
    print("\nRows on Page 9:")
    tables = page.find_tables()
    for table in tables:
        for i, row_cells in enumerate(table.rows):
            # A row is an object with cells and bbox. Wait, table.rows is a list of Row objects?
            # Actually find_tables returns Table objects.
            # let's try to print the bounding box of the row
            print(f"  Row {i+1} bbox: {row_cells.bbox}")
            # Also print the text
            text = table.extract()[i]
            print(f"    Text: {text[:2]}")
        break
