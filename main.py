from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from time import sleep, time
from datetime import datetime, date
from selenium.common.exceptions import StaleElementReferenceException, WebDriverException, NoSuchElementException
import firebase_admin
from firebase_admin import credentials, db
import os
import pytz
import sys
import subprocess
import threading
import traceback

# =============================================================
# ⚠️ CONTROLE GLOBAL DE THREADS E DRIVER
# =============================================================
DRIVER_LOCK = threading.Lock() 
STOP_EVENT = threading.Event() # Evento para sinalizar reinício geral

# =============================================================
# 🔥 CONFIGURAÇÃO FIREBASE
# =============================================================
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'

try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
    print("✅ Firebase Admin SDK inicializado.")
except Exception as e:
    print(f"\n❌ ERRO CONEXÃO FIREBASE: {e}")
    sys.exit()

# =============================================================
# ⚙️ VARIÁVEIS 
# =============================================================
URL_DO_SITE = "https://www.goathbet.com"

LINK_AVIATOR_ORIGINAL = "https://www.goathbet.com/pt/casino/spribe/aviator"
LINK_AVIATOR_2 = "https://www.goathbet.com/pt/casino/spribe/aviator-2"
FIREBASE_PATH_ORIGINAL = "history"
FIREBASE_PATH_2 = "aviator2"

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

POLLING_INTERVAL = 0.05       
TEMPO_MAX_INATIVIDADE = 360 # 6 minutos
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
            nome_jogo = path.split('/')[0].upper()
            if nome_jogo == "HISTORY": nome_jogo = "AVIATOR 1"
            print(f"🔥 {nome_jogo}: {data['multiplier']}x às {data['time']}")
        except Exception:
            pass 
    threading.Thread(target=_send).start()

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
# 🚀 DRIVER (ADAPTADO PARA DOCKER/SQUARE CLOUD)
# =============================================================
def initialize_driver_instance():
    # Tenta matar processos antigos (manter para compatibilidade local)
    try:
        if os.name == 'nt': # Windows
            subprocess.run("taskkill /f /im chromedriver.exe", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            subprocess.run("taskkill /f /im chrome.exe", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    except: pass

    options = webdriver.ChromeOptions()
    options.page_load_strategy = 'eager'
    options.add_argument("--headless=new") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--start-maximized")
    options.add_argument("--log-level=3")
    options.add_argument("--silent")
    # Adicionando user-agent para evitar bloqueios simples
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")
    
    # ⚠️ MUDANÇA CRUCIAL PARA AMBIENTE DOCKER 
    # Aponta para o binário do Chrome instalado no Dockerfile
    options.binary_location = "/usr/bin/google-chrome-stable" 
    
    try:
        # No Docker, o ChromeDriver está no PATH.
        return webdriver.Chrome(options=options)
    except Exception as e:
        print(f"❌ Erro ao iniciar WebDriver: {e}")
        return None

def setup_tabs(driver):
    print("➡️ Acessando site e configurando abas...")
    
    try:
        driver.get(URL_DO_SITE)
        sleep(5)
        verificar_modais_bloqueio(driver)

        btns = driver.find_elements(By.XPATH, "//button[contains(., 'Entrar')]")
        if btns: 
            btns[0].click()
            sleep(2)
            
        # Login
        driver.find_element(By.NAME, "email").send_keys(EMAIL)
        driver.find_element(By.NAME, "password").send_keys(PASSWORD)
        sleep(1)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        print("✅ Login enviado.")
        sleep(8) # Tempo maior para login processar
    except Exception as e:
        print(f"⚠️ Aviso no login: {e}")

    # Aba 1
    driver.get(LINK_AVIATOR_ORIGINAL)
    sleep(5)
    handle_original = driver.current_window_handle
    print(f"✅ Aba Aviator 1 configurada.")

    # Aba 2
    driver.execute_script("window.open('');")
    handles = driver.window_handles
    handle_aviator2 = [h for h in handles if h != handle_original][0]
    
    driver.switch_to.window(handle_aviator2)
    driver.get(LINK_AVIATOR_2)
    sleep(5)
    print(f"✅ Aba Aviator 2 configurada.")
    
    driver.switch_to.window(handle_original) 
    
    return {
        FIREBASE_PATH_ORIGINAL: handle_original,
        FIREBASE_PATH_2: handle_aviator2
    }

# =============================================================
# 🎮 BUSCA DE ELEMENTOS
# =============================================================
def find_game_elements_safe(driver):
    try:
        iframe = driver.find_element(By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]')
        driver.switch_to.frame(iframe)
        hist = driver.find_element(By.CSS_SELECTOR, "app-stats-widget, .payouts-block")
        return iframe, hist
    except:
        return None, None

def initialize_game_elements_initial(driver, game_handle):
    with DRIVER_LOCK:
        try:
            driver.switch_to.window(game_handle)
            driver.switch_to.default_content()
            iframe = WebDriverWait(driver, 20).until( 
                EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'))
            )
            driver.switch_to.frame(iframe)
            hist = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "app-stats-widget, .payouts-block"))
            )
            return iframe, hist
        except:
            return None, None

