import os
import sys
import pytz
import logging
import threading
import traceback
import subprocess
from time import sleep, time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException, NoSuchElementException, WebDriverException
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

POLLING_INTERVAL = 0.5 # Aumentado para 0.5s para reduzir CPU/Logs
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
    
    # Fixando o binário do Chromium na Square Cloud
    if os.path.exists("/usr/bin/chromium"):
        options.binary_location = "/usr/bin/chromium"
    elif os.path.exists("/usr/bin/google-chrome"):
        options.binary_location = "/usr/bin/google-chrome"

    # Bloquear imagens
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
    # ... (Login e setup das abas permanecem iguais, pois funcionaram) ...
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
# 🎮 LÓGICA DE BUSCA RÁPIDA (Foco na Reconexão)
# =============================================================

# Seletores para o histórico (mais robusto)
HISTORY_CONTAINER_SELECTORS = [
    "app-stats-widget",        # Container comum
    ".payouts-block",          # Outro container comum
    ".result-buttons-container" # Container mais externo (ajuda a focar)
]

# Seletores para o primeiro item do histórico
FIRST_PAYOUT_SELECTORS = [
    ".payout:first-child",
    ".bubble-multiplier:first-child",
    ".ng-star-inserted:first-child .bubble-multiplier"
]


def find_game_elements_quick(driver, log_name="GAME"):
    """Tenta encontrar o iframe e o elemento do histórico rapidamente."""
    
    driver.switch_to.default_content() # Volta para o HTML principal
    
    # 1. Busca pelo iframe (o mais comum)
    try:
        # Busca o iframe que contém spribe ou aviator na URL de origem (src)
        iframe = driver.find_element(By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]')
    except NoSuchElementException:
        print(f"❌ {log_name}: Iframe não encontrado.")
        return None, None, None

    # 2. Entra no iframe
    try:
        driver.switch_to.frame(iframe)
    except:
        print(f"❌ {log_name}: Falha ao entrar no Iframe.")
        return None, None, None
    
    # 3. Busca o container de histórico (para focar a busca)
    history_container = None
    for selector in HISTORY_CONTAINER_SELECTORS:
        try:
            history_container = driver.find_element(By.CSS_SELECTOR, selector)
            break
        except:
            continue
            
    if not history_container:
        print(f"❌ {log_name}: Container do histórico não encontrado dentro do iframe.")
        return None, None, None
        
    # 4. Busca o primeiro multiplicador (dentro do container)
    for selector in FIRST_PAYOUT_SELECTORS:
        try:
            # Tenta encontrar o elemento final a partir do container
            first_payout = history_container.find_element(By.CSS_SELECTOR, selector.split(':first-child')[0]) # Tenta achar pelo seletor base
            print(f"🎯 {log_name}: Conexão Estabelecida com '{selector}'")
            # Retornamos o Iframe, o Container e o Seletor do Payout
            return iframe, history_container, selector 
        except:
            continue

    print(f"❌ {log_name}: Primeiro multiplicador não encontrado.")
    return None, None, None


def start_bot(driver, game_handle: str, firebase_path: str):
    nome_log = "AVIATOR 1" if "history" in firebase_path else "AVIATOR 2"
    
    current_iframe = None
    current_container = None
    current_payout_selector = None
    
    # Tentativa inicial de encontrar
    with DRIVER_LOCK:
        try:
            driver.switch_to.window(game_handle)
            current_iframe, current_container, current_payout_selector = find_game_elements_quick(driver, nome_log)
        except Exception as e:
            # Captura exceções mais raras durante o setup inicial
            print(f"⚠️ {nome_log}: Erro no setup inicial: {e}")
            pass

    if not current_iframe:
        print(f"🚨 {nome_log}: Não foi possível inicializar os elementos. Tentando recuperar no loop...")

    LAST_SENT = None
    ULTIMO_MULTIPLIER_TIME = time()

    while not STOP_EVENT.is_set():
        raw_text = None
        
        with DRIVER_LOCK:
            if STOP_EVENT.is_set(): break
            try:
                driver.switch_to.window(game_handle)
                
                # RECONEXÃO: Se perdeu a referência, tenta re-encontrar tudo
                if not current_iframe or not current_payout_selector:
                    current_iframe, current_container, current_payout_selector = find_game_elements_quick(driver, nome_log)
                    if not current_iframe:
                        # Se não achou nada, continua o loop e espera o próximo ciclo
                        raise Exception("Reconexão falhou")

                # Garante que está dentro do iframe e foca no container
                try:
                    driver.switch_to.frame(current_iframe)
                    # Não precisamos re-encontrar o container, só precisamos garantir que o DOM está visível
                except Exception:
                    # Se falhou a troca de frame, força re-conexão completa na próxima
                    current_iframe = None 
                    raise Exception("Falha na troca de frame")

                # Coleta texto (usamos o seletor completo, que inclui ':first-child')
                element = driver.find_element(By.CSS_SELECTOR, current_payout_selector)
                raw_text = element.get_attribute("innerText")
                
            except (StaleElementReferenceException, NoSuchElementException, WebDriverException):
                # Erro comum, reseta para forçar a busca de novo na próxima iteração
                current_iframe = None
                pass 
            except Exception:
                # Erro geral de Selenium, reseta
                current_iframe = None
                pass
        
        # PROCESSAMENTO
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
    print("=== BOT AVIATOR ONLINE (SQUARE CLOUD V4 - SELECTORS FIX) ===")
    while True:
        try:
            rodar_ciclo_monitoramento()
            print("♻️ Reiniciando em 5s...")
            sleep(5)
        except KeyboardInterrupt:
            break
        except Exception:
            sleep(10)
