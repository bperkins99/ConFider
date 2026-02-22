import requests
import fitz  # PyMuPDF is better for extracting actual image files
import io
import re
import os
from bs4 import BeautifulSoup

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

print("Extracting actual images...")
doc = fitz.open(stream=pdf_content, filetype="pdf")

extracted = 0
for page_num in range(len(doc)):
    page = doc.load_page(page_num)
    image_list = page.get_images(full=True)
    
    for img_index, img in enumerate(image_list):
        xref = img[0]
        base_image = doc.extract_image(xref)
        image_bytes = base_image["image"]
        image_ext = base_image["ext"]
        
        filename = f"extracted_image_{page_num}_{img_index}.{image_ext}"
        with open(filename, "wb") as f:
            f.write(image_bytes)
        print(f"Saved {filename}")
        
        extracted += 1
        if extracted >= 5:
            break
    if extracted >= 5:
        break

print("Done extracting 5 images.")
