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
                    if (/[0-9,.]+/.test(nextParagraph.textContent.trim())) {
                        amount = nextParagraph.textContent.trim();
                        break;
                    }
                }
            }
        }
    
        // If not found, look for combined format
        if (!amount) {
            const amountParagraph = paragraphs.find(p => 
                /^[€$£]?\s*[0-9,.]+$/.test(p.textContent.trim())
            );
    
            if (amountParagraph) {
                const text = amountParagraph.textContent.trim();
                const match = text.match(/^([€$£]?)\s*([0-9,.]+)$/);
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
    
        // --- FIXED RETURN DETECTION ---
        // Find <p>Return</p>
        const returnParagraph = paragraphs.find(p => p.textContent.trim() === 'Return');
    
        let hasBeenReturned = false;
        let returnStatus = '';
    
        if (returnParagraph) {
            const parent = returnParagraph.parentElement;
            if (parent) {
                const small = parent.querySelector('small');
                if (small) {
                    returnStatus = small.textContent.trim();
    
                    // Correct interpretation based on your examples
                    if (returnStatus === 'Invoiced') {
                        hasBeenReturned = true;
                    } else if (returnStatus === 'Pending invoice') {
                        hasBeenReturned = false;
                    } else {
                        // Unknown status - optionally default to false
                        hasBeenReturned = false;
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