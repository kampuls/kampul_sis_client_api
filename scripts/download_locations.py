import requests
import json
import os
import time

base_url = "https://data.mef.gov.kh/api/v1/public-datasets/pd_68e370856a965e00074a5e7b/json"
page_size = 200
total_items = 14582
max_pages = (total_items // page_size) + 2 # Safety buffer

# Helper to load existing data
output_dir = "../pama_international_school/assets/json"
os.makedirs(output_dir, exist_ok=True)
output_file = os.path.join(output_dir, "locations.json")

all_items = []
start_page = 1

if os.path.exists(output_file):
    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            all_items = json.load(f)
            print(f"Loaded {len(all_items)} existing items.")
            # Calculate start page based on existing items
            # Assuming pages are full (200 items) except maybe the last one
            # If we have 4800 items, we finished page 24. Start at 25.
            # If we have 4801 items, we are in the middle of page 25? API doesn't support offset, only page.
            # So if we have partial data, we might duplicate or miss. 
            # Safer to start from (len // page_size) + 1, and maybe some overlap is fine if we deduplicate?
            # Or just truncate to exact page boundary.
            
            # Let's truncate to valid pages
            valid_count = (len(all_items) // page_size) * page_size
            if valid_count < len(all_items):
                print(f"Trimming {len(all_items) - valid_count} items to align with page boundaries.")
                all_items = all_items[:valid_count]
            
            start_page = (len(all_items) // page_size) + 1
            print(f"Resuming from page {start_page}...")
    except Exception as e:
        print(f"Error loading existing file: {e}. Starting from scratch.")
        all_items = []

print(f"Starting download of remaining items out of {total_items}...")

for page in range(start_page, max_pages):
    print(f"Fetching page {page}...")
    for attempt in range(5): # Retry up to 5 times
        try:
            response = requests.get(f"{base_url}?page={page}&page_size={page_size}", verify=False, timeout=30)
            
            if response.status_code == 429:
                print(f"Rate limited (429) on page {page}. Sleeping for 60 seconds...")
                time.sleep(60)
                continue
                
            if response.status_code != 200:
                print(f"Failed to fetch page {page}: {response.status_code}. Retrying in 5s...")
                time.sleep(5)
                continue
            
            data = response.json()
            items = data.get('items', [])
            if not items:
                print("No more items found.")
                # Save just in case
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(all_items, f, ensure_ascii=False, indent=2)
                break
                
            all_items.extend(items)
            
            # Save progress every page to avoid losing data
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(all_items, f, ensure_ascii=False, indent=2)
                
            time.sleep(2) # Increased delay to 2s to cause less load
            break # Success, move to next page
            
        except Exception as e:
            print(f"Error fetching page {page} (Attempt {attempt+1}): {e}")
            time.sleep(5)
    else:
        print(f"Failed to fetch page {page} after 5 attempts.")
        print("Stopping download due to errors.")
        break
    
    if not items:
        break

print(f"Total downloaded items: {len(all_items)}")
print(f"Data saved to {output_file}")
