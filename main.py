import os
import sys
import pytz
import logging
import threading
import traceback
import subprocess
from time import sleep, time
from datetime import datetime

# Bibliotecas externas
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

import firebase_admin
from firebase_admin import credentials, db

# =============================================================
# ⚠️ CONTROLE GLOBAL
# =============================================================
DRIVER_LOCK = threading.Lock() 
STOP_EVENT = threading.Event()

# =============================================================
# 🔥 CONFIGURAÇÃO FIREBASE
# =============================================================
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'

if not os.path.exists(SERVICE_ACCOUNT_FILE):
    print(f"❌ ERRO CRÍTICO: O arquivo {SERVICE_ACCOUNT_FILE} não foi encontrado!")
    sys.exit(1)

try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
    print("✅ Firebase Admin SDK inicializado.")
except Exception as e:
    print(f"\n❌ ERRO CONEXÃO FIREBASE: {e}")
    sys.exit(1)

# =============================================================
# ⚙️ VARIÁVEIS DE AMBIENTE
# =============================================================
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

if not EMAIL or not PASSWORD:
    print("❌ ERRO: Configure as variáveis EMAIL e PASSWORD no painel da Square Cloud.")
    sys.exit(1)

URL_DO_SITE = "https://www.goathbet.com"
LINK_AVIATOR_ORIGINAL = "https://www.goathbet.com/pt/casino/spribe/aviator"
LINK_AVIATOR_2 = "https://www.goathbet.com/pt/casino/spribe/aviator-2"
FIREBASE_PATH_ORIGINAL = "history"
FIREBASE_PATH_2 = "aviator2"

POLLING_INTERVAL = 0.5 # Levemente mais lento para garantir leitura do DOM
TEMPO_MAX_INATIVIDADE = 360 
TZ_BR = pytz.timezone("America/Sao_Paulo")

# =============================================================
# 🔧 FUNÇÕES AUXILIARES
# =============================================================
def getColorClass(value):
    try:
        m = float(value)
        if 1.0 <= m < 2.0: return "blue-bg"
        if 2.0 <= m < 10.0: return "purple-bg"
        if m >= 10.0: return "magenta-bg"
        return "default-bg"
    except: return "default-bg"

def enviar_firebase_async(path, data):
    def _send():
        try:
            db.reference(path).set(data)
            nome_jogo = "AVIATOR 1" if "history" in path else "AVIATOR 2"
            print(f"🔥 {nome_jogo}: {data['multiplier']}x às {data['time']}")
        except Exception as e:
            print(f"⚠️ Erro ao enviar Firebase: {e}")
    threading.Thread(target=_send, daemon=True).start()

def verificar_modais_bloqueio(driver):
    botoes = ["//button[contains(., 'Sim')]", "//button[contains(., 'Aceitar')]", "//button[contains(., 'Fechar')]"]
    for xpath in botoes:
        try:
            btn = driver.find_element(By.XPATH, xpath)
            if btn.is_displayed(): 
                btn.click()
                sleep(0.5)
        except: pass

# =============================================================
# 🚀 DRIVER OTIMIZADO PARA NUVEM
# =============================================================
def initialize_driver_instance():
    if os.name == 'nt':
        try:
            subprocess.run("taskkill /f /im chromedriver.exe", shell=True, stderr=subprocess.DEVNULL)
            subprocess.run("taskkill /f /im chrome.exe", shell=True, stderr=subprocess.DEVNULL)
        except: pass

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage") 
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--mute-audio")
    options.add_argument("--window-size=1366,768")
    options.add_argument("--log-level=3")
    options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    if os.path.exists("/usr/bin/chromium"):
        options.binary_location = "/usr/bin/chromium"
    elif os.path.exists("/usr/bin/google-chrome"):
        options.binary_location = "/usr/bin/google-chrome"

    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2,
        "profile.managed_default_content_settings.stylesheets": 2,
    }
    options.add_experimental_option("prefs", prefs)

    print("🔧 Iniciando Driver (Modo Linux/Chromium)...")
    try:
        service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
        return webdriver.Chrome(service=service, options=options)
    except Exception as e:
        print(f"❌ Falha ao iniciar Driver: {e}")
        raise e

