from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from time import sleep, time
from datetime import datetime, date
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, NoSuchElementException
import firebase_admin
from firebase_admin import credentials, db
import os
import pytz
import logging
import threading

# =============================================================
# 🔥 GOATHBOT V6.1 - DUAL MODE (CORRIGIDO)
# =============================================================
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
URL_DO_SITE = "https://www.goathbet.com"

# CONFIGURAÇÃO DOS DOIS JOGOS
CONFIG_BOTS = [
    {
        "nome": "ORIGINAL",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator",
        "firebase_path": "history"
    },
    {
        "nome": "AVIATOR 2",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator-2",
        "firebase_path": "aviator2"
    }
]

# Configuração Limpa de Logs
logging.getLogger('WDM').setLevel(logging.ERROR)
os.environ['WDM_LOG_LEVEL'] = '0'

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
TZ_BR = pytz.timezone("America/Sao_Paulo")

# Configurações Turbo
POLLING_INTERVAL = 0.5 # Aumentei levemente para evitar sobrecarga de leitura
TEMPO_MAX_INATIVIDADE = 600 # 10 minutos tolerância

# =============================================================
# 🔧 FIREBASE
# =============================================================
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
    print("✅ Conexão Firebase estabelecida.")
except Exception as e:
    print(f"\n❌ ERRO CRÍTICO NO FIREBASE: {e}")

# =============================================================
# 🛠️ DRIVER E NAVEGAÇÃO
# =============================================================
def start_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--headless=new") 
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.page_load_strategy = 'eager'
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--log-level=3")
    options.add_argument("--silent")

    try:
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    except:
        # Fallback para servidores Linux
        import shutil
        chromedriver_path = shutil.which("chromedriver") or "/usr/bin/chromedriver"
        return webdriver.Chrome(service=Service(chromedriver_path), options=options)

def safe_click(driver, by, value, timeout=5):
    try:
        element = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        driver.execute_script("arguments[0].click();", element)
        return True
    except: return False

def check_blocking_modals(driver):
    """Fecha popups chatos"""
    try:
        xpaths = [
            "//button[contains(., 'Sim')]", 
            "//button[@data-age-action='yes']", 
            "//div[contains(text(), '18')]/following::button[1]",
            "//button[contains(., 'Aceitar')]"
        ]
        for xp in xpaths:
            if safe_click(driver, By.XPATH, xp, 1): break
    except: pass

def process_login(driver, target_link):
    # 1. Acessa Home e faz Login
    try: driver.get(URL_DO_SITE)
    except: pass
    sleep(2)
    check_blocking_modals(driver)

    if safe_click(driver, By.XPATH, "//button[contains(., 'Entrar')]", 5) or \
       safe_click(driver, By.CSS_SELECTOR, 'a[href*="login"]', 5):
        sleep(1)
        try:
            driver.find_element(By.NAME, "email").send_keys(EMAIL)
            driver.find_element(By.NAME, "password").send_keys(PASSWORD)
            if safe_click(driver, By.CSS_SELECTOR, "button[type='submit']", 5):
                sleep(3)
        except: pass
    
    # 2. Navega para o jogo específico
    print(f"🌍 Navegando para {target_link}...")
    driver.get(target_link)
    
    # Aguarda carregamento inicial maior para garantir scripts da página
    sleep(5)
    check_blocking_modals(driver)
    return True

def initialize_game_elements(driver):
    """Tenta localizar o iframe e o elemento de histórico de forma robusta."""
    try:
        driver.switch_to.default_content()
    except: pass
    
    iframe = None
    try:
        # Procura iframes da Spribe ou genéricos de jogo
        iframe = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator") or contains(@id, "game")]'))
        )
        driver.switch_to.frame(iframe)
    except:
        return None, None

    hist = None
    try:
        # Tenta múltiplos seletores para o container do histórico
        seletores = [
            ".payouts-block", 
            "app-stats-widget", 
            ".stats-container",
            ".history-container",
            "app-history"
        ]
        
        for sel in seletores:
            try:
                found = driver.find_elements(By.CSS_SELECTOR, sel)
                if found:
                    hist = found[0]
                    break
            except: continue
            
        if not hist:
            # Tenta fallback com wait explícito no mais comum
            hist = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".payouts-block, app-stats-widget"))
            )
    except:
        return None, None

    return iframe, hist

def getColorClass(value):
    try:
        m = float(value)
        if 1.0 <= m < 2.0: return "blue-bg"
        if 2.0 <= m < 10.0: return "purple-bg"
        if m >= 10.0: return "magenta-bg"
        return "default-bg"
    except: return "default-bg"

