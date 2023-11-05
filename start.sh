#! /bin/bash
cd /home/pi/homeautomation/ChargeControl
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 ChargeControl.py 
