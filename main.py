#!/usr/bin/env python3
"""
Famly Deposit Extractor

A script to extract deposit information from a specific child's profile in the Famly system.
Uses the exact same logic as the original JavaScript DepositExtractor.

Usage:
    python famly_deposit_extractor.py --username <email> --password <password> --child-id <id> --output <filename.csv>

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
    StaleElementReferenceException,
    JavascriptException
)
from webdriver_manager.chrome import ChromeDriverManager

# Configuration with updated timestamp and user
CONFIG = {
    "BASE_URL": "https://app.famly.co/#/login",
    "CHILD_PROFILE_URL_TEMPLATE": "https://app.famly.co/#/account/childProfile/{}/plansAndInvoices",
    "USER": "wolketich",
    "TIMESTAMP": "2025-04-28 14:57:50",  # Updated as provided
    "DEFAULT_TIMEOUT": 25,
    "PAGE_LOAD_WAIT": 7,
    "RETRY_ATTEMPTS": 3,
    "DELAY_BETWEEN_ACTIONS": 1.0,
    "MODAL_LOAD_DELAY": 2.0,
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
        "DEPOSITS": {
            "CONTAINERS": [
                '.sc-beqWaB.sc-eIoBCF.bUiODS.iDrAoK',
                '[class*="sc-beqWaB"][class*="sc-eIoBCF"]'
            ],
            "DEPOSIT_TEXT": 'p:contains("Deposit")',
            "RETURN_TEXT": 'p:contains("Return")',
            "CURRENCY_SYMBOLS": ['€', '$', '£']
        },
        "MODAL": {
            "CONTAINER": [
                '.LEGACY_MODAL_groupActionModal',
                '[role="dialog"]',
                '.modal',
                'form',
                '[data-e2e-class="modal-header"]'
            ],
            "CLOSE_BUTTON": [
                '#closeModalButton',
                '.LEGACY_MODAL_closeButton',
                'button[role="button"]',
                'button:contains("Close")',
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
        """Initialize the extractor."""
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
            chrome_options.add_argument("--headless=new")
        
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        # Enable JavaScript
        chrome_options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.javascript": 1
        })
        
        # Disable animations for better stability
        chrome_options.add_argument("--disable-animations")
        
        if self.debug:
            chrome_options.add_argument("--auto-open-devtools-for-tabs")
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.maximize_window()
        
        # Define wait strategy
        self.wait = WebDriverWait(self.driver, CONFIG["DEFAULT_TIMEOUT"])
        
        logger.info("WebDriver setup complete")
    
    def login(self, username, password):
        """Log in to the Famly system."""
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
            
            # Wait for login to complete - check for URL change
            self.wait.until(EC.url_changes(CONFIG["BASE_URL"]))
            
            # Additional verification
            timeout = time.time() + CONFIG["DEFAULT_TIMEOUT"]
            while time.time() < timeout:
                if "login" not in self.driver.current_url.lower():
                    logger.info("Login successful")
                    return True
                time.sleep(0.5)
            
            logger.error("Login failed: Still on login page after timeout")
            return False
            
        except TimeoutException:
            logger.error("Login failed: Timeout waiting for elements")
            return False
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            return False
    
    def navigate_to_child_profile(self, child_id):
        """Navigate to the specified child's profile page."""
        logger.info(f"Navigating to child profile with ID: {child_id}...")
        
        try:
            # Format URL with child ID
            url = CONFIG["CHILD_PROFILE_URL_TEMPLATE"].format(child_id)
            logger.info(f"Navigating to URL: {url}")
            
            # Navigate to the URL
            self.driver.get(url)
            
            # Wait for the page to load
            logger.info(f"Waiting {CONFIG['PAGE_LOAD_WAIT']} seconds for initial page load...")
            time.sleep(CONFIG["PAGE_LOAD_WAIT"])
            
            # Verify page loaded by checking for specific elements
            page_loaded = False
            for selector in CONFIG["SELECTORS"]["PAGE_READY"]:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements and len(elements) > 0:
                        logger.info(f"Page load confirmed with selector: {selector}")
                        page_loaded = True
                        break
                except Exception:
                    continue
            
            if not page_loaded:
                logger.warning("Could not confirm page load with selectors. Will continue anyway.")
            
            # Additional wait for dynamic content
            time.sleep(CONFIG["DELAY_BETWEEN_ACTIONS"])
            
            return True
            
        except Exception as e:
            logger.error(f"Navigation failed: {str(e)}")
            return False
    
    def is_page_fully_loaded(self):
        """Check if the page is fully loaded."""
        try:
            # Check if document.readyState is complete
            ready_state = self.driver.execute_script("return document.readyState")
            
            # Check if jQuery is active (if present)
            jquery_active = self.driver.execute_script(
                "return typeof jQuery !== 'undefined' ? jQuery.active === 0 : true"
            )
            
            # Check if there are no active AJAX requests
            ajax_complete = self.driver.execute_script(
                "return typeof window.performance !== 'undefined' && "
                "typeof window.performance.getEntriesByType !== 'undefined' ? "
                "window.performance.getEntriesByType('resource').every(r => r.responseEnd > 0) : true"
            )
            
            return ready_state == "complete" and jquery_active and ajax_complete
        except Exception as e:
            logger.warning(f"Error checking page load status: {str(e)}")
            return False

    def find_deposits(self):
        """Find all deposits on the page using exact original DepositExtractor logic."""
        logger.info("Finding deposits using original DepositExtractor logic...")
        
        # Make sure page is fully loaded
        max_wait = time.time() + 20
        while not self.is_page_fully_loaded() and time.time() < max_wait:
            logger.info("Waiting for page to fully load...")
            time.sleep(1)
        
        # Additional safety delay
        time.sleep(3)
        
        # Inject the exact original DepositExtractor code
        try:
            script = """
            // Execute the original DepositExtractor logic
            const extractorResult = (function() {
                'use strict';
                
                // Configuration settings - directly from the original code
                const CONFIG = {
                    SELECTORS: {
                        DEPOSITS: {
                            CONTAINERS: [
                                '.sc-beqWaB.sc-eIoBCF.bUiODS.iDrAoK',
                                '[class*="sc-beqWaB"][class*="sc-eIoBCF"]',
                                '.sc-dxnOzg',
                                '.sc-beqWaB.sc-eKNumk.sc-hbpqLB'
                            ],
                            CURRENCY_SYMBOLS: ['€', '$', '£']
                        }
                    }
                };
                
                // Utility functions - directly from original code
                const DOMUtils = {
                    querySelector: function(selector, root = document) {
                        try {
                            return root.querySelector(selector);
                        } catch (error) {
                            console.error(`Invalid selector: ${selector}`, error);
                            return null;
                        }
                    },
                    
                    querySelectorAll: function(selector, root = document) {
                        try {
                            return Array.from(root.querySelectorAll(selector));
                        } catch (error) {
                            console.error(`Invalid selector: ${selector}`, error);
                            return [];
                        }
                    },
                    
                    elementContainsText: function(element, text) {
                        return element.textContent.trim().includes(text);
                    },
                    
                    findElementsByText: function(tagName, text, root = document) {
                        return this.querySelectorAll(tagName, root)
                            .filter(el => el.textContent.trim() === text);
                    },
                    
                    findAncestor: function(element, predicate, maxDepth = 10) {
                        let current = element;
                        let depth = 0;
                        
                        while (current && depth < maxDepth) {
                            if (predicate(current)) {
                                return current;
                            }
                            current = current.parentElement;
                            depth++;
                        }
                        
                        return null;
                    }
                };

                // Find deposit containers - exactly as in the original code
                function findDepositContainers() {
                    // Try direct selectors first
                    const containerSelectors = CONFIG.SELECTORS.DEPOSITS.CONTAINERS.join(', ');
                    let containers = DOMUtils.querySelectorAll(containerSelectors);
                    
                    console.log(`Found ${containers.length} potential containers with direct selectors`);
                    
                    // Filter to only include those with "Deposit" text
                    containers = containers.filter(container => 
                        DOMUtils.elementContainsText(container, 'Deposit')
                    );
                    
                    console.log(`Found ${containers.length} containers with "Deposit" text`);
                    
                    // If no containers found, try generic approach
                    if (containers.length === 0) {
                        return findDepositContainersGeneric();
                    }
                    
                    return containers;
                }
                
                // Generic approach - exactly as in the original code
                function findDepositContainersGeneric() {
                    // Find all "Deposit" paragraphs
                    const depositTexts = DOMUtils.findElementsByText('p', 'Deposit');
                    console.log(`Found ${depositTexts.length} deposit texts, searching for containers...`);
                    
                    const containers = [];
                    
                    // For each deposit text, find its container
                    for (const depositText of depositTexts) {
                        const container = DOMUtils.findAncestor(
                            depositText,
                            el => {
                                // Container must have both deposit text and amount info
                                const hasDeposit = DOMUtils.elementContainsText(el, 'Deposit');
                                const hasAmount = CONFIG.SELECTORS.DEPOSITS.CURRENCY_SYMBOLS.some(
                                    symbol => DOMUtils.elementContainsText(el, symbol)
                                );
                                const hasNumbers = /\\d+\\.\\d+|\\d+,\\d+/.test(el.textContent);
                                
                                return hasDeposit && (hasAmount || hasNumbers);
                            },
                            8 // Check up to 8 levels up
                        );
                        
                        if (container && !containers.includes(container)) {
                            containers.push(container);
                        }
                    }
                    
                    console.log(`Found ${containers.length} deposit containers using generic approach`);
                    return containers;
                }
                
                // Extract deposit information - exactly as in the original code
                function extractDepositInfo(container, index) {
                    const paragraphs = DOMUtils.querySelectorAll('p', container);
                    const smallElements = DOMUtils.querySelectorAll('small', container);
                    
                    // Check for Return text
                    const hasBeenReturned = paragraphs.some(p => p.textContent.trim() === 'Return') || 
                                          DOMUtils.elementContainsText(container, 'Return');
                    
                    // Find currency and amount
                    let currency = '';
                    let amount = '';
                    
                    // Check for standalone currency symbols
                    for (const symbol of CONFIG.SELECTORS.DEPOSITS.CURRENCY_SYMBOLS) {
                        const currencyParagraph = paragraphs.find(p => p.textContent.trim() === symbol);
                        if (currencyParagraph) {
                            currency = symbol;
                            
                            // Look for amount in adjacent paragraph
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
                        // Find small element following deposit paragraph
                        const depositParent = depositParagraph.parentElement;
                        if (depositParent) {
                            const smallInParent = DOMUtils.querySelector('small', depositParent);
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
                                const smallInParent = DOMUtils.querySelector('small', returnParent);
                                if (smallInParent) {
                                    returnStatus = smallInParent.textContent.trim();
                                }
                            }
                        }
                    }
                    
                    // Generate XPath for the element for easier identification later
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
                    
                    return {
                        index,
                        type: 'Deposit',
                        amount,
                        currency,
                        depositStatus,
                        hasBeenReturned,
                        returnStatus,
                        xpath: getXPath(container),
                        outerHTML: container.outerHTML.substring(0, 500) // For debugging
                    };
                }
                
                // Find all deposits on the page - exactly as in the original code
                function findAllDeposits() {
                    const containers = findDepositContainers();
                    console.log(`Processing ${containers.length} deposit containers`);
                    return containers.map((container, index) => 
                        extractDepositInfo(container, index + 1)
                    );
                }
                
                // Run the deposit finder
                try {
                    // Capture page info for debugging
                    const pageTitle = document.title;
                    const url = window.location.href;
                    const pageContent = document.body.textContent;
                    const depositParas = document.querySelectorAll('p');
                    console.log(`Page title: ${pageTitle}`);
                    console.log(`URL: ${url}`);
                    console.log(`Found ${depositParas.length} paragraphs in total`);
                    
                    // Count how many paragraphs contain the word "Deposit"
                    const depositTextCount = Array.from(depositParas).filter(p => 
                        p.textContent.includes('Deposit')
                    ).length;
                    console.log(`Found ${depositTextCount} paragraphs containing "Deposit"`);
                    
                    // Find all deposits
                    const deposits = findAllDeposits();
                    console.log(`Found ${deposits.length} deposits total`);
                    
                    return {
                        success: true,
                        deposits: deposits,
                        debug: {
                            title: pageTitle,
                            url: url,
                            depositTextCount,
                            totalParagraphs: depositParas.length
                        }
                    };
                } catch (error) {
                    console.error("Error finding deposits:", error);
                    return {
                        success: false,
                        error: error.toString()
                    };
                }
            })();
            
            return extractorResult;
            """
            
            # Execute the script
            result = self.driver.execute_script(script)
            
            if result.get('success'):
                deposits = result.get('deposits', [])
                debug_info = result.get('debug', {})
                
                logger.info(f"Found {len(deposits)} deposits")
                logger.info(f"Page title: {debug_info.get('title', 'Unknown')}")
                logger.info(f"Found {debug_info.get('depositTextCount', 0)} paragraphs containing 'Deposit'")
                logger.info(f"Total paragraphs: {debug_info.get('totalParagraphs', 0)}")
                
                if len(deposits) == 0:
                    logger.warning("No deposits found with JavaScript finder")
                
                self.deposits = deposits
                return deposits
            else:
                logger.error(f"JavaScript error: {result.get('error', 'Unknown error')}")
                return []
                
        except Exception as e:
            logger.error(f"Error running JavaScript deposit finder: {str(e)}")
            return []
    
    def extract_deposit_details(self, deposit):
        """Extract detailed information for a single deposit."""
        logger.debug(f"Extracting details for deposit #{deposit['index']}: {deposit.get('currency', '')}{deposit.get('amount', '')}")
        
        detailed_deposit = {
            "index": deposit["index"],
            "amount": deposit.get("amount", "").replace(",", ""),
            "currency": deposit.get("currency", ""),
            "depositStatus": deposit.get("depositStatus", ""),
            "hasBeenReturned": deposit.get("hasBeenReturned", False),
            "returnStatus": deposit.get("returnStatus", ""),
            "billPayer": "",
            "formAmount": "",
            "depositDate": "",
            "note": "",
            "alreadyPaid": False,
            "extractedBy": CONFIG["USER"],
            "extractedAt": CONFIG["TIMESTAMP"],
            "errorMessage": ""
        }
        
        try:
            # Try to locate element using XPath if available
            if "xpath" in deposit and deposit["xpath"]:
                try:
                    element = self.driver.find_element(By.XPATH, deposit["xpath"])
                    logger.debug(f"Found element using XPath for deposit #{deposit['index']}")
                    self.driver.execute_script("arguments[0].click();", element)
                except Exception as e:
                    logger.warning(f"Failed to find element using XPath: {str(e)}")
                    # Try an alternative click method directly in JavaScript
                    clicked = self.driver.execute_script("""
                        var depositInfo = arguments[0];
                        
                        // Helper to find deposit elements
                        function findDepositElements() {
                            return Array.from(document.querySelectorAll('p'))
                                .filter(p => p.textContent.trim() === 'Deposit')
                                .map(p => {
                                    // Find container
                                    let container = p;
                                    for (let i = 0; i < 5; i++) {
                                        if (!container.parentElement) break;
                                        container = container.parentElement;
                                        
                                        if (container.textContent.includes(depositInfo.amount)) {
                                            return container;
                                        }
                                    }
                                    return null;
                                })
                                .filter(el => el !== null);
                        }
                        
                        // Find deposits
                        var depositElements = findDepositElements();
                        console.log("Found " + depositElements.length + " deposit elements");
                        
                        // Click the deposit at index
                        if (depositElements.length >= depositInfo.index) {
                            var targetElement = depositElements[depositInfo.index - 1];
                            targetElement.click();
                            return true;
                        }
                        
                        return false;
                    """, deposit)
                    
                    if not clicked:
                        raise Exception("Could not click deposit with alternative method")
            
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
                        logger.debug(f"Modal found with selector: {selector}")
                        break
                except NoSuchElementException:
                    continue
            
            if not modal_found:
                logger.warning(f"Modal not detected for deposit #{deposit['index']}")
                time.sleep(CONFIG["MODAL_LOAD_DELAY"])  # Try waiting longer
            
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
                        logger.debug(f"Closed modal for deposit #{deposit['index']} with button")
                        break
                except:
                    continue
            
            # Try ESC key if button click didn't work
            try:
                # Check if modal is still open
                is_modal_open = False
                for selector in CONFIG["SELECTORS"]["MODAL"]["CONTAINER"]:
                    try:
                        modal = self.driver.find_element(By.CSS_SELECTOR, selector)
                        if modal.is_displayed():
                            is_modal_open = True
                            break
                    except:
                        continue
                
                if is_modal_open:
                    logger.debug(f"Using ESC key to close modal for deposit #{deposit['index']}")
                    webdriver.ActionChains(self.driver).send_keys(webdriver.Keys.ESCAPE).perform()
            except:
                pass
            
            # Wait for modal to close
            time.sleep(CONFIG["DELAY_BETWEEN_ACTIONS"])
            
        except Exception as e:
            logger.error(f"Error processing deposit #{deposit['index']}: {str(e)}")
            detailed_deposit["errorMessage"] = str(e)
        
        return detailed_deposit
    
    def extract_all_deposits(self):
        """Extract detailed information for all deposits."""
        if not self.deposits:
            logger.warning("No deposits found to extract details from")
            return []
            
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
        """Export extracted data to CSV."""
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
    
    def run(self, username, password, child_id, output_file):
        """Run the complete extraction process."""
        try:
            # Login
            if not self.login(username, password):
                return {"success": False, "error": "Login failed"}
            
            # Navigate to child profile
            if not self.navigate_to_child_profile(child_id):
                return {"success": False, "error": "Navigation to child profile failed"}
            
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
    parser.add_argument("-c", "--child-id", required=True, help="Child ID")
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
    result = extractor.run(username, password, args.child_id, args.output)
    
    if result["success"]:
        print(f"\n✅ Extraction completed successfully!")
        print(f"📄 {result['count']} deposits exported to {result['output_file']}")
        return 0
    else:
        print(f"\n❌ Extraction failed: {result['error']}")
        return 1


if __name__ == "__main__":
    sys.exit(main())