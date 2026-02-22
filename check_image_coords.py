import requests
import pdfplumber
import io
import re
from bs4 import BeautifulSoup

URL = "https://www.richlandcountyoh.gov/departments/jail/WhosinJail"

response = requests.get(URL)
soup = BeautifulSoup(response.content, 'html.parser')
iframe = soup.find('iframe')
src = iframe.get('src')
file_id = re.search(r'/d/([a-zA-Z0-9_-]+)', src).group(1)
download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

pdf_response = requests.get(download_url)
pdf_content = io.BytesIO(pdf_response.content)

with pdfplumber.open(pdf_content) as pdf:
    extracted = 0
    print("Coordinates of first 20 images found:")
    for i, page in enumerate(pdf.pages):
        for j, img in enumerate(page.images):
            print(f"Page {i+1} Image {j+1}: Size {img['width']}x{img['height']}, Top-Left: ({img['x0']}, {img['top']}), Bottom-Right: ({img['x1']}, {img['bottom']})")
            extracted += 1
            if extracted >= 20:
                break
        if extracted >= 20:
            break