# =============================================================
# 🤖 LÓGICA DE SESSÃO INDIVIDUAL (THREAD)
# =============================================================
def run_single_bot(bot_config):
    """Função que roda o ciclo de vida completo de UM bot"""
    nome = bot_config["nome"]
    link = bot_config["link"]
    path_fb = bot_config["firebase_path"]
    
    relogin_date = date.today()

    while True: # Loop infinito de reconexão se cair
        driver = None
        try:
            print(f"🔄 [{nome}] Iniciando driver...")
            driver = start_driver()
            process_login(driver, link)

            iframe, hist = initialize_game_elements(driver)
            if not hist: 
                print(f"❌ [{nome}] Elementos não encontrados no início. Tentando novamente...")
                driver.quit()
                sleep(5)
                continue

            print(f"🚀 [{nome}] MONITORANDO EM '{path_fb}'")
            
            LAST_SENT = None
            ULTIMO_MULTIPLIER_TIME = time()
            
            while True: # Loop de leitura
                # 1. Manutenção Diária
                now_br = datetime.now(TZ_BR)
                if now_br.hour == 0 and now_br.minute <= 5 and (relogin_date != now_br.date()):
                    print(f"🌙 [{nome}] Reinício diário...")
                    driver.quit()
                    relogin_date = now_br.date()
                    break 

                # 2. Check Inatividade
                if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
                    raise Exception("Inatividade detectada - Jogo pode ter travado")

                # 3. Leitura e Processamento (Robustez aplicada)
                try:
                    # Busca lista de elementos (plural) para não dar erro fatal se vazio
                    items = hist.find_elements(By.CSS_SELECTOR, ".payout, .bubble-multiplier, app-bubble-multiplier, .payout-item, .history-item")
                    
                    if not items:
                        # Se achou o container mas não tem itens, espera e tenta de novo
                        sleep(POLLING_INTERVAL)
                        continue

                    # Geralmente o primeiro item é o mais recente
                    first_payout = items[0]
                    raw_text = first_payout.get_attribute("innerText")
                    clean_text = raw_text.strip().lower().replace('x', '')

                    if not clean_text:
                        sleep(POLLING_INTERVAL)
                        continue

                    try:
                        novo = float(clean_text)
                    except ValueError:
                        sleep(POLLING_INTERVAL)
                        continue
                    
                    # 4. Envio
                    if novo != LAST_SENT:
                        ULTIMO_MULTIPLIER_TIME = time()
                        now_br = datetime.now(TZ_BR)
                        
                        entry = {
                            "multiplier": f"{novo:.2f}",
                            "time": now_br.strftime("%H:%M:%S"),
                            "color": getColorClass(novo),
                            "date": now_br.strftime("%Y-%m-%d")
                        }
                        key = now_br.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-')
                        
                        try:
                            db.reference(f"{path_fb}/{key}").set(entry)
                            print(f"🔥 [{nome}] {entry['multiplier']}x")
                            LAST_SENT = novo
                        except Exception as e:
                            print(f"⚠️ [{nome}] Erro Firebase: {e}")

                    sleep(POLLING_INTERVAL)

                except (StaleElementReferenceException, TimeoutException) as e:
                    # Elemento mudou/sumiu. Tenta re-inicializar apenas os ponteiros, sem reiniciar driver
                    print(f"⚠️ [{nome}] DOM mudou (Stale). Atualizando elementos...")
                    driver.switch_to.default_content()
                    iframe, hist = initialize_game_elements(driver)
                    if not hist:
                        raise Exception("Não foi possível recuperar elementos após Stale.")
                    sleep(1)
                
                except NoSuchElementException:
                    # Elemento não existe no momento, apenas continua
                    sleep(POLLING_INTERVAL)

        except Exception as e:
            print(f"❌ [{nome}] Falha Crítica: {e}. Reiniciando em 10s...")
            if driver:
                try: driver.quit()
                except: pass
            sleep(10)

# =============================================================
# 🚀 EXECUTOR PARALELO
# =============================================================
if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD nas variáveis de ambiente.")
    else:
        print("==============================================")
        print("    GOATHBOT V6.1 - DUAL MONITORING FIX")
        print("==============================================")

        threads = []
        for config in CONFIG_BOTS:
            t = threading.Thread(target=run_single_bot, args=(config,))
            t.start()
            threads.append(t)
            sleep(5) # Pausa maior entre inícios para não sobrecarregar login simultâneo

        for t in threads:
            t.join()
