from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from time import sleep, time
from datetime import datetime, date, timedelta
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, NoSuchElementException
import firebase_admin
from firebase_admin import credentials, db
import os
import pytz
import logging

# =============================================================
# 🔥 GOATHBOT V6.5 - SINGLE DRIVER / DUAL TAB (FINAL)
# =============================================================
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
URL_DO_SITE = "https://www.goathbet.com"

# CONFIGURAÇÃO DOS DOIS JOGOS
BOT_CONFIG_1 = {
    "nome": "ORIGINAL",
    "link": "https://www.goathbet.com/pt/casino/spribe/aviator",
    "firebase_path": "history"
}
BOT_CONFIG_2 = {
    "nome": "AVIATOR 2",
    "link": "https://www.goathbet.com/pt/casino/spribe/aviator-2",
    "firebase_path": "aviator2"
}

# Configuração Limpa de Logs
logging.getLogger('WDM').setLevel(logging.ERROR)
os.environ['WDM_LOG_LEVEL'] = '0'

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
TZ_BR = pytz.timezone("America/Sao_Paulo")

# Configurações de Otimização (LOW DELAY)
POLLING_INTERVAL = 0.1
TEMPO_MAX_INATIVIDADE = 600
RECYCLE_HOURS = 12
LOG_LIMIT = 20

# Variáveis globais para rastreamento (DEFINIÇÃO)
LAST_SENT_1 = None
LAST_SENT_2 = None
LOG_COUNTER_1 = 0
LOG_COUNTER_2 = 0
ULTIMO_MULTIPLIER_TIME_1 = time()
ULTIMO_MULTIPLIER_TIME_2 = time()
HIST_REF_1 = None
HIST_REF_2 = None


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
        driver.switch_to.default_content()
        xpaths = [
            "//button[contains(., 'Sim')]", 
            "//button[@data-age-action='yes']", 
            "//button[contains(., 'Aceitar')]",
            "//button[contains(., 'Entendi')]"
        ]
        for xp in xpaths:
            if safe_click(driver, By.XPATH, xp, 1): break
    except: pass

def process_login(driver):
    try: driver.get(URL_DO_SITE)
    except: pass
    sleep(2)
    check_blocking_modals(driver)

    print("🌍 Tentando Login...")
    if safe_click(driver, By.XPATH, "//button[contains(., 'Entrar')]", 5) or \
       safe_click(driver, By.CSS_SELECTOR, 'a[href*="login"]', 5):
        sleep(1)
        try:
            driver.find_element(By.NAME, "email").send_keys(EMAIL)
            driver.find_element(By.NAME, "password").send_keys(PASSWORD)
            if safe_click(driver, By.CSS_SELECTOR, "button[type='submit']", 5):
                sleep(3)
        except: pass
    
    check_blocking_modals(driver)
    print("✅ Login concluído.")
    return True

def initialize_game_elements(driver, nome, link):
    """Navega, localiza iframe e o elemento de histórico, retornando o ponteiro do histórico."""
    print(f"🌍 [{nome}] Navegando para {link}...")
    driver.get(link)
    
    sleep(5)
    check_blocking_modals(driver)

    try:
        driver.switch_to.default_content() 
        iframe = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator") or contains(@id, "game")]'))
        )
        driver.switch_to.frame(iframe)
    except:
        print(f"❌ [{nome}] Iframe não encontrado.")
        return None

    hist = None
    try:
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
            hist = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".payouts-block, app-stats-widget"))
            )
    except:
        print(f"❌ [{nome}] Elemento de histórico não encontrado.")
        return None

    print(f"✅ [{nome}] Elementos inicializados.")
    return hist

def getColorClass(value):
    try:
        m = float(value)
        if 1.0 <= m < 2.0: return "blue-bg"
        if 2.0 <= m < 10.0: return "purple-bg"
        if m >= 10.0: return "magenta-bg"
        return "default-bg"
    except: return "default-bg"

