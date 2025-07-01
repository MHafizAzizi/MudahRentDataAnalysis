# MudahRentDataAnalysis

## 📄 Overview
This is a project of getting rental properties data from Mudah.my

## 📁 Folder Structure
- `data/` – Contains raw and processed datasets. MasterFile.csv contains the cleaned and merged data from the raw datasets
- `scripts/` – Python scripts for data cleaning and scraping.

    - `1_webscrape.py` is the Python script for scraping data from the website
    - `2_clean_merge_into_masterfile.py` is the cleaning script and merging the processed dataset into the MasterFile.csv
- `app/` – Streamlit web application. WIP

## 🚀 Getting Started

1. Setup Virtual Environment - `python -m venv venv`
2. Activate Virtual Environment - `source venv/bin/activate`
3. Install the necessary dependencies - `pip install -r requirements.txt`

## 📦 Dependencies
- `requirements.txt` contains the necessary dependencies for the scripts to work

The script code is based on this machine learning project by Aditya Arie Wijaya 

https://adtarie.net/posts/005-webscraping-machinelearning-rent-pricing/