def setup_tabs(driver):
    print("➡️ Acessando site...")
    try:
        driver.get(URL_DO_SITE)
        sleep(5)
        verificar_modais_bloqueio(driver)

        # Login
        try:
            btns = driver.find_elements(By.XPATH, "//button[contains(., 'Entrar')]")
            if btns: 
                btns[0].click()
                sleep(2)
            
            driver.find_element(By.NAME, "email").send_keys(EMAIL)
            driver.find_element(By.NAME, "password").send_keys(PASSWORD)
            sleep(1)
            driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
            print("✅ Login enviado.")
            sleep(10)
        except Exception as e:
            print(f"⚠️ Aviso login: {e}")

        # Aba 1
        driver.get(LINK_AVIATOR_ORIGINAL)
        sleep(5)
        handle_original = driver.current_window_handle
        print(f"✅ Aba 1 OK.")

        # Aba 2
        driver.execute_script("window.open('');")
        sleep(2)
        handles = driver.window_handles
        handle_aviator2 = [h for h in handles if h != handle_original][0]
        
        driver.switch_to.window(handle_aviator2)
        driver.get(LINK_AVIATOR_2)
        sleep(5)
        print(f"✅ Aba 2 OK.")
        
        driver.switch_to.window(handle_original) 
        
        return {
            FIREBASE_PATH_ORIGINAL: handle_original,
            FIREBASE_PATH_2: handle_aviator2
        }
    except Exception as e:
        print(f"❌ Erro no setup das abas: {e}")
        raise e

# =============================================================
# 🎮 LÓGICA DE BUSCA AVANÇADA (SCANNER DE IFRAMES)
# =============================================================

# Lista de seletores possíveis para o histórico
SELECTORS_HISTORY = [
    ".payouts-block .payout:first-child",
    "app-stats-widget .payout:first-child",
    ".bubble-multiplier:first-child",
    ".payout.ng-star-inserted:first-child",
    "app-history-item .bubble-multiplier"
]

def find_game_elements_robust(driver, log_name="GAME"):
    """
    Tenta encontrar o iframe correto varrendo todos os iframes da página
    e testando se existe um elemento de histórico dentro dele.
    """
    # 1. Tenta achar iframes pelo SRC primeiro (método rápido)
    try:
        possible_iframes = driver.find_elements(By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]')
        for index, frame in enumerate(possible_iframes):
            try:
                driver.switch_to.default_content()
                driver.switch_to.frame(frame)
                
                # Testa seletores
                for selector in SELECTORS_HISTORY:
                    elems = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elems and len(elems) > 0:
                        print(f"🎯 {log_name}: Elemento encontrado no iframe {index} com seletor '{selector}'")
                        return frame, selector # Retorna o iframe e o seletor que funcionou
            except:
                continue
    except: pass

    # 2. Se falhar, varredura bruta em TODOS os iframes (método lento mas garantido)
    try:
        print(f"🔎 {log_name}: Modo busca profunda de iframes...")
        driver.switch_to.default_content()
        all_iframes = driver.find_elements(By.TAG_NAME, "iframe")
        
        for index, frame in enumerate(all_iframes):
            try:
                driver.switch_to.default_content()
                driver.switch_to.frame(frame)
                
                for selector in SELECTORS_HISTORY:
                    if len(driver.find_elements(By.CSS_SELECTOR, selector)) > 0:
                        print(f"🎯 {log_name}: ACHOU no Iframe Profundo #{index} com '{selector}'")
                        return frame, selector
            except: pass
    except: pass

    return None, None

