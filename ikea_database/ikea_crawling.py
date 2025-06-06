import os
import time
import requests
from PIL import Image
from io import BytesIO
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import json
import re

"""
How to use:
    1. type into terminal:
        pip install -r requirements.txt
    2. place chromedriver folder to the same directory with this file
    3. set 'NUM_PRODUCTS' to the number of products per category you want
    4. run this .py file
    5. the crawled images will be saved in 'ikea_images/main' and 'ikea_images/sub'
        - main images are for model encoding, sub images are for additional images
    6. the product information will be saved in 'ikea_product_info.json'
        - saved image name is identical to the key of .json file
    7. if some categories have an error, you can set 'RUN_ONLY_CATEGORY' to crawl only a specific category
"""

# --------- config ----------
SAVE_LIMIT = 2 # (fixed) image number per product
NUM_PRODUCTS = 2  # product number per category
RUN_ONLY_CATEGORY = None  # "None", "sofa", "desk", "chair", "cupboard", "couch", "bookcase"

category_metadata = {
    "sofa": "https://www.ikea.com/kr/ko/cat/sofas-fu003/",
    "desk": "https://www.ikea.com/kr/ko/cat/desks-computer-desks-20649/",
    "chair": "https://www.ikea.com/kr/ko/cat/desk-chairs-20652/",
    "cupboard": "https://www.ikea.com/kr/ko/cat/cabinets-cupboards-st003/",
    "couch": "https://www.ikea.com/kr/ko/cat/armchairs-couches-fu006/",
    "bookcase": "https://www.ikea.com/kr/ko/cat/bookcases-shelving-units-st002/",
    "bed": "https://www.ikea.com/kr/ko/cat/beds-bm003/"
}

main_images_path = f"ikea_images/main"
sub_images_path = f"ikea_images/sub"
driver_path = "./chromedriver-mac-arm64/chromedriver"

# ---------------------------
os.makedirs(main_images_path, exist_ok=True)
os.makedirs(sub_images_path, exist_ok=True)

# chromedriver config
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
service = Service(executable_path=driver_path)
driver = webdriver.Chrome(service=service, options=chrome_options)

final_product_info = {}
category_counts = {}

for CATEGORY, category_url in category_metadata.items():
    if RUN_ONLY_CATEGORY and CATEGORY != RUN_ONLY_CATEGORY:
        continue

    print(f"\n▶ Crawling category: {CATEGORY}")
    driver.get(category_url)
    time.sleep(3)

    product_info = {}
    product_ids = []

    for page in range(5):
        if len(product_info) >= NUM_PRODUCTS:
            break

        products = driver.find_elements(By.CSS_SELECTOR, "div.plp-fragment-wrapper div[data-testid='plp-product-card']")
        print(f"[INFO] Found {len(products)} products on page {page + 1}")

        for i, p in enumerate(products):
            if len(product_info) >= NUM_PRODUCTS:
                break
            try:
                product_id = p.get_attribute("data-product-number")
                product_name = p.get_attribute("data-product-name")
                desc_elements = p.find_elements(By.CSS_SELECTOR, "span.plp-price-module__description")
                product_description = desc_elements[0].text.strip() if desc_elements else ""
                product_price = p.get_attribute("data-price")

                try:
                    rating_raw = p.find_element(By.CSS_SELECTOR, "button.plp-rating span[aria-label]").get_attribute("aria-label")
                    rating_match = re.search(r"([\d.]+)", rating_raw)
                    product_rating = float(rating_match.group(1)) if rating_match else None
                except:
                    product_rating = "N/A"

                try:
                    reviews_raw = p.find_element(By.CSS_SELECTOR, "span.plp-rating__label").text.strip()
                    reviews_match = re.search(r"(\d+)", reviews_raw)
                    product_num_review = int(reviews_match.group(1)) if reviews_match else 0
                except:
                    product_num_review = 0

                product_link = p.find_element(By.CSS_SELECTOR, "a.plp-product__image-link").get_attribute("href")
                product_key = f"{CATEGORY}-{product_id}"

                if product_id in product_ids:
                    continue
                else:
                    product_ids.append(product_id)

                product_info[product_key] = {
                    "id": product_id,
                    "name": product_name,
                    "description": product_description,
                    "price": product_price,
                    "rating": product_rating,
                    "num_reviews": product_num_review,
                    "link": product_link
                }

                img_tags = p.find_elements(By.CSS_SELECTOR, "img.plp-product__image")
                img_urls = []
                for img in img_tags:
                    src = img.get_attribute("src")
                    if src and src not in img_urls:
                        src = src.split("?")[0] + "?f=jpg&h=600&w=600"
                        img_urls.append(src)
                    if len(img_urls) >= SAVE_LIMIT:
                        break

                for img_idx, img_url in enumerate(img_urls):
                    try:
                        response = requests.get(img_url)
                        if response.status_code == 200:
                            img = Image.open(BytesIO(response.content)).convert("RGB")
                            filename = f"{CATEGORY}-{product_id}-{img_idx}.png"
                            save_path = main_images_path if img_idx == 0 else sub_images_path
                            img.save(os.path.join(save_path, filename))
                    except Exception as e:
                        print(f"[Image Error] {product_key} - {img_idx}: {e}")

            except Exception as e:
                print(f"[ERROR] Product {i}: {e}")
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])

        # move to next page
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        try:
            more_button = driver.find_element(By.CSS_SELECTOR, "a.plp-btn--secondary")
            next_page_url = more_button.get_attribute("href")
            driver.get(next_page_url)
        except:
            break

    final_product_info.update(product_info)
    category_counts[CATEGORY] = len(product_info)
    print(f"[DONE] {CATEGORY}: {len(product_info)} products crawled.")

driver.quit()

with open("ikea_product_info.json", "w", encoding="utf-8") as f:
    json.dump(final_product_info, f, indent=2, ensure_ascii=False)

print("\n✅ All categories done!")
for cat, count in category_counts.items():
    print(f"- {cat}: {count} items")