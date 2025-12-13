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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType 

# Configurações de terceiros (Firebase)
import firebase_admin
from firebase_admin import credentials, db

# =============================================================
# ⚠️ CONTROLE GLOBAL DE THREADS E DRIVER
# =============================================================
DRIVER_LOCK = threading.Lock() 
STOP_EVENT = threading.Event() 

# =============================================================
# 🔥 GOATHBOT V8 - DUAL MODE (FIX LEITURA FINAL)
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

logging.getLogger('WDM').setLevel(logging.ERROR)
os.environ['WDM_LOG_LEVEL'] = '0'

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
TZ_BR = pytz.timezone("America/Sao_Paulo")

# Configurações Turbo
POLLING_INTERVAL = 0.5 
TEMPO_MAX_INATIVIDADE = 360     

# Lista de Seletores Refinados V8: Foco no elemento que tem o número
FIRST_PAYOUT_SELECTORS_V8 = [
    ".payouts-block .payout:first-child",                 # Tenta achar o item dentro do bloco
    "app-stats-widget .payout:first-child",               # Outra variação do container
    ".bubble-multiplier:first-child",                     # O mais comum (o número puro)
    "app-history-item:first-child .bubble-multiplier",    # Com o container da vela (item)
    "//div[starts-with(@class, 'bubble-multiplier')][1]", # XPath mais específico para o número
    "//div[contains(@class, 'payouts-block')]//div[starts-with(@class, 'payout')][1]" # Dentro do container
]


# =============================================================
# 🔧 FIREBASE E AUXILIARES (Sem mudanças)
# =============================================================
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
    print("✅ Conexão Firebase estabelecida.")
except Exception as e:
    print(f"\n❌ ERRO CRÍTICO NO FIREBASE: {e}")
    sys.exit()

def getColorClass(value):
    try:
        m = float(value)
        if 1.0 <= m < 2.0: return "blue-bg"
        if 2.0 <= m < 10.0: return "purple-bg"
        if m >= 10.0: return "magenta-bg"
        return "default-bg"
    except: return "default-bg"

def enviar_firebase_async(path, data, nome_jogo):
    def _send():
        try:
            key = datetime.now(TZ_BR).strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '')
            db.reference(f"{path}/{key}").set(data)
            print(f"🔥 [{nome_jogo.upper()}] ENVIADO: {data['multiplier']}x às {data['time']}")
        except Exception:
            pass 
    threading.Thread(target=_send).start()

def verificar_modais_bloqueio(driver):
    xpaths = [
        "//button[contains(., 'Sim')]", 
        "//button[@data-age-action='yes']", 
        "//div[contains(text(), '18')]/following::button[1]",
        "//button[contains(., 'Aceitar')]",
        "//button[contains(., 'Fechar')]" 
    ]
    for xp in xpaths:
        try:
            btn = driver.find_element(By.XPATH, xp)
            if btn.is_displayed(): 
                driver.execute_script("arguments[0].click();", btn)
                sleep(0.5)
        except: pass

# =============================================================
# 🛠️ DRIVER E NAVEGAÇÃO (Sem mudanças)
# =============================================================
def initialize_driver_instance():
    try:
        if os.name == 'nt': 
            subprocess.run("taskkill /f /im chromedriver.exe", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            subprocess.run("taskkill /f /im chrome.exe", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    except: pass

    options = webdriver.ChromeOptions()
    options.page_load_strategy = 'eager'
    options.add_argument("--headless=new") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3")
    options.add_argument("--silent")
    options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # FIX CRÍTICO PARA SQUARE CLOUD / LINUX
    if os.path.exists("/usr/bin/chromium"):
        options.binary_location = "/usr/bin/chromium"

    try:
        print("🔧 Iniciando Driver (Modo Linux/Chromium)...")
        service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
        return webdriver.Chrome(service=service, options=options)
    except Exception as e:
        try:
            print(f"⚠️ Erro ao usar Chromium fix: {e}. Tentando fallback...")
            return webdriver.Chrome(options=options)
        except Exception as e_fallback:
            print(f"❌ Falha crítica ao iniciar Driver: {e_fallback}")
            raise e_fallback 


def setup_tabs_and_login(driver):
    print("➡️ Acessando site e configurando abas...")
    
    try:
        driver.get(URL_DO_SITE)
        sleep(5)
        verificar_modais_bloqueio(driver)

        btns = driver.find_elements(By.XPATH, "//button[contains(., 'Entrar')] | //a[contains(@href, 'login')]") 
        if btns: 
            driver.execute_script("arguments[0].click();", btns[0])
            sleep(1)
            
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "email"))).send_keys(EMAIL)
        driver.find_element(By.NAME, "password").send_keys(PASSWORD)
        sleep(0.5)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        print("✅ Login enviado.")
        sleep(8) 
        verificar_modais_bloqueio(driver) 
    except Exception as e:
        print(f"⚠️ Aviso no login ou popups: {e}")

    # Configura Abas
    handles = {}
    config1 = CONFIG_BOTS[0]
    driver.get(config1["link"])
    sleep(5)
    handles[config1["firebase_path"]] = driver.current_window_handle
    print(f"✅ Aba {config1['nome']} configurada.")

    config2 = CONFIG_BOTS[1]
    driver.execute_script("window.open('');")
    new_handle = [h for h in driver.window_handles if h != driver.current_window_handle][0]
    
    driver.switch_to.window(new_handle)
    driver.get(config2["link"])
    sleep(5)
    handles[config2["firebase_path"]] = driver.current_window_handle
    print(f"✅ Aba {config2['nome']} configurada.")
    
    driver.switch_to.window(handles[config1["firebase_path"]]) 
    
    return handles

