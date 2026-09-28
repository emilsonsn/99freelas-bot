import json
import logging
from datetime import datetime
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException
from selenium.webdriver.support.ui import WebDriverWait
from time import sleep
import subprocess
import os
import socket
import sys
sys.stdout.reconfigure(line_buffering=True)


def setup_logging():
    logs_dir = Path('logs')
    logs_dir.mkdir(exist_ok=True)

    started_at = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_file = logs_dir / f'bot_{started_at}.log'

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )

    logging.info('Log iniciado em %s', log_file)
    return log_file


def log_uncaught_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logging.critical(
        'Erro não tratado encerrou o bot',
        exc_info=(exc_type, exc_value, exc_traceback),
    )


logger = logging.getLogger(__name__)

class Main:

    def start(self):
        logger.info('Encerrando instâncias antigas do Chrome e limpando locks')
        os.system("pkill chrome || true")
        os.system("rm -f /home/emilsonsn/.chrome-selenium/SingletonLock")
        os.system("rm -f /home/emilsonsn/.chrome-selenium/SingletonCookie")
        os.system("rm -f /home/emilsonsn/.chrome-selenium/SingletonSocket")

        logger.info('Iniciando Chrome em modo headless')
        subprocess.Popen([
            "/usr/bin/google-chrome",
            "--remote-debugging-port=9222",
            "--user-data-dir=/home/emilsonsn/.chrome-selenium",
            "--disable-dev-shm-usage",
            "--headless=new",
            "--disable-gpu",
            "--window-size=1920,1080"
        ])
        self.options = webdriver.ChromeOptions()
        self.options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
        for _ in range(10):
            try:
                with socket.create_connection(("127.0.0.1", 9222), timeout=1):
                    break
            except OSError:
                sleep(1)
        else:
            raise Exception("Chrome não respondeu na porta 9222.")

        options = webdriver.ChromeOptions()
        options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

        self.driver = webdriver.Chrome(options=options)
        try:
            self.driver.maximize_window()
        except Exception:
            logger.exception('Não foi possível maximizar a janela do Chrome')

        logger.info('Bot iniciado e rodando')

        # Palavras que ele irá buscar
        self.keys = (open('keys.txt', encoding='UTF-8').read()).split('\n')
        # Mensagem
        self.mensagem = open('mensagem.txt', encoding='UTF-8').read()
        logger.info('Configurações carregadas: %s palavras-chave', len([key for key in self.keys if key.strip()]))
    
    def login(self):
        logger.info('Abrindo página de login')
        self.driver.get('https://www.99freelas.com.br/login')
        sleep(2)
        try:
            google_button = self.driver.find_element(By.CLASS_NAME, 'btn-social-google')
            google_button.click()
            logger.info('Botão de login com Google clicado')
            sleep(2)
        except Exception:
            logger.warning('Botão de login com Google não encontrado ou não clicável')

    def procurar_projetos(self):
        logger.info('Iniciando busca por projetos')
        self.driver.get('https://www.99freelas.com.br/dashboard')
        for key in self.keys:
            try:
                termo = key.strip().replace(' ', '+')
                if not termo:
                    continue

                logger.info('Buscando projetos para: %s', key.strip())
                url = f'https://www.99freelas.com.br/projects?q={termo}&order=mais-recentes&categoria=web-mobile-e-software'
                self.driver.get(url)
                titles = [[title.text, title.get_attribute('href')] for title in self.driver.find_elements(By.CSS_SELECTOR, 'h1.title a')[0:10]]
                projetos_enviados = [palavra.strip() for palavra in open('enviados.csv', encoding='UTF8').read().split('\n')]
                logger.info('Encontrados %s projetos para: %s', len(titles), key.strip())
                for title in titles:
                    texto_titulo = title[0]
                    if texto_titulo in projetos_enviados:
                        logger.info('Projeto já enviado, ignorando: %s', texto_titulo)
                    else:
                        logger.info('Enviando mensagem para projeto: %s', texto_titulo)
                        self.enviar_mensagem(title[1])
                        self.salvar_projeto(texto_titulo)
                        logger.info('Aguardando 5s para próxima mensagem')
                        sleep(5)
                sleep(10)
            except Exception:
                logger.exception('Erro ao procurar projetos para a palavra-chave: %s', key.strip())
                self.driver.get('https://www.99freelas.com.br/dashboard')
                sleep(2)
                continue

    def enviar_mensagem(self, url):
        try:
            logger.info('Abrindo projeto: %s', url)
            self.driver.get(url)
            WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.info-usuario-nome')))
            sleep(1)
            nome_cliente = self.driver.find_element(By.CSS_SELECTOR, 'div.info-usuario-nome').text.split()[0]
            logger.info('Cliente identificado: %s', nome_cliente)
            pergunta = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'p.txt-duvidas a')))
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", pergunta)
            pergunta.click()
            sleep(1)
            self.driver.execute_script("""
            var o=document.querySelector('div.content.infinite-time');
            if(o){o.style.pointerEvents='none';o.style.display='none';o.style.visibility='hidden';}
            """)
            sended = self.driver.find_elements(By.CSS_SELECTOR, 'div.generic.information')
            if len(sended) > 0:
                logger.info('Projeto já possui mensagem enviada: %s', url)
                return
            campo = WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'textarea#mensagem-pergunta')))
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", campo)
            WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'textarea#mensagem-pergunta'))).click()
            campo.clear()
            texto = self.mensagem.replace(r'{{NAME}}', nome_cliente)
            campo.send_keys(texto)
            sleep(1)
            botao = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button#btnEnviarPergunta')))
            self.driver.execute_script("arguments[0].click();", botao)
            sleep(2)
            logger.info('Mensagem enviada com sucesso: %s', url)
        except Exception:
            logger.exception('Erro ao enviar mensagem para o projeto: %s', url)
    
    def salvar_projeto(self, projeto):
        projeto = projeto.strip()
        if not projeto:
            return

        try:
            with open('enviados.csv', 'r', encoding='utf-8') as f:
                projetos = [linha.strip() for linha in f if linha.strip()]
        except FileNotFoundError:
            projetos = []

        projetos.append(projeto)
        projetos = projetos[-150:]

        with open('enviados.csv', 'w', encoding='utf-8') as f:
            f.write('\n'.join(projetos) + '\n')
        logger.info('Projeto salvo em enviados.csv: %s', projeto)

    def main(self):
        try:
            self.start()
            self.login()
            while True:
                self.procurar_projetos()
                logger.info('Cooldown de 10 minutos...')
                sleep(10 * 60) # 10 minutos
        except Exception:
            logger.exception('Erro fatal no loop principal')
            raise SystemExit(1)

if __name__ == '__main__':
    setup_logging()
    sys.excepthook = log_uncaught_exception
    main = Main()
    main.main()
