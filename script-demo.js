/**
 * DepositExtractor - A professional tool for extracting and exporting deposit information
 * 
 * @version 1.0.0
 * @author Professional Development Team
 * @license MIT
 */
(function DepositExtractor() {
    'use strict';
  
    /**
     * Configuration settings
     */
    const CONFIG = Object.freeze({
      VERSION: '1.0.0',
      TIMESTAMPS: {
        format: 'YYYY-MM-DD HH:mm:ss',
        current: '2025-04-28 14:25:07'
      },
      USER: 'wolketich',
      SELECTORS: {
        DEPOSITS: {
          CONTAINERS: [
            '.sc-beqWaB.sc-eIoBCF.bUiODS.iDrAoK',
            '[class*="sc-beqWaB"][class*="sc-eIoBCF"]'
          ],
          DEPOSIT_TEXT: 'p:contains("Deposit")',
          RETURN_TEXT: 'p:contains("Return")',
          CURRENCY_SYMBOLS: ['€', '$', '£']
        },
        MODAL: {
          CONTAINER: [
            '.LEGACY_MODAL_groupActionModal',
            '[role="dialog"]',
            '.modal',
            'form',
            '[data-e2e-class="modal-header"]'
          ],
          CLOSE_BUTTON: [
            '#closeModalButton',
            '.LEGACY_MODAL_closeButton',
            'button[role="button"]',
            'button:contains("Close")',
            '[aria-label="Close"]'
          ],
          BILL_PAYER: '.Select-value-label',
          AMOUNT: 'input[name="amount"]',
          DATE: 'input[value*="/"]',
          NOTE: 'textarea[name="note"]',
          ALREADY_PAID: 'input[name="alreadyPaid"]'
        }
      },
      TIMEOUTS: {
        MODAL_WAIT: 10000,
        FORM_EXTRACTION: 800,
        MODAL_CLOSE: 800
      },
      EXPORT: {
        CSV_MIME: 'text/csv',
        JSON_MIME: 'application/json',
        FILE_PREFIX: 'deposits_export_'
      },
      LOGGING: {
        ENABLED: true,
        LEVELS: {
          INFO: 'INFO',
          WARN: 'WARN',
          ERROR: 'ERROR',
          DEBUG: 'DEBUG'
        }
      }
    });
  
    /**
     * Logger utility for consistent logging
     */
    const Logger = (function() {
      const isEnabled = CONFIG.LOGGING.ENABLED;
      const { INFO, WARN, ERROR, DEBUG } = CONFIG.LOGGING.LEVELS;
      
      function formatMessage(level, message) {
        return `[DepositExtractor:${level}] ${message}`;
      }
      
      return {
        info: function(message) {
          if (isEnabled) console.info(formatMessage(INFO, message));
        },
        warn: function(message) {
          if (isEnabled) console.warn(formatMessage(WARN, message));
        },
        error: function(message, error) {
          if (isEnabled) {
            console.error(formatMessage(ERROR, message));
            if (error) console.error(error);
          }
        },
        debug: function(message, data) {
          if (isEnabled && console.debug) {
            console.debug(formatMessage(DEBUG, message));
            if (data !== undefined) console.debug(data);
          }
        },
        group: function(title) {
          if (isEnabled && console.group) console.group(formatMessage(INFO, title));
        },
        groupEnd: function() {
          if (isEnabled && console.groupEnd) console.groupEnd();
        }
      };
    })();
  
    /**
     * DOM utilities for reliable element selection and manipulation
     */
    const DOMUtils = (function() {
      /**
       * Safely query selector with error handling
       * @param {string} selector - CSS selector string
       * @param {Element} [root=document] - Root element to search from
       * @returns {Element|null} Found element or null
       */
      function querySelector(selector, root = document) {
        try {
          return root.querySelector(selector);
        } catch (error) {
          Logger.error(`Invalid selector: ${selector}`, error);
          return null;
        }
      }
      
      /**
       * Safely query selector all with error handling
       * @param {string} selector - CSS selector string
       * @param {Element} [root=document] - Root element to search from
       * @returns {Element[]} Array of matching elements
       */
      function querySelectorAll(selector, root = document) {
        try {
          return Array.from(root.querySelectorAll(selector));
        } catch (error) {
          Logger.error(`Invalid selector: ${selector}`, error);
          return [];
        }
      }
      
      /**
       * Check if element contains specific text
       * @param {Element} element - Element to check
       * @param {string} text - Text to search for
       * @returns {boolean} True if element contains text
       */
      function elementContainsText(element, text) {
        return element.textContent.trim().includes(text);
      }
      
      /**
       * Find elements by text content
       * @param {string} tagName - Tag name to search (e.g., 'p', 'div')
       * @param {string} text - Text to search for
       * @param {Element} [root=document] - Root element to search from
       * @returns {Element[]} Array of matching elements
       */
      function findElementsByText(tagName, text, root = document) {
        return querySelectorAll(tagName, root)
          .filter(el => el.textContent.trim() === text);
      }
      
      /**
       * Find closest ancestor matching a condition
       * @param {Element} element - Starting element
       * @param {Function} predicate - Test function
       * @param {number} [maxDepth=10] - Maximum levels to traverse up
       * @returns {Element|null} Matching ancestor or null
       */
      function findAncestor(element, predicate, maxDepth = 10) {
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
      
      /**
       * Check if element has specific style
       * @param {Element} element - Element to check
       * @param {string} property - CSS property
       * @param {string} value - Expected value
       * @returns {boolean} True if style matches
       */
      function hasStyle(element, property, value) {
        const style = window.getComputedStyle(element);
        return style[property] === value;
      }
      
      /**
       * Find clickable element
       * @param {Element} container - Container to search in
       * @returns {Element} Best clickable element
       */
      function findClickableElement(container) {
        // Check if container itself is clickable
        if (container.onclick || 
            container.getAttribute('role') === 'button' || 
            container.tagName === 'BUTTON' || 
            container.classList.contains('clickable')) {
          return container;
        }
        
        // Check for buttons
        const buttons = querySelectorAll('button', container);
        if (buttons.length > 0) return buttons[0];
        
        // Check for role=button
        const roleButtons = querySelectorAll('[role="button"]', container);
        if (roleButtons.length > 0) return roleButtons[0];
        
        // Check for pointer cursor
        const elements = querySelectorAll('*', container);
        for (const element of elements) {
          if (hasStyle(element, 'cursor', 'pointer')) {
            return element;
          }
        }
        
        return container;
      }
      
      /**
       * Wait for element to appear in DOM
       * @param {string|string[]} selectors - CSS selector(s)
       * @param {number} [timeout] - Timeout in ms
       * @returns {Promise<Element>} Found element
       */
      function waitForElement(selectors, timeout = CONFIG.TIMEOUTS.MODAL_WAIT) {
        if (!Array.isArray(selectors)) {
          selectors = [selectors];
        }
        
        return new Promise((resolve, reject) => {
          // Check if already exists
          for (const selector of selectors) {
            const element = querySelector(selector);
            if (element) {
              return resolve(element);
            }
          }
          
          // Setup observer
          const observer = new MutationObserver(() => {
            for (const selector of selectors) {
              const element = querySelector(selector);
              if (element) {
                observer.disconnect();
                resolve(element);
                return;
              }
            }
          });
          
          observer.observe(document.body, {
            childList: true,
            subtree: true,
            attributes: true
          });
          
          // Setup timeout
          setTimeout(() => {
            observer.disconnect();
            Logger.warn(`Timeout waiting for elements: ${selectors.join(', ')}`);
            
            // Try to find any modal-like elements as fallback
            const possibleModals = querySelectorAll(
              CONFIG.SELECTORS.MODAL.CONTAINER.join(', ')
            );
            
            if (possibleModals.length > 0) {
              Logger.debug('Found possible modal as fallback', possibleModals[0]);
              resolve(possibleModals[0]);
            } else {
              reject(new Error(`Timeout waiting for elements: ${selectors.join(', ')}`));
            }
          }, timeout);
        });
      }
      
      return {
        querySelector,
        querySelectorAll,
        elementContainsText,
        findElementsByText,
        findAncestor,
        hasStyle,
        findClickableElement,
        waitForElement
      };
    })();
  
    /**
     * Core deposit finding and information extraction
     */
    const DepositFinder = (function() {
      /**
       * Find all deposit containers on the page
       * @returns {Element[]} Array of deposit containers
       */
      function findDepositContainers() {
        // Try direct selectors first
        const containerSelectors = CONFIG.SELECTORS.DEPOSITS.CONTAINERS.join(', ');
        let containers = DOMUtils.querySelectorAll(containerSelectors);
        
        // Filter to only include those with "Deposit" text
        containers = containers.filter(container => 
          DOMUtils.elementContainsText(container, 'Deposit')
        );
        
        Logger.info(`Found ${containers.length} deposit containers using direct selectors`);
        
        // If no containers found, try generic approach
        if (containers.length === 0) {
          return findDepositContainersGeneric();
        }
        
        return containers;
      }
      
      /**
       * Generic approach to find deposit containers
       * @returns {Element[]} Array of deposit containers
       */
      function findDepositContainersGeneric() {
        // Find all "Deposit" paragraphs
        const depositTexts = DOMUtils.findElementsByText('p', 'Deposit');
        Logger.info(`Found ${depositTexts.length} deposit texts, searching for containers...`);
        
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
              const hasNumbers = /\d+\.\d+|\d+,\d+/.test(el.textContent);
              
              return hasDeposit && (hasAmount || hasNumbers);
            },
            8 // Check up to 8 levels up
          );
          
          if (container && !containers.includes(container)) {
            containers.push(container);
          }
        }
        
        Logger.info(`Found ${containers.length} deposit containers using generic approach`);
        return containers;
      }
      
      /**
       * Extract deposit information from container
       * @param {Element} container - Deposit container element
       * @param {number} index - Deposit index (1-based)
       * @returns {Object} Deposit information
       */
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
              if (/[\d,.]+/.test(nextParagraph.textContent.trim())) {
                amount = nextParagraph.textContent.trim();
                break;
              }
            }
          }
        }
        
        // If not found, look for combined format
        if (!amount) {
          const amountParagraph = paragraphs.find(p => 
            /^[€$£]?\s*[\d,.]+$/.test(p.textContent.trim())
          );
          
          if (amountParagraph) {
            const text = amountParagraph.textContent.trim();
            const match = text.match(/^([€$£]?)\s*([\d,.]+)$/);
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
        
        return {
          index,
          type: 'Deposit',
          amount,
          currency,
          depositStatus,
          hasBeenReturned,
          returnStatus,
          element: container
        };
      }
      
      /**
       * Find all deposits on the page
       * @returns {Object[]} Array of deposit objects
       */
      function findAllDeposits() {
        const containers = findDepositContainers();
        return containers.map((container, index) => 
          extractDepositInfo(container, index + 1)
        );
      }
      
      return {
        findAllDeposits,
        extractDepositInfo
      };
    })();
  
    /**
     * Modal operations for extracting detailed deposit information
     */
    const ModalHandler = (function() {
      /**
       * Extract details from the deposit modal form
       * @returns {Promise<Object>} Extracted form data
       */
      function extractModalDetails() {
        return new Promise((resolve, reject) => {
          setTimeout(() => {
            try {
              // Get bill payer
              const billPayerElement = DOMUtils.querySelector(CONFIG.SELECTORS.MODAL.BILL_PAYER);
              const billPayer = billPayerElement ? billPayerElement.textContent.trim() : '';
              
              // Get amount
              const amountInput = DOMUtils.querySelector(CONFIG.SELECTORS.MODAL.AMOUNT);
              const amount = amountInput ? amountInput.value : '';
              
              // Get deposit date
              const dateInput = DOMUtils.querySelector(CONFIG.SELECTORS.MODAL.DATE);
              const depositDate = dateInput ? dateInput.value : '';
              
              // Get note
              const noteTextarea = DOMUtils.querySelector(CONFIG.SELECTORS.MODAL.NOTE);
              const note = noteTextarea ? noteTextarea.value : '';
              
              // Check if already paid
              const alreadyPaidCheckbox = DOMUtils.querySelector(CONFIG.SELECTORS.MODAL.ALREADY_PAID);
              const alreadyPaid = alreadyPaidCheckbox ? alreadyPaidCheckbox.checked : false;
              
              const details = {
                billPayer,
                amount,
                depositDate,
                note,
                alreadyPaid
              };
              
              Logger.debug('Extracted modal details', details);
              resolve(details);
              
            } catch (error) {
              Logger.error('Failed to extract modal details', error);
              reject(error);
            }
          }, CONFIG.TIMEOUTS.FORM_EXTRACTION);
        });
      }
      
      /**
       * Close the current modal
       * @returns {boolean} Success status
       */
      function closeModal() {
        Logger.info('Attempting to close modal...');
        
        // Try all possible close buttons
        for (const selector of CONFIG.SELECTORS.MODAL.CLOSE_BUTTON) {
          try {
            const button = DOMUtils.querySelector(selector);
            if (button) {
              Logger.debug(`Found close button with selector: ${selector}`);
              button.click();
              return true;
            }
          } catch (e) {
            // Ignore errors for invalid selectors
          }
        }
        
        // Fallback: Try ESC key
        Logger.debug('No close button found, trying ESC key');
        document.dispatchEvent(new KeyboardEvent('keydown', { 
          key: 'Escape', 
          code: 'Escape',
          bubbles: true 
        }));
        
        return false;
      }
      
      /**
       * Get detailed information for a specific deposit
       * @param {Object} deposit - Deposit object
       * @returns {Promise<Object>} Full deposit details
       */
      async function getDepositDetails(deposit) {
        try {
          Logger.info(`Getting details for deposit #${deposit.index}: ${deposit.currency}${deposit.amount}`);
          
          // Find clickable element and click
          const clickableElement = DOMUtils.findClickableElement(deposit.element);
          Logger.debug('Found clickable element', clickableElement);
          clickableElement.click();
          
          // Wait for modal
          try {
            await DOMUtils.waitForElement(CONFIG.SELECTORS.MODAL.CONTAINER);
            Logger.info('Modal detected');
          } catch (error) {
            Logger.warn('Modal detection timed out, attempting to extract anyway');
          }
          
          // Extract details
          const modalInfo = await extractModalDetails();
          
          // Combine information
          const fullDetails = {
            index: deposit.index,
            listInfo: {
              amount: deposit.amount,
              currency: deposit.currency,
              depositStatus: deposit.depositStatus,
              hasBeenReturned: deposit.hasBeenReturned,
              returnStatus: deposit.returnStatus
            },
            modalInfo,
            timestamp: CONFIG.TIMESTAMPS.current,
            extractedBy: CONFIG.USER
          };
          
          return fullDetails;
          
        } catch (error) {
          Logger.error(`Failed to get details for deposit #${deposit.index}`, error);
          
          // Return partial information
          return {
            index: deposit.index,
            listInfo: {
              amount: deposit.amount,
              currency: deposit.currency,
              depositStatus: deposit.depositStatus,
              hasBeenReturned: deposit.hasBeenReturned,
              returnStatus: deposit.returnStatus
            },
            error: error.message,
            timestamp: CONFIG.TIMESTAMPS.current,
            extractedBy: CONFIG.USER
          };
        }
      }
      
      return {
        extractModalDetails,
        closeModal,
        getDepositDetails
      };
    })();
  
    /**
     * Export utilities for saving deposit data
     */
    const DataExport = (function() {
      /**
       * Convert data to CSV format
       * @param {Object[]} data - Array of data objects
       * @returns {string} CSV content
       */
      function toCSV(data) {
        if (!data || data.length === 0) return '';
        
        // Get headers from first object
        const headers = Object.keys(data[0]);
        
        // Create header row
        let csv = headers.join(',') + '\n';
        
        // Add data rows
        data.forEach(item => {
          const row = headers.map(header => {
            const value = item[header];
            
            // Handle different data types
            if (value === null || value === undefined) {
              return '';
            } else if (typeof value === 'boolean') {
              return value ? 'true' : 'false';
            } else if (typeof value === 'string') {
              // Escape quotes and wrap in quotes
              return `"${value.replace(/"/g, '""')}"`;
            } else if (typeof value === 'object') {
              // Convert objects to JSON strings
              return `"${JSON.stringify(value).replace(/"/g, '""')}"`;
            } else {
              return `"${String(value)}"`;
            }
          });
          
          csv += row.join(',') + '\n';
        });
        
        return csv;
      }
      
      /**
       * Format deposit data for export
       * @param {Object[]} deposits - Array of deposit objects with details
       * @returns {Object[]} Formatted data for export
       */
      function formatForExport(deposits) {
        return deposits.map(deposit => {
          // Flatten the structure for easier export
          const modalInfo = deposit.modalInfo || {};
          const listInfo = deposit.listInfo || {};
          
          return {
            index: deposit.index,
            amount: listInfo.amount ? listInfo.amount.replace(/,/g, '') : '',
            currency: listInfo.currency || '',
            depositStatus: listInfo.depositStatus || '',
            hasBeenReturned: listInfo.hasBeenReturned || false,
            returnStatus: listInfo.returnStatus || '',
            billPayer: modalInfo.billPayer || '',
            formAmount: modalInfo.amount || '',
            depositDate: modalInfo.depositDate || '',
            note: modalInfo.note || '',
            alreadyPaid: modalInfo.alreadyPaid || false,
            extractedBy: deposit.extractedBy || CONFIG.USER,
            extractedAt: deposit.timestamp || CONFIG.TIMESTAMPS.current,
            errorMessage: deposit.error || ''
          };
        });
      }
      
      /**
       * Download content as a file
       * @param {string} content - File content
       * @param {string} fileName - File name
       * @param {string} contentType - MIME type
       */
      function downloadFile(content, fileName, contentType) {
        // Create a file and download link
        const blob = new Blob([content], { type: contentType });
        const url = URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        a.style.display = 'none';
        
        // Add to DOM, click, and clean up
        document.body.appendChild(a);
        a.click();
        
        setTimeout(() => {
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        }, 100);
      }
      
      /**
       * Generate timestamp-based filename
       * @param {string} extension - File extension
       * @returns {string} Filename with timestamp
       */
      function generateFilename(extension) {
        const timestamp = CONFIG.TIMESTAMPS.current.replace(/[: ]/g, '_');
        return `${CONFIG.EXPORT.FILE_PREFIX}${timestamp}.${extension}`;
      }
      
      return {
        toCSV,
        formatForExport,
        downloadFile,
        generateFilename
      };
    })();
  
    /**
     * UI utilities for user feedback
     */
    const UIUtils = (function() {
      let loadingOverlay = null;
      
      /**
       * Show loading overlay
       * @param {string} message - Message to display
       */
      function showLoading(message) {
        // Create overlay if it doesn't exist
        if (!loadingOverlay) {
          loadingOverlay = document.createElement('div');
          loadingOverlay.style.position = 'fixed';
          loadingOverlay.style.top = '0';
          loadingOverlay.style.left = '0';
          loadingOverlay.style.width = '100%';
          loadingOverlay.style.height = '100%';
          loadingOverlay.style.backgroundColor = 'rgba(0, 0, 0, 0.7)';
          loadingOverlay.style.zIndex = '9999';
          loadingOverlay.style.display = 'flex';
          loadingOverlay.style.alignItems = 'center';
          loadingOverlay.style.justifyContent = 'center';
          loadingOverlay.style.flexDirection = 'column';
          loadingOverlay.style.color = 'white';
          loadingOverlay.style.fontFamily = 'Arial, sans-serif';
          loadingOverlay.style.fontSize = '16px';
          
          // Add progress indicator
          const spinner = document.createElement('div');
          spinner.style.border = '5px solid #f3f3f3';
          spinner.style.borderTop = '5px solid #3498db';
          spinner.style.borderRadius = '50%';
          spinner.style.width = '50px';
          spinner.style.height = '50px';
          spinner.style.animation = 'spin 2s linear infinite';
          
          // Add keyframes for spinner animation
          const style = document.createElement('style');
          style.innerHTML = `
            @keyframes spin {
              0% { transform: rotate(0deg); }
              100% { transform: rotate(360deg); }
            }
          `;
          document.head.appendChild(style);
          
          loadingOverlay.appendChild(spinner);
          
          // Add message container
          const messageElement = document.createElement('div');
          messageElement.style.marginTop = '20px';
          messageElement.style.maxWidth = '80%';
          messageElement.style.textAlign = 'center';
          loadingOverlay.appendChild(messageElement);
          
          // Add counter element
          const counterElement = document.createElement('div');
          counterElement.style.marginTop = '10px';
          counterElement.style.fontSize = '14px';
          loadingOverlay.appendChild(counterElement);
          
          document.body.appendChild(loadingOverlay);
        }
        
        // Update message
        loadingOverlay.querySelector('div:nth-child(2)').textContent = message;
        loadingOverlay.querySelector('div:nth-child(3)').textContent = '';
        
        // Show overlay
        loadingOverlay.style.display = 'flex';
      }
      
      /**
       * Update loading progress
       * @param {number} current - Current progress
       * @param {number} total - Total items
       */
      function updateProgress(current, total) {
        if (loadingOverlay) {
          loadingOverlay.querySelector('div:nth-child(3)').textContent = 
            `Processing ${current} of ${total}`;
        }
      }
      
      /**
       * Hide loading overlay
       */
      function hideLoading() {
        if (loadingOverlay) {
          loadingOverlay.style.display = 'none';
        }
      }
      
      /**
       * Show alert with styled message
       * @param {string} message - Message to display
       * @param {string} type - Alert type (success, error, info)
       */
      function showAlert(message, type = 'info') {
        // Use a more styled approach than basic alert()
        const alertBox = document.createElement('div');
        alertBox.style.position = 'fixed';
        alertBox.style.top = '20px';
        alertBox.style.left = '50%';
        alertBox.style.transform = 'translateX(-50%)';
        alertBox.style.padding = '15px 25px';
        alertBox.style.borderRadius = '5px';
        alertBox.style.boxShadow = '0 4px 12px rgba(0,0,0,0.15)';
        alertBox.style.zIndex = '10000';
        alertBox.style.fontFamily = 'Arial, sans-serif';
        alertBox.style.fontSize = '16px';
        alertBox.style.textAlign = 'center';
        alertBox.style.maxWidth = '80%';
        
        // Set type-specific styles
        switch (type) {
          case 'success':
            alertBox.style.backgroundColor = '#2ecc71';
            alertBox.style.color = 'white';
            break;
          case 'error':
            alertBox.style.backgroundColor = '#e74c3c';
            alertBox.style.color = 'white';
            break;
          default:
            alertBox.style.backgroundColor = '#f8f9fa';
            alertBox.style.color = '#333';
            alertBox.style.border = '1px solid #ddd';
        }
        
        alertBox.textContent = message;
        document.body.appendChild(alertBox);
        
        // Auto-remove after delay
        setTimeout(() => {
          if (document.body.contains(alertBox)) {
            document.body.removeChild(alertBox);
          }
        }, 4000);
      }
      
      return {
        showLoading,
        updateProgress,
        hideLoading,
        showAlert
      };
    })();
  
    /**
     * Main application controller
     */
    const App = (function() {
      /**
       * Export all deposit data with details
       * @returns {Promise<Object>} Export results
       */
      async function exportAllDepositData() {
        try {
          // Find all deposits first
          const deposits = DepositFinder.findAllDeposits();
          
          if (deposits.length === 0) {
            UIUtils.showAlert('No deposits found on the page.', 'error');
            return { success: false, error: 'No deposits found' };
          }
          
          // Show loading overlay
          UIUtils.showLoading(`Extracting details for ${deposits.length} deposits...`);
          
          // Process each deposit to get details
          const depositDetails = [];
          
          for (let i = 0; i < deposits.length; i++) {
            try {
              UIUtils.updateProgress(i + 1, deposits.length);
              
              // Get details
              const details = await ModalHandler.getDepositDetails(deposits[i]);
              depositDetails.push(details);
              
              // Close modal
              ModalHandler.closeModal();
              
              // Wait for modal to close
              await new Promise(resolve => setTimeout(resolve, CONFIG.TIMEOUTS.MODAL_CLOSE));
              
            } catch (error) {
              Logger.error(`Error processing deposit #${i+1}`, error);
              
              // Add deposit with error info
              depositDetails.push({
                index: deposits[i].index,
                listInfo: {
                  amount: deposits[i].amount,
                  currency: deposits[i].currency,
                  depositStatus: deposits[i].depositStatus,
                  hasBeenReturned: deposits[i].hasBeenReturned,
                  returnStatus: deposits[i].returnStatus
                },
                error: error.message,
                timestamp: CONFIG.TIMESTAMPS.current,
                extractedBy: CONFIG.USER
              });
            }
          }
          
          // Format data for export
          const exportData = DataExport.formatForExport(depositDetails);
          
          // Generate CSV and JSON content
          const csvContent = DataExport.toCSV(exportData);
          const jsonContent = JSON.stringify(exportData, null, 2);
          
          // Generate filenames
          const csvFilename = DataExport.generateFilename('csv');
          const jsonFilename = DataExport.generateFilename('json');
          
          // Download files
          DataExport.downloadFile(csvContent, csvFilename, CONFIG.EXPORT.CSV_MIME);
          DataExport.downloadFile(jsonContent, jsonFilename, CONFIG.EXPORT.JSON_MIME);
          
          // Hide loading overlay
          UIUtils.hideLoading();
          
          // Show success message
          UIUtils.showAlert(`Successfully exported ${deposits.length} deposits!`, 'success');
          
          // Log success
          Logger.info(`Export complete: ${deposits.length} deposits exported to ${csvFilename} and ${jsonFilename}`);
          
          return {
            success: true,
            count: deposits.length,
            csvFilename,
            jsonFilename,
            data: exportData
          };
          
        } catch (error) {
          // Hide loading overlay
          UIUtils.hideLoading();
          
          // Show error message
          UIUtils.showAlert(`Export failed: ${error.message}`, 'error');
          
          // Log error
          Logger.error('Export failed', error);
          
          return {
            success: false,
            error: error.message
          };
        }
      }
      
      /**
       * Display deposits found on the page
       */
      function displayDepositsFound() {
        const deposits = DepositFinder.findAllDeposits();
        
        Logger.group('Deposits Found');
        deposits.forEach((deposit, index) => {
          Logger.info(`Deposit #${index + 1}: ${deposit.currency}${deposit.amount}`);
          Logger.debug(`  Status: ${deposit.depositStatus}`);
          Logger.debug(`  Returned: ${deposit.hasBeenReturned ? 'Yes (' + deposit.returnStatus + ')' : 'No'}`);
        });
        Logger.groupEnd();
        
        return deposits;
      }
      
      /**
       * Initialize the application
       */
      function init() {
        // Display app info
        Logger.info(`DepositExtractor v${CONFIG.VERSION} initialized`);
        Logger.info(`Current user: ${CONFIG.USER}`);
        Logger.info(`Timestamp: ${CONFIG.TIMESTAMPS.current}`);
        
        // Display found deposits
        const deposits = displayDepositsFound();
        
        // Expose public API
        window.DepositExtractor = {
          findDeposits: DepositFinder.findAllDeposits,
          getDepositDetails: ModalHandler.getDepositDetails,
          exportAllData: exportAllDepositData,
          version: CONFIG.VERSION,
          config: { ...CONFIG, SELECTORS: '...' }  // Omit verbose selectors
        };
        
        // Display usage instructions in console
        const depositCount = deposits.length;
        
        console.log('====== Deposit Extractor ======');
        console.log(`Found ${depositCount} deposits on the page`);
        console.log('\nTo export all deposits to CSV and JSON:');
        console.log('  DepositExtractor.exportAllData()');
        console.log('\nOther available functions:');
        console.log('  DepositExtractor.findDeposits()');
        console.log('  DepositExtractor.getDepositDetails(deposit)');
        console.log('================================');
        
        return {
          deposits,
          exportAllData: exportAllDepositData
        };
      }
      
      return {
        init,
        exportAllDepositData,
        displayDepositsFound
      };
    })();
  
    // Initialize and return the application
    return App.init();
  })();