# =============================================================
# 🔄 LOOP DE CAPTURA
# =============================================================
def start_bot(driver, game_handle: str, firebase_path: str):
    nome_log = "AVIATOR 1" if "history" in firebase_path else "AVIATOR 2"
    print(f"🚀 INICIADO: {nome_log}")

    iframe, hist_element = initialize_game_elements_initial(driver, game_handle)
    
    if not iframe:
        print(f"🚨 Falha ao carregar {nome_log}. Tentando recuperar no loop.")

    LAST_SENT = None
    ULTIMO_MULTIPLIER_TIME = time()

    while not STOP_EVENT.is_set(): # Verifica se o evento de parada foi acionado
        raw_text = None
        
        # === SEÇÃO CRÍTICA ===
        with DRIVER_LOCK:
            if STOP_EVENT.is_set(): break # Verificação dupla

            try:
                driver.switch_to.window(game_handle)
                
                if not iframe or not hist_element:
                    iframe, hist_element = find_game_elements_safe(driver)
                    if not iframe: raise Exception("Frame perdido")

                try:
                    driver.switch_to.frame(iframe) 
                except:
                    iframe, hist_element = find_game_elements_safe(driver)
                    if iframe: driver.switch_to.frame(iframe)

                first_payout = hist_element.find_element(By.CSS_SELECTOR, ".payout:first-child, .bubble-multiplier:first-child")
                raw_text = first_payout.get_attribute("innerText")
                
            except (StaleElementReferenceException, NoSuchElementException):
                iframe = None 
                hist_element = None
                continue 
            except Exception:
                iframe = None
                continue
        # === FIM DA SEÇÃO CRÍTICA ===
        
        # PROCESSAMENTO
        if raw_text:
            clean_text = raw_text.strip().lower().replace('x', '')
            
            if clean_text:
                try:
                    novo_valor = float(clean_text)
                except: continue 

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

        # REINÍCIO POR INATIVIDADE (6 MINUTOS)
        if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
            print(f"🚨 {nome_log}: SEM DADOS HÁ 6 MIN. SOLICITANDO REINÍCIO DO DRIVER...")
            STOP_EVENT.set() # Avisa a thread principal e a outra thread para parar
            return 
        
        # REINÍCIO AS 23:59 (REINÍCIO DIÁRIO)
        now = datetime.now(TZ_BR)
        if now.hour == 23 and now.minute == 59:
            print(f"⏰ 23:59 Detectado em {nome_log}. SOLICITANDO REINÍCIO DIÁRIO...")
            STOP_EVENT.set()
            return
            
        sleep(POLLING_INTERVAL)

# =============================================================
# 🚀 SUPERVISOR (MAIN LOOP)
# =============================================================
def rodar_ciclo_monitoramento():
    """Função que configura e roda um ciclo do bot até que precise reiniciar"""
    DRIVER = None
    STOP_EVENT.clear() # Limpa o evento de parada para começar novo ciclo
    
    try:
        print("\n🔵 INICIANDO NOVO CICLO DO NAVEGADOR...")
        DRIVER = initialize_driver_instance()
        
        if DRIVER is None:
            print("❌ Falha ao inicializar o DRIVER. Tentando novamente no próximo ciclo.")
            return

        handles = setup_tabs(DRIVER)
        
        handle_original = handles[FIREBASE_PATH_ORIGINAL]
        handle_aviator2 = handles[FIREBASE_PATH_2]

        print("⏳ Monitoramento iniciado (Threads)...")
        
        t1 = threading.Thread(target=start_bot, args=(DRIVER, handle_original, FIREBASE_PATH_ORIGINAL))
        t2 = threading.Thread(target=start_bot, args=(DRIVER, handle_aviator2, FIREBASE_PATH_2))

        t1.start()
        t2.start()

        # O Supervisor fica vigiando o STOP_EVENT
        while t1.is_alive() or t2.is_alive():
            if STOP_EVENT.is_set():
                # Se alguém pediu parada, aguarda um pouco e sai do loop
                break
            sleep(1)
            
        print("🛑 Ciclo encerrado. Limpando recursos...")
        
    except Exception as e:
        print(f"\n❌ ERRO NO CICLO: {e}")
        traceback.print_exc()
    finally:
        # Garante que tudo fecha
        STOP_EVENT.set() 
        if DRIVER:
            try:
                DRIVER.quit()
                print("🗑️ Driver encerrado com sucesso.")
            except: pass
        sleep(5) # Pausa respiratória antes de reabrir

if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD nas variáveis de ambiente.")
        # Não usamos sys.exit() aqui para que o container não feche
        # Apenas para que o loop continue e tente de novo
        sleep(10)
    
    print("==============================================")
    print("      SUPERVISOR DE BOT INICIADO (24H)       ")
    print("==============================================")

    # O loop infinito que mantém o bot rodando 24h e reiniciando
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
