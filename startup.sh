#!/bin/bash
# Wait 30 seconds for networking to fully initialize after a reboot
sleep 30

# 1. Start the Streamlit Dashboard in the background
source /home/brad/miniconda/bin/activate jail_env
cd /home/brad/jail_roster_project
nohup streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true > /dev/null 2>&1 &

# 2. Run the Scraper once just in case it missed its 6 AM schedule while powered off
/home/brad/jail_roster_project/run_scraper.sh
