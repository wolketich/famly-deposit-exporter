#!/usr/bin/env python3
"""
Famly Deposit Extractor with Batch Processing

A script to extract deposit information from multiple children's profiles in the Famly system.
Processes a CSV file containing child names and IDs.

Usage:
    python famly_deposit_extractor.py --username <email> --password <password> --input <children.csv> [--output-dir <dir>]

CSV Format:
    name,child_id
    Example:
    John Smith,123456
    Jane Doe,789012

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
import traceback
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

# Configuration - All time delays are in seconds
CONFIG = {
    "BASE_URL": "https://app.famly.co/#/login",
    "CHILD_PROFILE_URL_TEMPLATE": "https://app.famly.co/#/account/childProfile/{}/plansAndInvoices",
    "USER": "wolketich",
    "TIMESTAMP": "2025-04-28 16:15:37",  # Updated timestamp
    "TIMEOUTS": {
        "DEFAULT": 25,         # Default timeout for WebDriverWait
        "PAGE_LOAD": 3,        # Wait after initial page navigation
        "LOGIN": 15,           # Wait for login to complete
        "MODAL_APPEAR": 1.0,   # Wait for modal to appear after clicking
        "MODAL_CLOSE": 0.5,    # Wait after closing modal
        "BETWEEN_ACTIONS": 0.3, # Delay between UI actions
        "BETWEEN_CHILDREN": 3.0 # Delay between processing different children
    },
    "RETRY": {
        "ATTEMPTS": 3,          # Number of retry attempts
        "DELAY": 1.0            # Delay between retries
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
            "button",
            "div[role='button']"
        ],
        "DEPOSITS": {
            "CONTAINERS": [
                '.sc-beqWaB.sc-joHvVE.bUiODS.cmkCrL',  # Updated selector
                '.sc-beqWaB.sc-iYdbym.sc-llnzWd',      # Alternative selector
                '[class*="sc-beqWaB"][class*="sc-eIoBCF"]',
                '[class*="MuiStack-root"]'
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
    
    def __init__(self, headless=False, debug=False, output_dir="output"):
        """Initialize the extractor.
        
        Args:
            headless (bool): Run browser in headless mode
            debug (bool): Enable debug logging and visible browser
            output_dir (str): Directory to save output files
        """
        self.headless = headless and not debug
        self.debug = debug
        self.output_dir = output_dir
        
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        if debug:
            logger.setLevel(logging.DEBUG)
        
        self.driver = None
        self.deposits = []
        self.extracted_data = []
        self.state_file = os.path.join(output_dir, "extraction_state.json")
        self.setup_driver()
    
    def setup_driver(self):
        """Configure and initialize the WebDriver with fallback options."""
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
        
        # Try multiple approaches to get ChromeDriver
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            logger.warning(f"ChromeDriverManager failed: {str(e)}, trying local driver")
            try:
                # Try common local paths
                local_driver_paths = [
                    './chromedriver',
                    './chromedriver.exe',
                    '/usr/local/bin/chromedriver'
                ]
                for path in local_driver_paths:
                    if os.path.exists(path):
                        service = Service(path)
                        self.driver = webdriver.Chrome(service=service, options=chrome_options)
                        break
                else:
                    raise Exception("Could not find local chromedriver")
            except Exception as local_error:
                logger.error(f"Local driver failed: {str(local_error)}")
                raise Exception("Failed to initialize ChromeDriver. Please ensure Chrome and ChromeDriver are installed.")
        
        self.driver.maximize_window()
        
        # Define wait strategy
        self.wait = WebDriverWait(self.driver, CONFIG["TIMEOUTS"]["DEFAULT"])
        
        logger.info("WebDriver setup complete")
    
    def login(self, username, password):
        """Log in to the Famly system with retry capability.
        
        Args:
            username (str): User email
            password (str): User password
            
        Returns:
            bool: True if login successful
        """
        logger.info("Logging in to Famly...")
        
        for attempt in range(CONFIG["RETRY"]["ATTEMPTS"]):
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
                timeout = time.time() + CONFIG["TIMEOUTS"]["LOGIN"]
                while time.time() < timeout:
                    if "login" not in self.driver.current_url.lower():
                        logger.info("Login successful")
                        return True
                    time.sleep(0.5)
                
                logger.warning(f"Login attempt {attempt+1} failed: Still on login page after timeout")
                
            except TimeoutException:
                logger.warning(f"Login attempt {attempt+1} failed: Timeout waiting for elements")
            except Exception as e:
                logger.warning(f"Login attempt {attempt+1} failed: {str(e)}")
            
            # Wait before retrying
            if attempt < CONFIG["RETRY"]["ATTEMPTS"] - 1:  # Don't delay after the last attempt
                time.sleep(CONFIG["RETRY"]["DELAY"])
        
        logger.error("All login attempts failed")
        return False
    
    def validate_child_data(self, child_data):
        """Validate a child's data before processing.
        
        Args:
            child_data (dict): Child data with name and ID
            
        Returns:
            list: List of validation errors, empty if valid
        """
        errors = []
        
        # Check required fields
        if 'child_id' not in child_data or not child_data.get('child_id'):
            errors.append("Missing child_id")
        
        # Validate child_id format
        try:
            if 'child_id' in child_data:
                child_id = str(child_data['child_id']).strip()
                if not child_id:
                    errors.append("Empty child_id")
        except Exception as e:
            errors.append(f"Error parsing child_id: {str(e)}")
        
        # Sanitize name
        if 'name' in child_data:
            if not child_data['name']:
                child_data['name'] = f"Unknown-{child_data.get('child_id', 'NoID')}"
            else:
                child_data['name'] = str(child_data['name']).strip()
        else:
            child_data['name'] = f"Unknown-{child_data.get('child_id', 'NoID')}"
        
        return errors
    
    def navigate_to_child_profile(self, child_id, child_name=""):
        """Navigate to the specified child's profile page with retry logic.
        
        Args:
            child_id (str): Child ID
            child_name (str): Child name (for logging)
            
        Returns:
            bool: True if navigation successful
        """
        child_info = f"{child_name} (ID: {child_id})" if child_name else f"ID: {child_id}"
        logger.info(f"Navigating to child profile: {child_info}")
        
        for attempt in range(CONFIG["RETRY"]["ATTEMPTS"]):
            try:
                # Format URL with child ID
                url = CONFIG["CHILD_PROFILE_URL_TEMPLATE"].format(child_id)
                logger.info(f"Navigating to URL: {url}")
                
                # Navigate to the URL
                self.driver.get(url)
                
                # Wait for the page to load
                logger.info(f"Waiting {CONFIG['TIMEOUTS']['PAGE_LOAD']} seconds for initial page load...")
                time.sleep(CONFIG["TIMEOUTS"]["PAGE_LOAD"])
                
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
                    logger.warning(f"Navigation attempt {attempt+1}: Could not confirm page load with selectors.")
                    if attempt < CONFIG["RETRY"]["ATTEMPTS"] - 1:
                        continue
                    else:
                        logger.warning("Will continue anyway despite not confirming page load.")
                
                # Additional wait for dynamic content
                time.sleep(CONFIG["TIMEOUTS"]["BETWEEN_ACTIONS"])
                
                return True
                
            except Exception as e:
                logger.warning(f"Navigation attempt {attempt+1} failed: {str(e)}")
                
                # Check if we need to re-login
                if "login" in self.driver.current_url.lower():
                    logger.warning("Session expired, need to re-login")
                    break  # Break the retry loop to handle re-login at a higher level
            
            # Wait before retrying
            if attempt < CONFIG["RETRY"]["ATTEMPTS"] - 1:
                time.sleep(CONFIG["RETRY"]["DELAY"])
        
        logger.error(f"Failed to navigate to child profile: {child_info} after {CONFIG['RETRY']['ATTEMPTS']} attempts")
        return False
    
    def is_page_fully_loaded(self):
        """Check if the page is fully loaded with enhanced checks.
        
        Returns:
            bool: True if page is fully loaded
        """
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
            
            # Check if deposits section is visible
            deposits_visible = self.driver.execute_script(
                "return document.body.textContent.includes('Deposit')"
            )
            
            return ready_state == "complete" and jquery_active and ajax_complete and deposits_visible
            
        except Exception as e:
            logger.warning(f"Error checking page load status: {str(e)}")
            return False

    def find_deposits(self):
        """Find all deposits on the page using enhanced JavaScript deposit finder.
        
        Returns:
            list: List of deposit objects
        """
        logger.info("Finding deposits using robust deposit finder...")
        
        # Make sure page is fully loaded
        max_wait = time.time() + 20
        while not self.is_page_fully_loaded() and time.time() < max_wait:
            logger.info("Waiting for page to fully load...")
            time.sleep(1)
        
        # Additional safety delay
        time.sleep(CONFIG["TIMEOUTS"]["BETWEEN_ACTIONS"])
        
        # Inject enhanced JavaScript for deposit finding with better return detection
        try:
            script = """
            // Execute enhanced deposit finder with improved return detection
            const extractorResult = (function() {
                'use strict';
                
                // Configuration settings
                const CONFIG = {
                    USER: "wolketich",
                    TIMESTAMP: "2025-04-28 16:15:37",
                    SELECTORS: {
                        DEPOSITS: {
                            CONTAINERS: [
                                '.sc-beqWaB.sc-joHvVE.bUiODS.cmkCrL',
                                '.sc-beqWaB.sc-iYdbym.sc-llnzWd',
                                '[class*="sc-beqWaB"][class*="sc-eIoBCF"]',
                                '[class*="sc-beqWaB"]',
                                '.MuiStack-root'
                            ],
                            CURRENCY_SYMBOLS: ['€', '$', '£']
                        }
                    }
                };
                
                // Utility functions
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

                // Find deposit containers with fallbacks for when selectors fail
                function findDepositContainers() {
                    // Try direct selectors first
                    const containerSelectors = CONFIG.SELECTORS.DEPOSITS.CONTAINERS.join(', ');
                    let containers = [];
                    
                    try {
                        containers = DOMUtils.querySelectorAll(containerSelectors);
                        console.log(`Found ${containers.length} potential containers with direct selectors`);
                    } catch (e) {
                        console.error("Error with selectors:", e);
                    }
                    
                    // Filter to only include those with "Deposit" text
                    containers = containers.filter(container => 
                        DOMUtils.elementContainsText(container, 'Deposit')
                    );
                    
                    console.log(`Found ${containers.length} containers with "Deposit" text`);
                    
                    // If no containers found, try content-based approach
                    if (containers.length === 0) {
                        return findDepositContainersGeneric();
                    }
                    
                    return containers;
                }
                
                // Generic content-based approach for finding deposits
                function findDepositContainersGeneric() {
                    // Find all "Deposit" paragraphs
                    const depositTexts = DOMUtils.findElementsByText('p', 'Deposit');
                    console.log(`Found ${depositTexts.length} deposit texts, searching for containers...`);
                    
                    if (depositTexts.length === 0) {
                        // Try a broader search for any element with Deposit text
                        const allElements = DOMUtils.querySelectorAll('*');
                        const depositElements = allElements.filter(el => 
                            el.textContent.trim() === 'Deposit' && 
                            el.children.length === 0  // Only leaf nodes
                        );
                        console.log(`Broader search found ${depositElements.length} elements with exact "Deposit" text`);
                        
                        if (depositElements.length > 0) {
                            return findContainersFromElements(depositElements);
                        }
                        
                        // Last resort: look for divs that contain Deposit and currency/amount
                        return findDepositDivsByContent();
                    }
                    
                    return findContainersFromElements(depositTexts);
                }
                
                // Find containers from a list of deposit elements
                function findContainersFromElements(elements) {
                    const containers = [];
                    
                    // For each deposit text, find its container
                    for (const depositElement of elements) {
                        const container = DOMUtils.findAncestor(
                            depositElement,
                            el => {
                                // Container must have both deposit text and amount info
                                const hasDeposit = DOMUtils.elementContainsText(el, 'Deposit');
                                const hasAmount = CONFIG.SELECTORS.DEPOSITS.CURRENCY_SYMBOLS.some(
                                    symbol => DOMUtils.elementContainsText(el, symbol)
                                );
                                const hasNumbers = /\\d+\\.\\d+|\\d+,\\d+/.test(el.textContent);
                                
                                return hasDeposit && (hasAmount || hasNumbers);
                            },
                            10 // Check up to 10 levels up
                        );
                        
                        if (container && !containers.includes(container)) {
                            containers.push(container);
                        }
                    }
                    
                    console.log(`Found ${containers.length} deposit containers using findContainersFromElements`);
                    return containers;
                }
                
                // Find deposit divs by content analysis as a last resort
                function findDepositDivsByContent() {
                    const allDivs = DOMUtils.querySelectorAll('div');
                    
                    // Find divs that contain both 'Deposit' and currency/amount pattern
                    const depositDivs = allDivs.filter(div => {
                        if (!div.textContent.includes('Deposit')) return false;
                        
                        // Check for currency pattern
                        const hasCurrency = CONFIG.SELECTORS.DEPOSITS.CURRENCY_SYMBOLS.some(
                            symbol => div.textContent.includes(symbol)
                        );
                        
                        const hasAmount = /\\d+\\.\\d+|\\d+,\\d+/.test(div.textContent);
                        
                        return (hasCurrency || hasAmount) && div.offsetWidth > 100;
                    });
                    
                    console.log(`Found ${depositDivs.length} deposit divs by content analysis`);
                    
                    // De-duplicate by finding the most specific containers
                    const uniqueDivs = [];
                    const seen = new Set();
                    
                    for (const div of depositDivs) {
                        const rect = div.getBoundingClientRect();
                        const signature = `${rect.top.toFixed(0)}_${rect.left.toFixed(0)}_${div.offsetWidth}`;
                        
                        if (!seen.has(signature)) {
                            seen.add(signature);
                            uniqueDivs.push(div);
                        }
                    }
                    
                    return uniqueDivs;
                }
                
                // Extract deposit information with improved Return detection
                function extractDepositInfo(container, index) {
                    // Get all paragraphs and small elements in the container
                    const paragraphs = DOMUtils.querySelectorAll('p', container);
                    const smallElements = DOMUtils.querySelectorAll('small', container);
                    
                    // IMPROVED RETURN DETECTION - START
                    // Method 1: Look for paragraphs with exact 'Return' text
                    const returnParagraphs = paragraphs.filter(p => p.textContent.trim() === 'Return');
                    
                    // Method 2: Look for parent Stack divs that contain Return paragraphs
                    let returnStacks = [];
                    try {
                        const stackDivs = Array.from(container.querySelectorAll('[class*="MuiStack"]'));
                        returnStacks = stackDivs.filter(div => {
                            const p = div.querySelector('p');
                            return p && p.textContent.trim() === 'Return';
                        });
                    } catch (e) {
                        console.log("Error finding MuiStack divs:", e);
                    }
                    
                    // Method 3: Content-based fallback
                    const containerHasReturnText = container.textContent.includes('Return');
                    
                    // Combine all methods for most reliable detection
                    const hasBeenReturned = returnParagraphs.length > 0 || 
                                           returnStacks.length > 0 || 
                                           containerHasReturnText;
                    
                    console.log(`Deposit ${index}: returnParagraphs=${returnParagraphs.length}, returnStacks=${returnStacks.length}, containerHasReturnText=${containerHasReturnText}`);
                    console.log(`Deposit ${index}: hasBeenReturned = ${hasBeenReturned}`);
                    // IMPROVED RETURN DETECTION - END
                    
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
                            
                            // Alternative: look in parent element for numeric content
                            if (!amount) {
                                const parent = currencyParagraph.parentElement;
                                if (parent) {
                                    const siblings = Array.from(parent.children);
                                    const currencyIndex = siblings.indexOf(currencyParagraph);
                                    
                                    if (currencyIndex >= 0 && currencyIndex < siblings.length - 1) {
                                        const nextSibling = siblings[currencyIndex + 1];
                                        if (/^[\\d,.]+$/.test(nextSibling.textContent.trim())) {
                                            amount = nextSibling.textContent.trim();
                                            break;
                                        }
                                    }
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
                        // Try to find return status in small element near Return text
                        if (returnParagraphs.length > 0) {
                            const returnPara = returnParagraphs[0];
                            const parent = returnPara.parentElement;
                            if (parent) {
                                const small = parent.querySelector('small');
                                if (small) {
                                    returnStatus = small.textContent.trim();
                                }
                            }
                        }
                        // Alternative: check stack divs if direct method fails
                        else if (returnStacks.length > 0) {
                            const returnStack = returnStacks[0];
                            const small = returnStack.querySelector('small');
                            if (small) {
                                returnStatus = small.textContent.trim();
                            }
                        }
                        // Final fallback: any small text near "Return" string
                        else if (containerHasReturnText) {
                            // Find text node with "Return" and check nearby small elements
                            const allNodes = [];
                            const walk = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
                            let node;
                            while (node = walk.nextNode()) {
                                if (node.textContent.trim() === 'Return') {
                                    const parentElement = node.parentElement;
                                    if (parentElement) {
                                        const nearbySmall = DOMUtils.querySelectorAll('small', parentElement.parentElement);
                                        if (nearbySmall.length > 0) {
                                            returnStatus = nearbySmall[0].textContent.trim();
                                            break;
                                        }
                                    }
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
                        extractedBy: CONFIG.USER,
                        extractedAt: CONFIG.TIMESTAMP,
                        html: container.outerHTML.substring(0, 200) // Store a preview of the HTML for debugging
                    };
                }
                
                // Find all deposits on the page
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
                    console.log(`Found ${depositParas.length} total paragraphs`);
                    
                    // Count paragraphs with Deposit and Return text
                    const depositTextCount = Array.from(depositParas).filter(p => 
                        p.textContent.includes('Deposit')
                    ).length;
                    const returnTextCount = Array.from(depositParas).filter(p => 
                        p.textContent.includes('Return')
                    ).length;
                    
                    console.log(`Found ${depositTextCount} paragraphs containing "Deposit"`);
                    console.log(`Found ${returnTextCount} paragraphs containing "Return"`);
                    
                    // Find all deposits
                    const deposits = findAllDeposits();
                    console.log(`Found ${deposits.length} deposits total`);
                    
                    // Count returned deposits
                    const returnedCount = deposits.filter(d => d.hasBeenReturned).length;
                    console.log(`Found ${returnedCount} returned deposits`);
                    
                    return {
                        success: true,
                        deposits: deposits,
                        debug: {
                            title: pageTitle,
                            url: url,
                            depositTextCount,
                            returnTextCount,
                            totalParagraphs: depositParas.length,
                            returnedCount
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
                logger.info(f"Found {debug_info.get('returnTextCount', 0)} paragraphs containing 'Return'")
                logger.info(f"Found {debug_info.get('returnedCount', 0)} returned deposits")
                
                if len(deposits) == 0:
                    logger.warning("No deposits found with JavaScript finder")
                
                self.deposits = deposits
                return deposits
            else:
                logger.error(f"JavaScript error: {result.get('error', 'Unknown error')}")
                return []
                
        except Exception as e:
            logger.error(f"Error running JavaScript deposit finder: {str(e)}")
            logger.error(traceback.format_exc())
            return []
    
    def extract_deposit_details(self, deposit):
        """Extract detailed information for a single deposit with enhanced error handling.
        
        Args:
            deposit (dict): Basic deposit information
            
        Returns:
            dict: Detailed deposit information
        """
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
        
        for attempt in range(CONFIG["RETRY"]["ATTEMPTS"]):
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
                                            
                                            const hasAmount = container.textContent.includes(depositInfo.amount);
                                            const hasCurrency = container.textContent.includes(depositInfo.currency);
                                            
                                            if ((hasAmount && depositInfo.amount) || 
                                                (hasCurrency && depositInfo.currency)) {
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
                            
                            // Store previously clicked elements to avoid duplicates
                            if (!window.clickedDepositElements) {
                                window.clickedDepositElements = [];
                            }
                            
                            // Click the deposit at index or find by match
                            if (depositElements.length >= depositInfo.index) {
                                var targetElement = depositElements[depositInfo.index - 1];
                                
                                // Check if we've already clicked this element
                                const alreadyClicked = window.clickedDepositElements.some(
                                    rect => Math.abs(rect.top - targetElement.getBoundingClientRect().top) < 5
                                );
                                
                                if (!alreadyClicked) {
                                    // Store this element as clicked
                                    window.clickedDepositElements.push(targetElement.getBoundingClientRect());
                                    
                                    // Click the element
                                    targetElement.click();
                                    return true;
                                } else {
                                    console.log("Element already clicked, trying next candidate");
                                    // Try the next unclicked element
                                    for (const el of depositElements) {
                                        const rect = el.getBoundingClientRect();
                                        const alreadyClickedThis = window.clickedDepositElements.some(
                                            clicked => Math.abs(clicked.top - rect.top) < 5
                                        );
                                        
                                        if (!alreadyClickedThis) {
                                            window.clickedDepositElements.push(rect);
                                            el.click();
                                            return true;
                                        }
                                    }
                                }
                            }
                            
                            // If we get here, we couldn't find a suitable element to click
                            return false;
                        """, deposit)
                        
                        if not clicked:
                            raise Exception("Could not click deposit with alternative method")
                
                logger.debug(f"Clicked on deposit #{deposit['index']}")
                
                # Wait for modal to appear
                time.sleep(CONFIG["TIMEOUTS"]["MODAL_APPEAR"])
                
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
                    logger.warning(f"Modal not detected for deposit #{deposit['index']} (attempt {attempt+1})")
                    if attempt < CONFIG["RETRY"]["ATTEMPTS"] - 1:
                        time.sleep(CONFIG["RETRY"]["DELAY"])
                        continue
                    else:
                        logger.warning("Modal not found, but will try to extract data anyway")
                
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
                
                # Close modal using multiple methods
                modal_closed = False
                
                # Method 1: Try to click close button
                for selector in CONFIG["SELECTORS"]["MODAL"]["CLOSE_BUTTON"]:
                    try:
                        close_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                        if close_button.is_displayed():
                            close_button.click()
                            logger.debug(f"Closed modal for deposit #{deposit['index']} with button")
                            modal_closed = True
                            break
                    except:
                        continue
                
                # Method 2: Try ESC key if button click didn't work
                if not modal_closed:
                    try:
                        webdriver.ActionChains(self.driver).send_keys(webdriver.Keys.ESCAPE).perform()
                        logger.debug(f"Tried closing modal with ESC key for deposit #{deposit['index']}")
                        modal_closed = True
                    except:
                        pass
                
                # Method 3: JavaScript click on any close button
                if not modal_closed:
                    try:
                        self.driver.execute_script("""
                            // Try to find and click any close button
                            const closeButtons = Array.from(document.querySelectorAll('button')).filter(btn => {
                                const text = btn.textContent.toLowerCase();
                                return text.includes('close') || 
                                       text.includes('cancel') || 
                                       btn.getAttribute('aria-label')?.toLowerCase().includes('close');
                            });
                            
                            if (closeButtons.length > 0) {
                                closeButtons[0].click();
                                return true;
                            }
                            
                            // Try a backdrop click
                            const backdrops = document.querySelectorAll('.modal-backdrop, [role="presentation"]');
                            if (backdrops.length > 0) {
                                backdrops[0].click();
                                return true;
                            }
                            
                            return false;
                        """)
                        logger.debug(f"Tried closing modal with JavaScript for deposit #{deposit['index']}")
                    except:
                        pass
                
                # Wait for modal to close
                time.sleep(CONFIG["TIMEOUTS"]["MODAL_CLOSE"])
                
                # Verify modal is closed
                modal_still_open = False
                try:
                    for selector in CONFIG["SELECTORS"]["MODAL"]["CONTAINER"]:
                        try:
                            modal = self.driver.find_element(By.CSS_SELECTOR, selector)
                            if modal.is_displayed():
                                modal_still_open = True
                                break
                        except:
                            continue
                    
                    if modal_still_open:
                        logger.warning(f"Modal may still be open for deposit #{deposit['index']}")
                    else:
                        logger.debug(f"Modal confirmed closed for deposit #{deposit['index']}")
                except:
                    pass
                
                # If we got here without exceptions, break the retry loop
                break
                
            except Exception as e:
                logger.warning(f"Error processing deposit #{deposit['index']} (attempt {attempt+1}): {str(e)}")
                detailed_deposit["errorMessage"] = str(e)
                
                if attempt < CONFIG["RETRY"]["ATTEMPTS"] - 1:
                    time.sleep(CONFIG["RETRY"]["DELAY"])
                else:
                    logger.error(f"Failed to extract details for deposit #{deposit['index']} after {CONFIG['RETRY']['ATTEMPTS']} attempts")
        
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
            time.sleep(CONFIG["TIMEOUTS"]["BETWEEN_ACTIONS"])
        
        logger.info(f"Extracted details for {len(self.extracted_data)} deposits")
        return self.extracted_data
    
    def export_to_csv(self, output_file):
        """Export extracted data to CSV with enhanced error handling."""
        logger.info(f"Exporting data to CSV: {output_file}")
        
        if not self.extracted_data:
            logger.warning("No data to export")
            return False
        
        try:
            # Convert to DataFrame for easy CSV export
            df = pd.DataFrame(self.extracted_data)
            
            # Ensure output directory exists
            output_dir = os.path.dirname(output_file)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # Save to CSV with proper encoding
            df.to_csv(output_file, index=False, quoting=csv.QUOTE_ALL, encoding='utf-8-sig')
            
            logger.info(f"Successfully exported {len(self.extracted_data)} deposits to {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"Export failed: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Try backup export
            try:
                backup_file = f"{output_file}.backup"
                with open(backup_file, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=self.extracted_data[0].keys(), quoting=csv.QUOTE_ALL)
                    writer.writeheader()
                    writer.writerows(self.extracted_data)
                logger.info(f"Exported backup data to {backup_file}")
                return True
            except Exception as backup_error:
                logger.error(f"Backup export failed: {str(backup_error)}")
                return False
    
    def save_state(self, processed_children, current_child=None):
        """Save the current processing state to a file for resume capability.
        
        Args:
            processed_children (list): List of already processed children IDs
            current_child (dict, optional): Current child being processed
        """
        try:
            state = {
                "processed_children": processed_children,
                "current_child": current_child,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
                
            logger.debug(f"Saved state: {len(processed_children)} children processed")
        except Exception as e:
            logger.warning(f"Failed to save state: {str(e)}")
    
    def load_state(self):
        """Load the processing state from a file.
        
        Returns:
            tuple: (processed_children, current_child)
        """
        if not os.path.exists(self.state_file):
            return [], None
            
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
                
            processed_children = state.get('processed_children', [])
            current_child = state.get('current_child')
            
            logger.info(f"Loaded state: {len(processed_children)} children already processed")
            return processed_children, current_child
        except Exception as e:
            logger.warning(f"Failed to load state: {str(e)}")
            return [], None
    
    def process_child(self, child_id, child_name=""):
        """Process a single child and extract their deposits.
        
        Args:
            child_id (str): Child ID
            child_name (str): Child name
            
        Returns:
            dict: Processing result
        """
        try:
            # Reset deposits and extracted data
            self.deposits = []
            self.extracted_data = []
            
            # Navigate to child profile
            if not self.navigate_to_child_profile(child_id, child_name):
                return {
                    "success": False,
                    "child_id": child_id,
                    "child_name": child_name,
                    "error": "Failed to navigate to child profile"
                }
            
            # Find deposits
            deposits = self.find_deposits()
            if not deposits:
                return {
                    "success": True,
                    "child_id": child_id,
                    "child_name": child_name,
                    "count": 0,
                    "message": "No deposits found"
                }
            
            # Extract deposit details
            self.extract_all_deposits()
            
            # Create filename
            safe_name = child_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
            safe_name = ''.join(c for c in safe_name if c.isalnum() or c in '_-.')  # Further sanitize
            filename = f"{safe_name}_{child_id}_deposits.csv" if safe_name else f"child_{child_id}_deposits.csv"
            output_file = os.path.join(self.output_dir, filename)
            
            # Export to CSV
            if not self.export_to_csv(output_file):
                return {
                    "success": False,
                    "child_id": child_id,
                    "child_name": child_name,
                    "error": "Failed to export data"
                }
            
            # Check if returns were detected
            returned_deposits = [d for d in self.extracted_data if d.get('hasBeenReturned', False)]
            
            return {
                "success": True,
                "child_id": child_id,
                "child_name": child_name,
                "count": len(self.extracted_data),
                "returned_count": len(returned_deposits),
                "output_file": output_file
            }
            
        except Exception as e:
            logger.error(f"Error processing child {child_name} (ID: {child_id}): {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "child_id": child_id,
                "child_name": child_name,
                "error": str(e)
            }
    
    def batch_process(self, children_data, resume=True):
        """Process a batch of children with resume capability.
        
        Args:
            children_data (list): List of dicts with name and child_id
            resume (bool): Whether to try to resume from a previous state
            
        Returns:
            list: Results for each child
        """
        results = []
        processed_children = []
        
        # Try to load previous state if resume is enabled
        if resume:
            processed_ids, current_child = self.load_state()
            
            # Filter out already processed children
            if processed_ids:
                filtered_data = [c for c in children_data if str(c.get('child_id', '')) not in processed_ids]
                
                if len(filtered_data) < len(children_data):
                    logger.info(f"Resuming batch: {len(processed_ids)} children already processed, {len(filtered_data)} remaining")
                    children_data = filtered_data
        
        # Process each child
        for i, child in enumerate(children_data):
            # Validate child data
            validation_errors = self.validate_child_data(child)
            if validation_errors:
                logger.warning(f"Skipping child due to validation errors: {validation_errors}")
                results.append({
                    "success": False,
                    "child_id": child.get('child_id', 'unknown'),
                    "child_name": child.get('name', 'Unknown'),
                    "error": f"Validation errors: {', '.join(validation_errors)}"
                })
                continue
                
            logger.info(f"Processing child {i+1}/{len(children_data)}: {child.get('name', '')} (ID: {child.get('child_id', '')})")
            
            # Check for login session
            if "login" in self.driver.current_url.lower():
                logger.warning("Session expired, trying to re-login")
                # We'll handle the re-login at a higher level
                break
            
            # Process child
            result = self.process_child(child.get('child_id', ''), child.get('name', ''))
            results.append(result)
            
            # Save state after each child
            if result.get('success', False):
                processed_children.append(str(child.get('child_id', '')))
                self.save_state(processed_children)
            
            # Delay between children
            if i < len(children_data) - 1:  # Don't delay after the last child
                time.sleep(CONFIG["TIMEOUTS"]["BETWEEN_CHILDREN"])
        
        return results
    
    def cleanup(self):
        """Clean up resources safely."""
        logger.info("Cleaning up resources...")
        
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.warning(f"Error during driver cleanup: {str(e)}")
            finally:
                self.driver = None
        
        logger.info("Cleanup complete")
    
    def run_batch(self, username, password, input_file, resume=True):
        """Run batch processing for multiple children with resume capability.
        
        Args:
            username (str): User email
            password (str): User password
            input_file (str): Path to input CSV file
            resume (bool): Whether to try to resume from previous runs
            
        Returns:
            dict: Batch processing results
        """
        overall_start_time = time.time()
        success = False
        results = []
        
        try:
            # Read input CSV file
            try:
                children_df = pd.read_csv(input_file)
                
                # Validate required columns
                required_columns = ['name', 'child_id']
                for col in required_columns:
                    if col not in children_df.columns:
                        return {
                            "success": False,
                            "error": f"CSV file missing required column: {col}"
                        }
                
                # Convert to list of dicts and sanitize data
                children_data = children_df.to_dict('records')
                
                if not children_data:
                    return {
                        "success": False,
                        "error": "No children found in CSV file"
                    }
                
                logger.info(f"Found {len(children_data)} children in CSV file")
                
            except Exception as e:
                logger.error(f"Error reading input file: {str(e)}")
                return {
                    "success": False,
                    "error": f"Failed to read input file: {str(e)}"
                }
            
            # Login
            login_success = self.login(username, password)
            if not login_success:
                return {
                    "success": False,
                    "error": "Login failed"
                }
            
            # Process each child with resume capability
            results = self.batch_process(children_data, resume)
            
            # Check if we need to re-login and continue
            if results and "login" in self.driver.current_url.lower():
                logger.info("Session expired, re-logging in to continue batch")
                login_success = self.login(username, password)
                
                if login_success:
                    # Find the last processed child
                    processed_ids = [r.get('child_id') for r in results if r.get('success', False)]
                    
                    # Continue with remaining children
                    remaining_children = [c for c in children_data if str(c.get('child_id', '')) not in processed_ids]
                    
                    if remaining_children:
                        logger.info(f"Continuing batch with {len(remaining_children)} remaining children")
                        additional_results = self.batch_process(remaining_children, resume=False)
                        results.extend(additional_results)
            
            success = True
            
        except Exception as e:
            logger.error(f"Batch processing failed: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            # Generate summary whether successful or not
            try:
                successful = [r for r in results if r.get('success', False)]
                failed = [r for r in results if not r.get('success', False)]
                total_deposits = sum(r.get('count', 0) for r in successful)
                total_returned = sum(r.get('returned_count', 0) for r in successful)
                
                # Calculate processing time
                processing_time = time.time() - overall_start_time
                
                summary = {
                    "success": success,
                    "total_children": len(children_data) if 'children_data' in locals() else 0,
                    "successful_children": len(successful),
                    "failed_children": len(failed),
                    "total_deposits": total_deposits,
                    "total_returned_deposits": total_returned,
                    "processing_time_seconds": round(processing_time, 2),
                    "results": results,
                    "timestamp": CONFIG["TIMESTAMP"],
                    "extractedBy": CONFIG["USER"]
                }
                
                # Export summary
                summary_file = os.path.join(self.output_dir, f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                with open(summary_file, 'w') as f:
                    json.dump(summary, f, indent=2)
                
                logger.info(f"Batch processing completed in {round(processing_time/60, 2)} minutes. Summary saved to {summary_file}")
                logger.info(f"Processed {len(children_data) if 'children_data' in locals() else 0} children: {len(successful)} successful, {len(failed)} failed")
                logger.info(f"Total deposits extracted: {total_deposits} (including {total_returned} returned deposits)")
                
                # Cleanup resources
                self.cleanup()
                
                return summary
                
            except Exception as summary_error:
                logger.error(f"Error generating summary: {str(summary_error)}")
                self.cleanup()
                
                if results:
                    return {
                        "success": success,
                        "results": results,
                        "error": f"Error generating summary: {str(summary_error)}"
                    }
                else:
                    return {
                        "success": False,
                        "error": str(e) if 'e' in locals() else "Unknown error during batch processing"
                    }

def main():
    """Main entry point for the script."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Extract deposit information from Famly system for multiple children")
    parser.add_argument("-u", "--username", help="Famly login email")
    parser.add_argument("-p", "--password", help="Famly login password")
    parser.add_argument("-i", "--input", help="Input CSV file with child names and IDs", required=True)
    parser.add_argument("-o", "--output-dir", default="output", help="Output directory for CSV files")
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
    extractor = FamlyDepositExtractor(headless=args.headless, debug=args.debug, output_dir=args.output_dir)
    result = extractor.run_batch(username, password, args.input)
    
    if result["success"]:
        print(f"\n✅ Batch processing completed successfully!")
        print(f"📊 Processed {result['total_children']} children: {result['successful_children']} successful, {result['failed_children']} failed")
        print(f"💰 Total deposits extracted: {result['total_deposits']}")
        print(f"📁 Results saved to {args.output_dir} directory")
        return 0
    else:
        print(f"\n❌ Batch processing failed: {result['error']}")
        return 1


if __name__ == "__main__":
    sys.exit(main())