# =============================================================
# 🎮 BUSCA DE ELEMENTOS V8 (Apenas para achar o seletor)
# =============================================================
def find_game_elements_v8(driver, game_handle, nome_log):
    try:
        driver.switch_to.window(game_handle)
        driver.switch_to.default_content()
        
        iframe = WebDriverWait(driver, 10).until( 
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'))
        )
        # ⚠️ FIX V8: Tenta entrar no iframe imediatamente para evitar 'stale'
        driver.switch_to.frame(iframe) 
        
        for selector in FIRST_PAYOUT_SELECTORS_V8:
            try:
                by_type = By.CSS_SELECTOR if not selector.startswith('//') else By.XPATH
                # Dá 5 segundos para o elemento interno carregar
                WebDriverWait(driver, 5).until(EC.presence_of_element_located((by_type, selector)))
                
                print(f"🎯 [{nome_log}] Conexão Estabelecida! Seletor: '{selector}'")
                return iframe, selector 
            except TimeoutException:
                continue
            except NoSuchElementException:
                continue
            
        print(f"❌ [{nome_log}] NENHUM multiplicador encontrado após varrer todos os seletores.")
        return None, None 

    except Exception as e:
        print(f"❌ [{nome_log}] Erro durante a busca de elementos: {e}")
        return None, None

