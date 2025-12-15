import time
import threading
import os
from flask import Flask
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# --- Configuração do Servidor Web (Para manter o Render vivo) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running..."

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

# --- Configuração do Bot ---
def run_browser():
    print("Iniciando o navegador...")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Roda sem interface gráfica
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    
    # Configura o User-Agent para parecer um navegador real
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # Links
    url1 = "https://botapostamax.netlify.app"
    url2 = "https://botapostaganha.netlify.app"

    try:
        # Abre a primeira guia
        print(f"Abrindo {url1}")
        driver.get(url1)

        # Abre a segunda guia
        print(f"Abrindo {url2}")
        driver.execute_script(f"window.open('{url2}', '_blank');")

        # Loop Infinito
        while True:
            # Espera 2 horas (7200 segundos)
            print("Aguardando 2 horas...")
            time.sleep(7200)

            print("Recarregando páginas...")
            # Percorre todas as abas e dá refresh
            for handle in driver.window_handles:
                driver.switch_to.window(handle)
                driver.refresh()
                time.sleep(5) # Pequena pausa entre refreshes
            
            print("Páginas recarregadas com sucesso.")

    except Exception as e:
        print(f"Erro: {e}")
    finally:
        driver.quit()

# --- Execução Principal ---
if __name__ == "__main__":
    # Inicia o Flask em uma thread separada
    t1 = threading.Thread(target=run_flask)
    t1.start()

    # Inicia o Bot
    run_browser()
