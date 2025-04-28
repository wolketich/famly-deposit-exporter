#!/usr/bin/env python3
import os
import sys
import time
import csv
import json
import argparse
import logging
from datetime import datetime
from getpass import getpass
import pandas as pd
from tqdm import tqdm

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

CONFIG = {
    "BASE_URL": "https://app.famly.co/#/login",
    "CHILD_PROFILE_URL_TEMPLATE": "https://app.famly.co/#/account/childProfile/{}/plansAndInvoices",
    "USER": "wolketich",
    "TIMESTAMP": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "TIMEOUTS": {
        "DEFAULT": 25,
        "PAGE_LOAD": 3,
        "LOGIN": 15,
        "MODAL_APPEAR": 1.0,
        "MODAL_CLOSE": 0.5,
        "BETWEEN_ACTIONS": 0.3,
        "BETWEEN_CHILDREN": 3.0
    },
    "SELECTORS": {
        "LOGIN": {
            "EMAIL_INPUT": 'input[type="email"]',
            "PASSWORD_INPUT": 'input[type="password"]',
            "LOGIN_BUTTON": 'button[type="submit"]'
        },
        "PAGE_READY": [
            ".sc-beqWaB.bUiODS",
            "h3",
            "button"
        ],
        "MODAL": {
            "CONTAINER": [
                '[role="dialog"]', '.modal', 'form'
            ],
            "CLOSE_BUTTON": [
                '#closeModalButton',
                'button[aria-label="Close"]'
            ],
            "BILL_PAYER": '.Select-value-label',
            "AMOUNT": 'input[name="amount"]',
            "DATE": 'input[value*="/"]',
            "NOTE": 'textarea[name="note"]',
            "ALREADY_PAID": 'input[name="alreadyPaid"]'
        }
    }
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("famly_deposit_extractor.log")
    ]
)
logger = logging.getLogger("FamlyExtractor")

