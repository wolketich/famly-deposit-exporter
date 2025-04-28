#!/usr/bin/env python3
"""
Famly Deposit Extractor

A script to extract deposit information from the Famly system and export to CSV.

Usage:
    python famly_deposit_extractor.py --username <email> --password <password> --output <filename.csv>

Requirements:
    pip install selenium pandas webdriver-manager tqdm
"""

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
from selenium.common.exceptions import (
    TimeoutException, 
    NoSuchElementException, 
    ElementClickInterceptedException,
    StaleElementReferenceException
)
from webdriver_manager.chrome import ChromeDriverManager

# Configuration
CONFIG = {
    "BASE_URL": "https://app.famly.co/#/login",
    "DEPOSITS_URL": "https://app.famly.co/#/finance/income",  # Update this to the correct path
    "USER": "wolketich",
    "TIMESTAMP": "2025-04-28 14:35:47",
    "DEFAULT_TIMEOUT": 15,  # seconds
    "RETRY_ATTEMPTS": 3,
    "DELAY_BETWEEN_ACTIONS": 0.5,  # seconds
    "MODAL_LOAD_DELAY": 1.0,  # seconds
    "SELECTORS": {
        "LOGIN": {
            "EMAIL_INPUT": 'input[type="email"]',
            "PASSWORD_INPUT": 'input[type="password"]',
            "LOGIN_BUTTON": 'button[type="submit"]'
        },
        "DEPOSITS": {
            "CONTAINERS": [
                '.sc-beqWaB.sc-eIoBCF.bUiODS.iDrAoK', 
                '[class*="sc-beqWaB"][class*="sc-eIoBCF"]'
            ],
            "DEPOSIT_TEXT": "p",
            "RETURN_TEXT": "p",
            "CURRENCY_SYMBOLS": ["€", "$", "£"]
        },
        "MODAL": {
            "CONTAINER": [
                '.LEGACY_MODAL_groupActionModal',
                '[role="dialog"]',
                '.modal',
                'form'
            ],
            "CLOSE_BUTTON": [
                '#closeModalButton',
                '.LEGACY_MODAL_closeButton',
                'button[role="button"]',
                '[aria-label="Close"]'
            ],
            "BILL_PAYER": '.Select-value-label',
            "AMOUNT": 'input[name="amount"]',
            "DATE": 'input[value*="/"]',
            "NOTE": 'textarea[name="note"]',
            "ALREADY_PAID": 'input[name="alreadyPaid"]'
        }
    }
}

