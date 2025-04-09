import os
import time
import logging
import random
import requests
import tempfile
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (TimeoutException, 
                                      NoSuchElementException,
                                      WebDriverException,
                                      InvalidSessionIdException)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

# Configuration
LOGIN_FILE = 'logins.txt'
MAX_ATTEMPTS = 3
DELAY_BETWEEN_ATTEMPTS = random.uniform(5, 10)  # Random delay between 5-10 seconds
LOG_FILE = 'login_log.txt'
NAVIGATION_DELAY = random.uniform(1, 3)  # Random delay between pages
TIMEOUT = 15
SCREENSHOT_DIR = 'screenshots'
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
]
OCR_API_KEY = 'K89947888988957'  # Free OCR.SPACE API key
MAX_CAPTCHA_RETRIES = 2  # Max attempts to solve captcha

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

class EmaktabAutomation:
    def __init__(self):
        self.driver = None
        self.current_credentials = None
        self.credentials_list = []
        self.load_credentials()
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        self.main_window = None
        self.session_active = False

    def load_credentials(self):
        """Load credentials from file in login:password format"""
        if not os.path.exists(LOGIN_FILE):
            logging.warning(f"{LOGIN_FILE} file not found. Creating new one.")
            open(LOGIN_FILE, 'a').close()
            return

        with open(LOGIN_FILE, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]
            
        valid_credentials = []
        seen = set()
        for line in lines:
            if ':' in line:
                login, password = line.split(':', 1)
                cred_pair = (login.strip(), password.strip())
                if cred_pair not in seen:
                    seen.add(cred_pair)
                    valid_credentials.append(cred_pair)
            else:
                logging.warning(f"Invalid format in line: {line}")

        self.credentials_list = valid_credentials
        logging.info(f"Loaded {len(self.credentials_list)} credentials from {LOGIN_FILE}")

    def human_type(self, element, text):
        """Simulate human typing with random delays"""
        for character in text:
            element.send_keys(character)
            time.sleep(random.uniform(0.1, 0.3))
        time.sleep(0.5)

    def random_delay(self, min_seconds=1, max_seconds=3):
        """Random delay between actions"""
        time.sleep(random.uniform(min_seconds, max_seconds))

    def init_driver(self):
        """Initialize Chrome WebDriver with human-like settings"""
        if self.driver is not None:
            try:
                self.driver.quit()
            except:
                pass

        chrome_options = webdriver.ChromeOptions()
        
        # Basic options
        chrome_options.add_argument('--disable-infobars')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        
        # Anti-bot measures
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Random user agent
        user_agent = random.choice(USER_AGENTS)
        chrome_options.add_argument(f'user-agent={user_agent}')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        
        # Mask selenium detection
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.driver.implicitly_wait(10)
        self.main_window = self.driver.current_window_handle
        self.session_active = True

    def solve_captcha(self):
        """Solve captcha using OCR.SPACE API with retry logic"""
        for retry in range(MAX_CAPTCHA_RETRIES):
            try:
                # Get captcha image
                captcha_element = WebDriverWait(self.driver, TIMEOUT).until(
                    EC.presence_of_element_located((By.CLASS_NAME, 'captcha__image')))
                captcha_src = captcha_element.get_attribute('src')
                
                if not captcha_src:
                    logging.error("No captcha image source found")
                    continue

                # Download captcha image
                try:
                    response = requests.get(captcha_src, timeout=10)
                    response.raise_for_status()
                except requests.RequestException as e:
                    logging.error(f"Failed to download captcha image: {e}")
                    continue

                # Save to temporary file
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                        tmp_file.write(response.content)
                        temp_image_path = tmp_file.name
                except IOError as e:
                    logging.error(f"Failed to save captcha image: {e}")
                    continue

                # Use OCR.SPACE API to solve captcha
                try:
                    payload = {
                        'apikey': OCR_API_KEY,
                        'language': 'eng',
                        'isOverlayRequired': False,
                        'filetype': 'PNG',
                        'OCREngine': 2  # Engine 2 is better for captchas
                    }
                    
                    with open(temp_image_path, 'rb') as f:
                        response = requests.post(
                            'https://api.ocr.space/parse/image',
                            files={'image': f},
                            data=payload,
                            timeout=30
                        )
                    
                    result = response.json()
                    
                    # Parse the result
                    if result['IsErroredOnProcessing']:
                        logging.error(f"OCR error: {result.get('ErrorMessage', 'Unknown error')}")
                        continue
                    
                    if 'ParsedResults' in result and len(result['ParsedResults']) > 0:
                        parsed_text = result['ParsedResults'][0]['ParsedText'].strip()
                        # Extract only digits (captcha is usually 5 digits)
                        captcha_text = ''.join(filter(str.isdigit, parsed_text))
                        
                        # Validate captcha length
                        if len(captcha_text) != 5:
                            logging.warning(f"Invalid captcha length: {captcha_text} (attempt {retry + 1}/{MAX_CAPTCHA_RETRIES})")
                            continue
                            
                        logging.info(f"Captcha solved: {captcha_text}")
                        return captcha_text
                        
                except Exception as e:
                    logging.error(f"OCR API error: {e}")
                finally:
                    # Clean up temp file
                    try:
                        os.unlink(temp_image_path)
                    except:
                        pass
                        
            except Exception as e:
                logging.error(f"Unexpected error in captcha solving (attempt {retry + 1}): {e}")
                if retry < MAX_CAPTCHA_RETRIES - 1:
                    time.sleep(random.uniform(2, 5))
        
        logging.error("All captcha solving attempts failed")
        return None

    def check_session_active(self):
        """Check if the browser session is still active"""
        try:
            if not self.session_active:
                return False
                
            # Try a simple command to check session status
            self.driver.current_url
            return True
        except (InvalidSessionIdException, WebDriverException):
            self.session_active = False
            return False

    def attempt_login(self, login, password):
        """Attempt to login with credentials with session handling"""
        try:
            # Check if session is still active
            if not self.check_session_active():
                logging.warning("Session expired, reinitializing driver...")
                self.init_driver()
            
            # Navigate to login page
            self.driver.get("https://login.emaktab.uz/")
            self.random_delay(2, 4)
            
            # Enter credentials
            username_field = WebDriverWait(self.driver, TIMEOUT).until(
                EC.presence_of_element_located((By.NAME, "login")))
            
            password_field = self.driver.find_element(By.NAME, "password")
            
            # Human-like typing
            self.human_type(username_field, login)
            self.random_delay(1, 2)
            self.human_type(password_field, password)
            self.random_delay(1, 2)
            
            # Click login button
            login_button = self.driver.find_element(By.CSS_SELECTOR, "[data-test-id='login-button']")
            ActionChains(self.driver).move_to_element(login_button).pause(
                random.uniform(0.5, 1.5)).click().perform()
            
            # Wait for login result
            self.random_delay(3, 5)
            
            # Check if login successful
            if "login" not in self.driver.current_url:
                logging.info(f"Login successful for {login}")
                return True
                
            # Check for captcha
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CLASS_NAME, 'captcha__image')))
                
                logging.info("Captcha detected, solving...")
                captcha_text = self.solve_captcha()
                
                if not captcha_text:
                    logging.error("Failed to solve captcha")
                    return False
                    
                # Enter captcha solution
                captcha_input = WebDriverWait(self.driver, TIMEOUT).until(
                    EC.presence_of_element_located((By.NAME, "Captcha.Input")))
                
                self.human_type(captcha_input, captcha_text)
                self.random_delay(1, 2)
                
                # Click login button again
                login_button = self.driver.find_element(By.CSS_SELECTOR, "[data-test-id='login-button']")
                ActionChains(self.driver).move_to_element(login_button).pause(
                    random.uniform(0.5, 1.5)).click().perform()
                
                # Wait for result
                self.random_delay(3, 5)
                
                return "login" not in self.driver.current_url
                
            except TimeoutException:
                logging.warning("Login failed, no captcha detected")
                return False
                
        except Exception as e:
            logging.error(f"Login attempt failed: {str(e)}")
            # Mark session as inactive if we hit a session error
            if "invalid session id" in str(e).lower():
                self.session_active = False
            return False

    def navigate_to_section(self, url, section_name):
        """Navigate to different sections with human-like behavior"""
        try:
            if not self.check_session_active():
                raise WebDriverException("Session expired")
                
            self.driver.get(url)
            WebDriverWait(self.driver, TIMEOUT).until(
                EC.presence_of_element_located((By.TAG_NAME, 'body')))
            
            # Random scrolling
            scroll_actions = random.randint(1, 3)
            for _ in range(scroll_actions):
                scroll_pixels = random.randint(200, 800)
                self.driver.execute_script(f"window.scrollBy(0, {scroll_pixels});")
                self.random_delay(0.5, 1.5)
            
            logging.info(f"Successfully navigated to {section_name} section")
            return True
        except Exception as e:
            logging.error(f"Failed to navigate to {section_name}: {str(e)}")
            return False

    def take_screenshot(self, prefix):
        """Take screenshot with timestamp"""
        try:
            if not self.check_session_active():
                raise WebDriverException("Session expired")
                
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"{SCREENSHOT_DIR}/{prefix}_{timestamp}.png"
            self.driver.save_screenshot(filename)
            logging.info(f"Screenshot saved: {filename}")
            return True
        except Exception as e:
            logging.error(f"Screenshot failed: {str(e)}")
            return False

    def perform_logout(self):
        """Logout from the system"""
        try:
            if not self.check_session_active():
                raise WebDriverException("Session expired")
                
            self.driver.get("https://login.emaktab.uz/logout")
            WebDriverWait(self.driver, TIMEOUT).until(
                EC.presence_of_element_located((By.TAG_NAME, 'body')))
            self.random_delay(2, 4)
            logging.info("Logout successful")
            return True
        except Exception as e:
            logging.error(f"Logout failed: {str(e)}")
            return False

    def process_account(self, login, password):
        """Process single account with proper error handling"""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            logging.info(f"Attempt {attempt}/{MAX_ATTEMPTS} for {login}")
            
            try:
                if self.attempt_login(login, password):
                    # Successful login actions
                    self.take_screenshot(f"{login}_dashboard")
                    
                    # Navigate to different sections
                    if self.navigate_to_section("https://schools.emaktab.uz/v2/homework", "Homework"):
                        self.take_screenshot(f"{login}_homework")
                        self.random_delay(2, 4)
                    
                    if self.navigate_to_section("https://emaktab.uz/marks", "Marks"):
                        self.take_screenshot(f"{login}_marks")
                        self.random_delay(2, 4)
                    
                    # Logout
                    self.perform_logout()
                    return True
                else:
                    logging.warning(f"Attempt {attempt} failed for {login}")
                    if attempt < MAX_ATTEMPTS:
                        delay = random.uniform(DELAY_BETWEEN_ATTEMPTS, DELAY_BETWEEN_ATTEMPTS * 1.5)
                        time.sleep(delay)
            
            except Exception as e:
                logging.error(f"Error processing account {login}: {str(e)}")
                if "session" in str(e).lower():
                    self.session_active = False
                    self.init_driver()
                if attempt < MAX_ATTEMPTS:
                    time.sleep(DELAY_BETWEEN_ATTEMPTS)
        
        logging.error(f"All login attempts failed for {login}")
        return False

    def process_all_accounts(self):
        """Process all accounts in the list with proper resource management"""
        if not self.credentials_list:
            logging.error("No credentials found in the file!")
            return

        self.init_driver()
        success_count = 0
        
        try:
            for idx, (login, password) in enumerate(self.credentials_list, 1):
                logging.info(f"Processing account {idx}/{len(self.credentials_list)}: {login}")
                
                if self.process_account(login, password):
                    success_count += 1
                
                # Delay between accounts
                if idx < len(self.credentials_list):
                    delay = random.uniform(5, 15)
                    time.sleep(delay)
            
            logging.info(f"Process completed. Successful logins: {success_count}/{len(self.credentials_list)}")
            
        except Exception as e:
            logging.error(f"Fatal error: {str(e)}")
            
        finally:
            try:
                if self.driver is not None:
                    self.driver.quit()
                    self.session_active = False
            except:
                pass
 
if __name__ == "__main__":
    try:
        automation = EmaktabAutomation()
        automation.process_all_accounts()
    except Exception as e: 
        logging.error(f"Critical error: {str(e)}")