# Usa uma imagem base oficial do Python
FROM python:3.9-slim

# Instala o utilitário CURL e o GNUPG (necessário para o processo de chave do Chrome)
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Instala o Google Chrome de forma mais moderna (sem apt-key)
# 1. Baixa a chave GPG. 2. Adiciona o repositório. 3. Atualiza. 4. Instala o Chrome.
RUN curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable

# Define o diretório de trabalho
WORKDIR /app

# Copia os arquivos do projeto
COPY . /app

# Instala as dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Expõe a porta que o Flask vai usar
EXPOSE 5000

# Comando para iniciar o script
CMD ["python", "main.py"]