# Set up logging
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
    """Class for extracting deposit information from Famly system."""
    
    def __init__(self, headless=False, debug=False):
        """Initialize the extractor.
        
        Args:
            headless (bool): Run browser in headless mode
            debug (bool): Enable debug logging and visible browser
        """
        self.headless = headless and not debug
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)
        
        self.driver = None
        self.deposits = []
        self.extracted_data = []
        self.setup_driver()
    
    def setup_driver(self):
        """Configure and initialize the WebDriver."""
        logger.info("Setting up WebDriver...")
        
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless")
        
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        # Add user agent to avoid detection
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")
        
        if self.debug:
            chrome_options.add_argument("--auto-open-devtools-for-tabs")
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.maximize_window()
        
        # Define wait strategy
        self.wait = WebDriverWait(self.driver, CONFIG["DEFAULT_TIMEOUT"])
        
        logger.info("WebDriver setup complete")
    
    def login(self, username, password):
        """Log in to the Famly system.
        
        Args:
            username (str): User email
            password (str): User password
            
        Returns:
            bool: True if login successful
        """
        logger.info("Logging in to Famly...")
        
        try:
            # Navigate to login page
            self.driver.get(CONFIG["BASE_URL"])
            
            # Wait for login form to load
            email_input = self.wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, CONFIG["SELECTORS"]["LOGIN"]["EMAIL_INPUT"])
            ))
            
            # Enter credentials
            email_input.clear()
            email_input.send_keys(username)
            
            password_input = self.driver.find_element(
                By.CSS_SELECTOR, CONFIG["SELECTORS"]["LOGIN"]["PASSWORD_INPUT"]
            )
            password_input.clear()
            password_input.send_keys(password)
            
            # Click login button
            login_button = self.driver.find_element(
                By.CSS_SELECTOR, CONFIG["SELECTORS"]["LOGIN"]["LOGIN_BUTTON"]
            )
            login_button.click()
            
            # Wait for login to complete - look for an element that indicates successful login
            # You might need to adjust this selector based on the actual Famly dashboard
            self.wait.until(EC.url_changes(CONFIG["BASE_URL"]))
            
            logger.info("Login successful")
            return True
            
        except TimeoutException:
            logger.error("Login failed: Timeout waiting for elements")
            return False
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            return False
    
    def navigate_to_deposits_page(self):
        """Navigate to the deposits page."""
        logger.info("Navigating to deposits page...")
        
        try:
            # Navigate directly to the deposits URL
            self.driver.get(CONFIG["DEPOSITS_URL"])
            
            # Wait for the page to load
            time.sleep(2)  # Allow time for the page to load
            
            # You may need to add additional navigation steps depending on the actual UI
            
            logger.info("Navigation to deposits page complete")
            return True
            
        except Exception as e:
            logger.error(f"Navigation failed: {str(e)}")
            return False
    
    def find_deposits(self):
        """Find all deposits on the page.
        
        Returns:
            list: List of deposit objects
        """
        logger.info("Finding deposits on page...")
        
        try:
            # Execute JavaScript to find deposits
            deposits = self.driver.execute_script("""
                function findDeposits() {
                    // Try specific selectors first
                    const containerSelectors = arguments[0];
                    let containers = [];
                    
                    for (const selector of containerSelectors) {
                        try {
                            const elements = document.querySelectorAll(selector);
                            if (elements.length > 0) {
                                containers = Array.from(elements).filter(container => 
                                    container.textContent.includes('Deposit')
                                );
                                break;
                            }
                        } catch (error) {
                            console.error(`Selector error: ${error.message}`);
                        }
                    }
                    
                    // If no containers found, try generic approach
                    if (containers.length === 0) {
                        console.log('No containers found with direct selectors, using generic approach');
                        
                        // Find all "Deposit" paragraphs
                        const depositTexts = Array.from(document.querySelectorAll('p'))
                            .filter(p => p.textContent.trim() === 'Deposit');
                        
                        for (const depositText of depositTexts) {
                            // Navigate up to find container
                            let current = depositText;
                            let containerFound = false;
                            
                            for (let i = 0; i < 8 && current.parentElement; i++) {
                                current = current.parentElement;
                                
                                // Check if this element contains both deposit text and amount info
                                if (current.textContent.includes('Deposit') && 
                                    (current.textContent.includes('€') || 
                                     current.textContent.includes('$') || 
                                     current.textContent.includes('£') || 
                                     /\\d+\\.\\d+|\\d+,\\d+/.test(current.textContent))) {
                                    containers.push(current);
                                    containerFound = true;
                                    break;
                                }
                            }
                        }
                    }
                    
                    console.log(`Found ${containers.length} deposit containers`);
                    
                    // Extract basic information from each container
                    return containers.map((container, index) => {
                        const paragraphs = Array.from(container.querySelectorAll('p'));
                        const smallElements = Array.from(container.querySelectorAll('small'));
                        
                        // Check for Return text
                        const hasBeenReturned = paragraphs.some(p => p.textContent.trim() === 'Return') || 
                                                container.textContent.includes('Return');
                        
                        // Find currency and amount
                        let currency = '';
                        let amount = '';
                        
                        // Look for currency symbol
                        for (const symbol of arguments[1]) {
                            const currencyParagraph = paragraphs.find(p => p.textContent.trim() === symbol);
                            if (currencyParagraph) {
                                currency = symbol;
                                
                                // Find amount paragraph (next to currency)
                                const currencyIndex = paragraphs.indexOf(currencyParagraph);
                                if (currencyIndex >= 0 && currencyIndex < paragraphs.length - 1) {
                                    const nextParagraph = paragraphs[currencyIndex + 1];
                                    if (/[\\d,.]+/.test(nextParagraph.textContent.trim())) {
                                        amount = nextParagraph.textContent.trim();
                                        break;
                                    }
                                }
                            }
                        }
                        
                        // If not found, look for combined format
                        if (!amount) {
                            const amountParagraph = paragraphs.find(p => 
                                /^[€$£]?\\s*[\\d,.]+$/.test(p.textContent.trim())
                            );
                            
                            if (amountParagraph) {
                                const text = amountParagraph.textContent.trim();
                                const match = text.match(/^([€$£]?)\\s*([\\d,.]+)$/);
                                if (match) {
                                    currency = match[1] || '';
                                    amount = match[2] || text;
                                } else {
                                    amount = text;
                                }
                            }
                        }
                        
                        // Get deposit status
                        let depositStatus = '';
                        const depositParagraph = paragraphs.find(p => p.textContent.trim() === 'Deposit');
                        if (depositParagraph) {
                            // Find small element near deposit paragraph
                            const depositParent = depositParagraph.parentElement;
                            if (depositParent) {
                                const smallInParent = depositParent.querySelector('small');
                                if (smallInParent) {
                                    depositStatus = smallInParent.textContent.trim();
                                }
                            }
                        }
                        
                        // Get return status if applicable
                        let returnStatus = '';
                        if (hasBeenReturned) {
                            const returnParagraph = paragraphs.find(p => p.textContent.trim() === 'Return');
                            if (returnParagraph) {
                                const returnParent = returnParagraph.parentElement;
                                if (returnParent) {
                                    const smallInParent = returnParent.querySelector('small');
                                    if (smallInParent) {
                                        returnStatus = smallInParent.textContent.trim();
                                    }
                                }
                            }
                        }
                        
                        return {
                            index: index + 1,
                            xpath: getXPath(container),
                            amount: amount,
                            currency: currency,
                            depositStatus: depositStatus,
                            hasBeenReturned: hasBeenReturned,
                            returnStatus: returnStatus
                        };
                    });
                }
                
                // Helper function to get XPath for an element
                function getXPath(element) {
                    if (element.id !== '')
                        return `//*[@id="${element.id}"]`;
                    
                    if (element === document.body)
                        return '/html/body';
                    
                    let ix = 0;
                    const siblings = element.parentNode.childNodes;
                    
                    for (let i = 0; i < siblings.length; i++) {
                        const sibling = siblings[i];
                        
                        if (sibling === element)
                            return getXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                        
                        if (sibling.nodeType === 1 && sibling.tagName === element.tagName)
                            ix++;
                    }
                }
                
                return findDeposits();
            """, CONFIG["SELECTORS"]["DEPOSITS"]["CONTAINERS"], CONFIG["SELECTORS"]["DEPOSITS"]["CURRENCY_SYMBOLS"])
            
            self.deposits = deposits
            logger.info(f"Found {len(deposits)} deposits")
            
            # Log the first few deposits for verification
            for i, deposit in enumerate(deposits[:3]):
                logger.debug(f"Deposit #{i+1}: {deposit['currency']}{deposit['amount']} - Status: {deposit['depositStatus']}")
                
            return deposits
            
        except Exception as e:
            logger.error(f"Error finding deposits: {str(e)}")
            return []
    
    def extract_deposit_details(self, deposit):
        """Extract detailed information for a single deposit.
        
        Args:
            deposit (dict): Deposit object with basic information
            
        Returns:
            dict: Deposit object with detailed information
        """
        logger.debug(f"Extracting details for deposit #{deposit['index']}: {deposit['currency']}{deposit['amount']}")
        
        detailed_deposit = {
            "index": deposit["index"],
            "amount": deposit["amount"].replace(",", ""),
            "currency": deposit["currency"],
            "depositStatus": deposit["depositStatus"],
            "hasBeenReturned": deposit["hasBeenReturned"],
            "returnStatus": deposit["returnStatus"],
            "billPayer": "",
            "formAmount": "",
            "depositDate": "",
            "note": "",
            "alreadyPaid": False,
            "extractedBy": CONFIG["USER"],
            "extractedAt": CONFIG["TIMESTAMP"],
            "errorMessage": ""
        }
        
        retry_count = 0
        while retry_count < CONFIG["RETRY_ATTEMPTS"]:
            try:
                # Find element using XPath
                element = self.driver.find_element(By.XPATH, deposit["xpath"])
                
                # Click on the deposit
                self.driver.execute_script("arguments[0].click();", element)
                logger.debug(f"Clicked on deposit #{deposit['index']}")
                
                # Wait for modal to appear
                time.sleep(CONFIG["MODAL_LOAD_DELAY"])
                
                # Check for modal presence
                modal_found = False
                for selector in CONFIG["SELECTORS"]["MODAL"]["CONTAINER"]:
                    try:
                        modal = self.driver.find_element(By.CSS_SELECTOR, selector)
                        if modal.is_displayed():
                            modal_found = True
                            break
                    except NoSuchElementException:
                        continue
                
                if not modal_found:
                    logger.warning(f"Modal not found for deposit #{deposit['index']}, retrying...")
                    retry_count += 1
                    continue
                
                # Extract data from modal
                try:
                    # Bill payer
                    try:
                        bill_payer_element = self.driver.find_element(
                            By.CSS_SELECTOR, CONFIG["SELECTORS"]["MODAL"]["BILL_PAYER"]
                        )
                        detailed_deposit["billPayer"] = bill_payer_element.text.strip()
                    except NoSuchElementException:
                        logger.debug(f"Bill payer element not found for deposit #{deposit['index']}")
                    
                    # Amount
                    try:
                        amount_input = self.driver.find_element(
                            By.CSS_SELECTOR, CONFIG["SELECTORS"]["MODAL"]["AMOUNT"]
                        )
                        detailed_deposit["formAmount"] = amount_input.get_attribute("value")
                    except NoSuchElementException:
                        logger.debug(f"Amount input not found for deposit #{deposit['index']}")
                    
                    # Date
                    try:
                        date_input = self.driver.find_element(
                            By.CSS_SELECTOR, CONFIG["SELECTORS"]["MODAL"]["DATE"]
                        )
                        detailed_deposit["depositDate"] = date_input.get_attribute("value")
                    except NoSuchElementException:
                        logger.debug(f"Date input not found for deposit #{deposit['index']}")
                    
                    # Note
                    try:
                        note_textarea = self.driver.find_element(
                            By.CSS_SELECTOR, CONFIG["SELECTORS"]["MODAL"]["NOTE"]
                        )
                        detailed_deposit["note"] = note_textarea.get_attribute("value")
                    except NoSuchElementException:
                        logger.debug(f"Note textarea not found for deposit #{deposit['index']}")
                    
                    # Already paid
                    try:
                        already_paid_checkbox = self.driver.find_element(
                            By.CSS_SELECTOR, CONFIG["SELECTORS"]["MODAL"]["ALREADY_PAID"]
                        )
                        detailed_deposit["alreadyPaid"] = already_paid_checkbox.is_selected()
                    except NoSuchElementException:
                        logger.debug(f"Already paid checkbox not found for deposit #{deposit['index']}")
                    
                except Exception as e:
                    logger.error(f"Error extracting modal data for deposit #{deposit['index']}: {str(e)}")
                    detailed_deposit["errorMessage"] = f"Modal data extraction error: {str(e)}"
                
                # Close modal
                for selector in CONFIG["SELECTORS"]["MODAL"]["CLOSE_BUTTON"]:
                    try:
                        close_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                        if close_button.is_displayed():
                            close_button.click()
                            logger.debug(f"Closed modal for deposit #{deposit['index']}")
                            time.sleep(CONFIG["DELAY_BETWEEN_ACTIONS"])
                            break
                    except:
                        continue
                
                # Try ESC key if button click didn't work
                try:
                    self.driver.find_element(By.CSS_SELECTOR, CONFIG["SELECTORS"]["MODAL"]["CONTAINER"][0])
                    self.driver.find_element(By.TAG_NAME, "body").send_keys(webdriver.Keys.ESCAPE)
                    logger.debug(f"Used ESC key to close modal for deposit #{deposit['index']}")
                except:
                    pass
                
                # Success!
                break
                
            except StaleElementReferenceException:
                logger.warning(f"Stale element reference for deposit #{deposit['index']}, retrying...")
                retry_count += 1
                time.sleep(1)
            except ElementClickInterceptedException:
                logger.warning(f"Click intercepted for deposit #{deposit['index']}, retrying...")
                retry_count += 1
                time.sleep(1)
            except Exception as e:
                logger.error(f"Error processing deposit #{deposit['index']}: {str(e)}")
                detailed_deposit["errorMessage"] = str(e)
                break
        
        if retry_count >= CONFIG["RETRY_ATTEMPTS"]:
            detailed_deposit["errorMessage"] = f"Failed after {CONFIG['RETRY_ATTEMPTS']} attempts"
        
        return detailed_deposit
    
    def extract_all_deposits(self):
        """Extract detailed information for all deposits.
        
        Returns:
            list: List of deposits with detailed information
        """
        logger.info(f"Extracting details for {len(self.deposits)} deposits...")
        
        self.extracted_data = []
        
        # Use tqdm for a progress bar
        for deposit in tqdm(self.deposits, desc="Extracting deposits"):
            detailed_deposit = self.extract_deposit_details(deposit)
            self.extracted_data.append(detailed_deposit)
            
            # Small delay to avoid overwhelming the page
            time.sleep(CONFIG["DELAY_BETWEEN_ACTIONS"])
        
        logger.info(f"Extracted details for {len(self.extracted_data)} deposits")
        return self.extracted_data
    
    def export_to_csv(self, output_file):
        """Export extracted data to CSV.
        
        Args:
            output_file (str): Path to output CSV file
            
        Returns:
            bool: True if export successful
        """
        logger.info(f"Exporting data to CSV: {output_file}")
        
        if not self.extracted_data:
            logger.warning("No data to export")
            return False
        
        try:
            # Convert to DataFrame for easy CSV export
            df = pd.DataFrame(self.extracted_data)
            
            # Save to CSV
            df.to_csv(output_file, index=False, quoting=csv.QUOTE_ALL)
            
            logger.info(f"Successfully exported {len(self.extracted_data)} deposits to {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"Export failed: {str(e)}")
            return False
    
    def cleanup(self):
        """Clean up resources."""
        logger.info("Cleaning up...")
        
        if self.driver:
            self.driver.quit()
            self.driver = None
        
        logger.info("Cleanup complete")
    
    def run(self, username, password, output_file):
        """Run the complete extraction process.
        
        Args:
            username (str): User email
            password (str): User password
            output_file (str): Path to output CSV file
            
        Returns:
            dict: Result information
        """
        try:
            # Login
            if not self.login(username, password):
                return {"success": False, "error": "Login failed"}
            
            # Navigate to deposits page
            if not self.navigate_to_deposits_page():
                return {"success": False, "error": "Navigation failed"}
            
            # Find deposits
            self.find_deposits()
            if not self.deposits:
                return {"success": False, "error": "No deposits found"}
            
            # Extract deposit details
            self.extract_all_deposits()
            
            # Export to CSV
            if not self.export_to_csv(output_file):
                return {"success": False, "error": "Export failed"}
            
            return {
                "success": True,
                "count": len(self.extracted_data),
                "output_file": output_file
            }
            
        except Exception as e:
            logger.error(f"Extraction failed: {str(e)}")
            return {"success": False, "error": str(e)}
            
        finally:
            self.cleanup()


def main():
    """Main entry point for the script."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Extract deposit information from Famly system")
    parser.add_argument("-u", "--username", help="Famly login email")
    parser.add_argument("-p", "--password", help="Famly login password")
    parser.add_argument("-o", "--output", default="famly_deposits.csv", help="Output CSV file")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()
    
    # Get credentials if not provided
    username = args.username
    password = args.password
    
    if not username:
        username = input("Enter your Famly login email: ")
    
    if not password:
        password = getpass("Enter your Famly login password: ")
    
    # Create and run extractor
    extractor = FamlyDepositExtractor(headless=args.headless, debug=args.debug)
    result = extractor.run(username, password, args.output)
    
    if result["success"]:
        print(f"\n✅ Extraction completed successfully!")
        print(f"📄 {result['count']} deposits exported to {result['output_file']}")
        return 0
    else:
        print(f"\n❌ Extraction failed: {result['error']}")
        return 1


if __name__ == "__main__":
    sys.exit(main())