# =============================================================
# 🔄 LOOP DE CAPTURA COM FIX DE LEITURA (THREAD)
# =============================================================
def start_bot_thread(driver, bot_config: dict, game_handle: str):
    nome_log = bot_config['nome']
    firebase_path = bot_config['firebase_path']
    print(f"🚀 THREAD INICIADA: {nome_log} -> {firebase_path}")

    iframe, payout_selector = find_game_elements_v8(driver, game_handle, nome_log)
    if not iframe:
        print(f"🚨 [{nome_log}] Falha inicial ao carregar. Tentando recuperar no loop...")

    LAST_SENT = None
    ULTIMO_MULTIPLIER_TIME = time()
    
    while not STOP_EVENT.is_set():
        raw_text = None
        
        # === SEÇÃO CRÍTICA (Acesso ao Driver) ===
        with DRIVER_LOCK:
            if STOP_EVENT.is_set(): break

            try:
                driver.switch_to.window(game_handle)
                
                # Re-busca se os elementos sumiram ou não foram encontrados
                if not iframe or not payout_selector:
                    iframe, payout_selector = find_game_elements_v8(driver, game_handle, nome_log)
                    if not iframe: raise Exception("Falha ao localizar elementos.")

                # Tenta entrar no iframe
                driver.switch_to.frame(iframe) # ⚠️ O iframe precisa ser o objeto retornado (o que já fazemos)

                by_type = By.CSS_SELECTOR if not payout_selector.startswith('//') else By.XPATH
                first_payout = driver.find_element(by_type, payout_selector)
                
                # *** FIX CRÍTICO V7/V8: LEITURA ABRANGENTE ***
                text_candidates = [
                    first_payout.text,
                    first_payout.get_attribute("innerText"),
                    first_payout.get_attribute("textContent"),
                    first_payout.get_attribute("innerHTML")
                ]
                
                # ⚠️ NOVO FIX V8: Tenta encontrar o texto válido em qualquer um dos atributos lidos
                found_valid_text = False
                for t in text_candidates:
                    if t:
                        temp_clean = t.strip().lower().replace('x', '').replace(',', '.')
                        try:
                            # Tenta converter para float e verifica se é um multiplicador válido
                            if float(temp_clean) >= 1.0: 
                                raw_text = t # Usa o texto original para debug, mas processa o limpo
                                found_valid_text = True
                                break
                        except ValueError:
                            continue
                
                if not found_valid_text:
                    # Se não achou texto válido, loga o que o bot viu no innerHTML
                    print(f"⚠️ [{nome_log}] DEBUG: Conteúdo lido vazio/inválido. Tentativas (innerHTML): {first_payout.get_attribute('innerHTML')}")
                
            except (StaleElementReferenceException, NoSuchElementException, WebDriverException, Exception):
                iframe = None 
                payout_selector = None
                driver.switch_to.default_content() # Volta para o default para evitar travamento
                continue 
        # === FIM DA SEÇÃO CRÍTICA ===
        
        # PROCESSAMENTO
        if raw_text:
            clean_text = raw_text.strip().lower().replace('x', '').replace(',', '.')
            
            if clean_text:
                try:
                    novo_valor = float(clean_text)
                except ValueError:
                    continue 

                if novo_valor != LAST_SENT:
                    if novo_valor < 1.0:
                        continue 
                        
                    now_br = datetime.now(TZ_BR)
                    
                    payload = {
                        "multiplier": f"{novo_valor:.2f}",
                        "time": now_br.strftime("%H:%M:%S"),
                        "color": getColorClass(novo_valor),
                        "date": now_br.strftime("%Y-%m-%d")
                    }
                    
                    enviar_firebase_async(firebase_path, payload, nome_log)

                    LAST_SENT = novo_valor
                    ULTIMO_MULTIPLIER_TIME = time()
        
        # 1. Check Inatividade (6 minutos)
        if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
            print(f"🚨 [{nome_log}] INATIVIDADE ({TEMPO_MAX_INATIVIDADE}s). SOLICITANDO REINÍCIO GERAL...")
            STOP_EVENT.set() 
            return 
        
        # 2. Reinício Diário (00:00)
        now_br = datetime.now(TZ_BR)
        if now_br.hour == 0 and now_br.minute <= 5: 
            print(f"⏰ [{nome_log}] REINÍCIO DIÁRIO DETECTADO. SOLICITANDO REINÍCIO GERAL...")
            STOP_EVENT.set()
            return
            
        sleep(POLLING_INTERVAL)

# =============================================================
# 🚀 SUPERVISOR (MAIN LOOP)
# =============================================================
def rodar_ciclo_monitoramento():
    DRIVER = None
    STOP_EVENT.clear() 
    
    try:
        print("\n🔵 INICIANDO NOVO CICLO DO NAVEGADOR...")
        DRIVER = initialize_driver_instance()
        handles = setup_tabs_and_login(DRIVER)
        
        threads = []
        for config in CONFIG_BOTS:
            path = config["firebase_path"]
            handle = handles.get(path)
            if handle:
                t = threading.Thread(target=start_bot_thread, args=(DRIVER, config, handle))
                t.start()
                threads.append(t)
            else:
                print(f"❌ Handle não encontrado para {config['nome']}.")

        print("⏳ Monitoramento iniciado (Threads)...")
        
        while any(t.is_alive() for t in threads):
            if STOP_EVENT.is_set():
                break
            sleep(1)
            
        print("🛑 Ciclo encerrado. Limpando recursos...")
        
    except Exception as e:
        print(f"\n❌ ERRO NO CICLO: {e}")
        traceback.print_exc()
    finally:
        STOP_EVENT.set() 
        for t in threads:
            if t.is_alive(): t.join(timeout=2) 

        if DRIVER:
            try:
                DRIVER.quit()
                print("🗑️ Driver encerrado com sucesso.")
            except: pass
        sleep(5) 

if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD nas variáveis de ambiente.")
        sys.exit()
    
    print("==============================================")
    print("    GOATHBOT V8 - FIX LEITURA FINAL")
    print("==============================================")

    while True:
        try:
            rodar_ciclo_monitoramento()
            print("♻️ Reiniciando processo em 5 segundos...\n")
            sleep(5)
        except KeyboardInterrupt:
            print("\n🚫 Parada manual pelo usuário.")
            break
        except Exception as e:
            print(f"❌ Erro crítico no Supervisor: {e}")
            sleep(10)