class FamlyDepositExtractor:
    def __init__(self, headless=False, debug=False, output_dir="output"):
        self.headless = headless and not debug
        self.debug = debug
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        if debug:
            logger.setLevel(logging.DEBUG)
        self.driver = None
        self.deposits = []
        self.extracted_data = []
        self.setup_driver()

    def setup_driver(self):
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--user-agent=Mozilla/5.0")
        chrome_options.add_argument("--disable-animations")
        if self.debug:
            chrome_options.add_argument("--auto-open-devtools-for-tabs")
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.maximize_window()
        self.wait = WebDriverWait(self.driver, CONFIG["TIMEOUTS"]["DEFAULT"])
        logger.info("WebDriver setup complete")

    def login(self, username, password):
        try:
            self.driver.get(CONFIG["BASE_URL"])
            email_input = self.wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, CONFIG["SELECTORS"]["LOGIN"]["EMAIL_INPUT"])
            ))
            email_input.clear()
            email_input.send_keys(username)
            password_input = self.driver.find_element(
                By.CSS_SELECTOR, CONFIG["SELECTORS"]["LOGIN"]["PASSWORD_INPUT"])
            password_input.clear()
            password_input.send_keys(password)
            login_button = self.driver.find_element(
                By.CSS_SELECTOR, CONFIG["SELECTORS"]["LOGIN"]["LOGIN_BUTTON"])
            login_button.click()
            self.wait.until(EC.url_changes(CONFIG["BASE_URL"]))
            time.sleep(CONFIG["TIMEOUTS"]["LOGIN"])
            return True
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            return False

    def navigate_to_child_profile(self, child_id, child_name=""):
        try:
            url = CONFIG["CHILD_PROFILE_URL_TEMPLATE"].format(child_id)
            self.driver.get(url)
            time.sleep(CONFIG["TIMEOUTS"]["PAGE_LOAD"])
            return True
        except Exception as e:
            logger.error(f"Navigation failed: {str(e)}")
            return False

    def is_page_fully_loaded(self):
        try:
            ready_state = self.driver.execute_script("return document.readyState")
            return ready_state == "complete"
        except:
            return False

    def find_deposits(self):
        logger.info("Finding deposits...")
        max_wait = time.time() + 20
        while not self.is_page_fully_loaded() and time.time() < max_wait:
            time.sleep(1)
        time.sleep(CONFIG["TIMEOUTS"]["BETWEEN_ACTIONS"])
        try:
            script = """
const extractorResult = (function() {
    function querySelectorAll(selector, root = document) {
        try {
            return Array.from(root.querySelectorAll(selector));
        } catch {
            return [];
        }
    }
    function elementContainsText(element, text) {
        return element && element.textContent && element.textContent.trim().includes(text);
    }
    function extractDeposits() {
        const depositsSection = document.querySelector('.sc-beqWaB.bUiODS');
        if (!depositsSection) return [];
        const depositBlocks = querySelectorAll('.sc-beqWaB.sc-CQMxN.bUiODS', depositsSection);
        const results = [];
        depositBlocks.forEach((block, index) => {
            const paragraphs = querySelectorAll('p', block);
            let depositAmount = '';
            let depositCurrency = '';
            let depositStatus = '';
            let hasBeenReturned = false;
            let returnStatus = '';
            paragraphs.forEach(p => {
                if (elementContainsText(p, 'Deposit')) {
                    const small = p.parentElement ? p.parentElement.querySelector('small') : null;
                    depositStatus = small ? small.textContent.trim() : '';
                }
                if (['€', '$', '£'].includes(p.textContent.trim())) {
                    depositCurrency = p.textContent.trim();
                }
                if (/^[\\d,.]+$/.test(p.textContent.trim())) {
                    depositAmount = p.textContent.trim();
                }
                if (elementContainsText(p, 'Return')) {
                    const small = p.parentElement ? p.parentElement.querySelector('small') : null;
                    if (small) {
                        returnStatus = small.textContent.trim();
                        hasBeenReturned = (returnStatus === 'Invoiced');
                    }
                }
            });
            results.push({
                index: index + 1,
                type: 'Deposit',
                amount: depositAmount,
                currency: depositCurrency,
                depositStatus: depositStatus,
                hasBeenReturned: hasBeenReturned,
                returnStatus: returnStatus
            });
        });
        return results;
    }
    try {
        const deposits = extractDeposits();
        return { success: true, deposits: deposits };
    } catch (error) {
        return { success: false, error: error.toString() };
    }
})();
return extractorResult;
            """
            result = self.driver.execute_script(script)
            if result.get('success'):
                self.deposits = result.get('deposits', [])
                return self.deposits
            else:
                logger.error(f"Error extracting deposits: {result.get('error')}")
                return []
        except Exception as e:
            logger.error(f"Error running JS extractor: {str(e)}")
            return []

    def batch_process(self, children_data):
        results = []
        for i, child in enumerate(children_data):
            logger.info(f"Processing {child.get('name')} ({child.get('child_id')})")
            self.deposits = []
            self.navigate_to_child_profile(child.get('child_id', ''))
            deposits = self.find_deposits()
            results.append({
                "child_name": child.get('name'),
                "child_id": child.get('child_id'),
                "deposits_found": len(deposits),
                "deposits": deposits
            })
            time.sleep(CONFIG["TIMEOUTS"]["BETWEEN_CHILDREN"])
        return results

    def cleanup(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

    def run_batch(self, username, password, input_file):
        try:
            children_df = pd.read_csv(input_file)
            children_data = children_df.to_dict('records')
            if not self.login(username, password):
                logger.error("Login failed")
                return
            return self.batch_process(children_data)
        finally:
            self.cleanup()

def main():
    parser = argparse.ArgumentParser(description="Famly Deposit Extractor")
    parser.add_argument("-u", "--username", help="Famly email")
    parser.add_argument("-p", "--password", help="Famly password")
    parser.add_argument("-i", "--input", required=True, help="Input CSV file")
    parser.add_argument("--headless", action="store_true", help="Run headless")
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    args = parser.parse_args()

    username = args.username or input("Famly email: ")
    password = args.password or getpass("Famly password: ")

    extractor = FamlyDepositExtractor(headless=args.headless, debug=args.debug)
    results = extractor.run_batch(username, password, args.input)

    if results:
        out_file = os.path.join("output", f"batch_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        os.makedirs("output", exist_ok=True)
        with open(out_file, "w") as f:
            json.dump(results, f, indent=2)
        print(f"✅ Batch completed. Results saved to {out_file}")

if __name__ == "__main__":
    sys.exit(main())