def start_bot(driver, game_handle: str, firebase_path: str):
    nome_log = "AVIATOR 1" if "history" in firebase_path else "AVIATOR 2"
    
    current_iframe = None
    current_selector = None
    
    # Tentativa inicial de encontrar
    with DRIVER_LOCK:
        try:
            driver.switch_to.window(game_handle)
            current_iframe, current_selector = find_game_elements_robust(driver, nome_log)
        except: pass

    LAST_SENT = None
    ULTIMO_MULTIPLIER_TIME = time()

    while not STOP_EVENT.is_set():
        raw_text = None
        
        with DRIVER_LOCK:
            if STOP_EVENT.is_set(): break
            try:
                driver.switch_to.window(game_handle)
                
                # Lógica de re-conexão ao elemento
                if not current_iframe or not current_selector:
                    current_iframe, current_selector = find_game_elements_robust(driver, nome_log)
                    if not current_iframe:
                        # Se não achou nada, sai do lock e espera tentar de novo
                        raise Exception("Frame não encontrado")

                # Garante que estamos dentro do iframe
                try:
                    driver.find_element(By.CSS_SELECTOR, current_selector)
                except:
                    # Se não achou o elemento, tenta entrar no frame de novo
                    driver.switch_to.default_content()
                    driver.switch_to.frame(current_iframe)

                # Coleta texto
                element = driver.find_element(By.CSS_SELECTOR, current_selector)
                raw_text = element.get_attribute("innerText")
                
            except Exception:
                # Se falhar algo crítico, reseta para forçar nova busca
                # print(f"⚠️ {nome_log}: Falha leitura. Retentando...")
                # current_iframe = None # Descomente se quiser resetar busca a cada erro
                pass
        
        if raw_text:
            clean_text = raw_text.strip().lower().replace('x', '')
            if clean_text:
                try:
                    novo_valor = float(clean_text)
                    if novo_valor != LAST_SENT:
                        now_br = datetime.now(TZ_BR)
                        payload = {
                            "multiplier": f"{novo_valor:.2f}",
                            "time": now_br.strftime("%H:%M:%S"),
                            "color": getColorClass(novo_valor),
                            "date": now_br.strftime("%Y-%m-%d")
                        }
                        key = now_br.strftime("%Y-%m-%d_%H-%M-%S-%f")
                        enviar_firebase_async(f"{firebase_path}/{key}", payload)
                        
                        LAST_SENT = novo_valor
                        ULTIMO_MULTIPLIER_TIME = time()
                        
                        # Reseta inatividade se achou valor
                except: pass

        # Timeout de inatividade
        if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
            print(f"🚨 {nome_log}: Inativo por {TEMPO_MAX_INATIVIDADE}s (Página travada ou manutenção). Reiniciando...")
            STOP_EVENT.set()
            return 
        
        # Reinício diário
        now = datetime.now(TZ_BR)
        if now.hour == 23 and now.minute == 59 and now.second < 10:
            STOP_EVENT.set()
            return
            
        sleep(POLLING_INTERVAL)

# =============================================================
# 🚀 SUPERVISOR
# =============================================================
def rodar_ciclo_monitoramento():
    driver = None
    STOP_EVENT.clear()
    
    try:
        print("\n🔵 Iniciando ciclo...")
        driver = initialize_driver_instance()
        handles = setup_tabs(driver)
        
        t1 = threading.Thread(target=start_bot, args=(driver, handles[FIREBASE_PATH_ORIGINAL], FIREBASE_PATH_ORIGINAL))
        t2 = threading.Thread(target=start_bot, args=(driver, handles[FIREBASE_PATH_2], FIREBASE_PATH_2))

        t1.start()
        t2.start()

        while t1.is_alive() or t2.is_alive():
            if STOP_EVENT.is_set(): break
            sleep(2)
            
    except Exception as e:
        print(f"❌ Erro Supervisor: {e}")
        traceback.print_exc()
    finally:
        STOP_EVENT.set()
        if driver:
            try:
                driver.quit()
                print("🗑️ Driver limpo.")
            except: pass

if __name__ == "__main__":
    print("=== BOT AVIATOR ONLINE (SQUARE CLOUD V3) ===")
    while True:
        try:
            rodar_ciclo_monitoramento()
            print("♻️ Reiniciando em 5s...")
            sleep(5)
        except KeyboardInterrupt:
            break
        except Exception:
            sleep(10)
