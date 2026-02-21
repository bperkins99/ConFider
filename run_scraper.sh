#!/bin/bash
cd "$(dirname "$0")"

# Activate Miniconda Environment
source ~/miniconda/bin/activate jail_env

# Run Scraper
python3 scraper.py
