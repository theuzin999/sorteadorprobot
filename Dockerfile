# Usa uma imagem base Python slim
FROM python:3.10-slim

# Variáveis para a versão do Chrome e ChromeDriver
# (Importante para evitar incompatibilidade do Selenium)
ENV CHROME_VERSION 120.0.6099.109-1
ENV CHROMEDRIVER_VERSION 120.0.6099.109

# 1. Instalação de dependências do sistema e utilitários
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    libglib2.0-0 \
    libnss3 \
    libgconf-2-4 \
    libfontconfig1 \
    libxrender1 \
    libxext6 \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 2. Adiciona o Google Chrome Stable
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list

# 3. Atualiza e instala a versão específica do Chrome
RUN apt-get update && apt-get install -y google-chrome-stable=$CHROME_VERSION

# 4. Baixa e instala o ChromeDriver
RUN wget -O /tmp/chromedriver.zip "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/120.0.6099.109/linux64/chromedriver-linux64.zip" \
    && unzip /tmp/chromedriver.zip -d /usr/bin \
    && rm /tmp/chromedriver.zip \
    && chmod +x /usr/bin/chromedriver

# Configura o diretório de trabalho no container
WORKDIR /app

# Copia os arquivos de dependência e instala
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante dos arquivos do seu projeto
COPY . .

# Comando de execução: usa o script start.sh
CMD ["/bin/bash", "start.sh"]