def read_and_send(driver, config, is_first_bot):
    """Função que lê o multiplicador e envia para o Firebase, com recuperação de Stale Element."""
    # Declaração global de TODAS as variáveis globais que serão MODIFICADAS aqui.
    global LAST_SENT_1, LAST_SENT_2, LOG_COUNTER_1, LOG_COUNTER_2, ULTIMO_MULTIPLIER_TIME_1, ULTIMO_MULTIPLIER_TIME_2
    global HIST_REF_1, HIST_REF_2 

    nome = config["nome"]
    path_fb = config["firebase_path"]
    
    # Referencia as variáveis corretas
    LAST_SENT = LAST_SENT_1 if is_first_bot else LAST_SENT_2
    LOG_COUNTER = LOG_COUNTER_1 if is_first_bot else LOG_COUNTER_2
    ULTIMO_MULTIPLIER_TIME = ULTIMO_MULTIPLIER_TIME_1 if is_first_bot else ULTIMO_MULTIPLIER_TIME_2
    HIST_REF = HIST_REF_1 if is_first_bot else HIST_REF_2

    if not HIST_REF:
        print(f"⚠️ [{nome}] Referência de histórico perdida. Forçando reinício completo.")
        raise Exception("Referência HIST perdida.")

    try:
        # 1. Check Inatividade
        if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
            raise Exception("Inatividade detectada - Forçando reinício do driver")

        # 2. Leitura
        driver.switch_to.default_content() 
        iframe = driver.find_element(By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator") or contains(@id, "game")]')
        driver.switch_to.frame(iframe)

        items = HIST_REF.find_elements(By.CSS_SELECTOR, ".payout, .bubble-multiplier, app-bubble-multiplier, .payout-item, .history-item")
        
        if not items:
            return 

        first_payout = items[0]
        raw_text = first_payout.get_attribute("innerText")
        clean_text = raw_text.strip().lower().replace('x', '')

        if not clean_text:
            return 

        try:
            novo = float(clean_text)
        except ValueError:
            return
        
        # 3. Envio
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
                
                LOG_COUNTER += 1
                if LOG_COUNTER % LOG_LIMIT == 0:
                    print(f"✅ [{nome}] Envio de {LOG_LIMIT} logs concluído. Último: {entry['multiplier']}x")
                    LOG_COUNTER = 0
                elif LOG_COUNTER < LOG_LIMIT:
                    print(f"🔥 [{nome}] {entry['multiplier']}x")
                    
                LAST_SENT = novo
            except Exception as e:
                print(f"⚠️ [{nome}] Erro Firebase: {e}")
        
    except StaleElementReferenceException:
        # Tenta recuperar a referência do elemento 'hist' sem reiniciar o driver
        print(f"⚠️ [{nome}] DOM mudou (Stale). Tentando re-inicializar o elemento 'hist'...")
        driver.switch_to.default_content()
        driver.switch_to.window(driver.current_window_handle)
        
        # O initialize_game_elements vai navegar para a URL correta e re-encontrar o iframe e o hist
        hist_new = initialize_game_elements(driver, nome, config["link"]) 

        if hist_new:
            if is_first_bot:
                HIST_REF_1 = hist_new
            else:
                HIST_REF_2 = hist_new
            print(f"✅ [{nome}] Elemento 'hist' recuperado. Continuando leitura.")
            return
        else:
            raise Exception("Falha crítica ao re-inicializar elementos após Stale.")

    except Exception as e:
        print(f"⚠️ [{nome}] Erro genérico na leitura: {e}. Forçando reinício...")
        raise e

    # Atualiza as variáveis globais de rastreamento (LAST_SENT, LOG_COUNTER, ULTIMO_MULTIPLIER_TIME)
    if is_first_bot:
        LAST_SENT_1 = LAST_SENT
        LOG_COUNTER_1 = LOG_COUNTER
        ULTIMO_MULTIPLIER_TIME_1 = ULTIMO_MULTIPLIER_TIME
    else:
        LAST_SENT_2 = LAST_SENT
        LOG_COUNTER_2 = LOG_COUNTER
        ULTIMO_MULTIPLIER_TIME_2 = ULTIMO_MULTIPLIER_TIME


# =============================================================
# 🤖 LÓGICA PRINCIPAL (MONITORAMENTO DUAL)
# =============================================================
def run_dual_bot():
    """Função que roda os dois bots em um único driver."""
    
    # 🚨 CORREÇÃO DE ERRO: As declarações globais DEVE SER AS PRIMEIRAS!
    global HIST_REF_1, HIST_REF_2 
    
    relogin_date = date.today()
    next_recycle_time = datetime.now(TZ_BR) + timedelta(hours=RECYCLE_HOURS)

    while True:
        driver = None
        try:
            print("🔄 Iniciando driver único...")
            driver = start_driver()
            
            # --- Configuração inicial ---
            process_login(driver)
            
            # 1. Configura Bot 1 (Aba principal)
            HIST_REF_1 = initialize_game_elements(driver, BOT_CONFIG_1["nome"], BOT_CONFIG_1["link"])
            handle1 = driver.current_window_handle
            
            # 2. Configura Bot 2 (Nova aba)
            driver.execute_script("window.open('');")
            sleep(1)
            handles = driver.window_handles
            handle2 = handles[1] if len(handles) > 1 else handles[0]
            
            driver.switch_to.window(handle2)
            HIST_REF_2 = initialize_game_elements(driver, BOT_CONFIG_2["nome"], BOT_CONFIG_2["link"])

            if not HIST_REF_1 or not HIST_REF_2: 
                raise Exception("Falha ao inicializar elementos de um ou ambos os jogos.")

            print("\n==============================================")
            print("🚀 MONITORAMENTO DUAL ATIVO EM UM SÓ DRIVER!")
            print("==============================================\n")
            
            while True: # Loop de leitura
                
                # 1. Manutenção Diária/Reciclagem Agendada
                now_br = datetime.now(TZ_BR)
                
                if now_br.hour == 0 and now_br.minute <= 5 and (relogin_date != now_br.date()):
                    print("🌙 Reinício diário iniciado...")
                    driver.quit()
                    relogin_date = now_br.date()
                    break 
                
                if now_br >= next_recycle_time:
                    print(f"♻️ Reinício periódico (Reciclagem de Driver) iniciado...")
                    driver.quit()
                    next_recycle_time = now_br + timedelta(hours=RECYCLE_HOURS)
                    break 

                # 2. Leitura Bot 1
                driver.switch_to.window(handle1)
                read_and_send(driver, BOT_CONFIG_1, is_first_bot=True)

                # 3. Leitura Bot 2
                driver.switch_to.window(handle2)
                read_and_send(driver, BOT_CONFIG_2, is_first_bot=False)

                # Pausa mínima
                sleep(POLLING_INTERVAL)

        except Exception as e:
            print(f"❌ Falha Crítica: {e}. Reiniciando o driver em 15s...")
            if driver:
                try: driver.quit()
                except: pass
            sleep(15)

# =============================================================
# 🚀 EXECUTOR
# =============================================================
if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD nas variáveis de ambiente.")
    else:
        run_dual_bot()
