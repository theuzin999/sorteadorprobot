import time
import threading
import os
import datetime
from flask import Flask
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Variável global para rastrear o status
last_refresh_time = "N/A"

# --- Configuração do Servidor Web (Flask) ---
app = Flask(__name__)

@app.route('/')
def home():
    """Endpoint principal para saber se o servidor está online."""
    return f"Bot is running. Last page refresh attempt: {last_refresh_time}"

@app.route('/status')
def status():
    """
    Endpoint de status HTTP para o monitoramento externo (UptimeRobot).
    Ele retorna um simples 'OK' para confirmar que o serviço está ativo.
    """
    return "OK", 200

def run_flask():
    """Inicia o servidor Flask para manter o Render acordado."""
    # Render usa a variável de ambiente PORT, se não, usa 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

# --- Configuração do Bot (Selenium) ---
def run_browser():
    global last_refresh_time
    print("Iniciando o navegador...")
    
    # Opções Headless para rodar no Render (sem tela gráfica)
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"Erro ao iniciar o WebDriver: {e}")
        return

    # Links
    url1 = "https://botapostamax.netlify.app"
    url2 = "https://botapostaganha.netlify.app"

    try:
        # Abre a primeira guia e a segunda (em uma nova aba)
        print(f"Abrindo {url1} e {url2}...")
        driver.get(url1)
        driver.execute_script(f"window.open('{url2}', '_blank');")

        # Loop principal do Refresh (2 em 2 horas = 7200 segundos)
        while True:
            # Tempo de espera de 2 horas
            print("Aguardando 2 horas...")
            time.sleep(7200)

            print("Recarregando páginas...")
            # Percorre todas as abas e dá refresh
            for handle in driver.window_handles:
                driver.switch_to.window(handle)
                driver.refresh()
                time.sleep(5) # Pequena pausa entre refreshes
            
            # Atualiza o tempo global para que o endpoint '/' reflita a atividade
            last_refresh_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"Páginas recarregadas com sucesso em: {last_refresh_time}")

    except Exception as e:
        print(f"Erro no loop do navegador: {e}")
    finally:
        print("Fechando o driver do navegador.")
        if 'driver' in locals():
            driver.quit()

# --- Execução Principal ---
if __name__ == "__main__":
    # Inicia o Flask em uma thread separada
    t1 = threading.Thread(target=run_flask)
    t1.start()

    # Inicia o Bot (Selenium)
    run_browser()
