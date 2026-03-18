#!/usr/bin/env python3
"""
Integração com Evolution API para WhatsApp
Versão: 1.0 (Março 2026)

Este módulo fornece funções para integrar o agente de vendas com a Evolution API,
permitindo atender clientes via WhatsApp de forma automatizada.

Documentação: https://evolution-api.com/docs
"""

import requests
import json
import os
from typing import Dict, Optional, List
from agente_consorcio_honda import gerar_resposta_agente

# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

# Variáveis de ambiente necessárias
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "sua_chave_api_aqui")
NUMERO_WHATSAPP = os.getenv("NUMERO_WHATSAPP", "5511999999999")  # Seu número com código do país

# Histórico de conversas (em produção, usar banco de dados)
historico_conversas: Dict[str, List[Dict]] = {}


# ============================================================================
# FUNÇÕES DE INTEGRAÇÃO
# ============================================================================

def enviar_mensagem_whatsapp(numero_cliente: str, mensagem: str) -> bool:
    """
    Envia uma mensagem via WhatsApp usando Evolution API.
    
    Args:
        numero_cliente: Número do cliente (formato: 5511999999999)
        mensagem: Texto da mensagem a enviar
        
    Returns:
        True se enviado com sucesso, False caso contrário
    """
    try:
        url = f"{EVOLUTION_API_URL}/message/sendText/{NUMERO_WHATSAPP}"
        
        payload = {
            "number": numero_cliente,
            "text": mensagem
        }
        
        headers = {
            "Content-Type": "application/json",
            "apikey": EVOLUTION_API_KEY
        }
        
        resposta = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if resposta.status_code == 200:
            print(f"✓ Mensagem enviada para {numero_cliente}")
            return True
        else:
            print(f"✗ Erro ao enviar: {resposta.status_code} - {resposta.text}")
            return False
            
    except Exception as e:
        print(f"✗ Erro na requisição: {e}")
        return False


def enviar_mensagem_com_botoes(numero_cliente: str, texto: str, botoes: List[Dict]) -> bool:
    """
    Envia uma mensagem com botões interativos via WhatsApp.
    
    Args:
        numero_cliente: Número do cliente
        texto: Texto da mensagem
        botoes: Lista de dicionários com {id, titulo}
        
    Returns:
        True se enviado com sucesso
    """
    try:
        url = f"{EVOLUTION_API_URL}/message/sendButtons/{NUMERO_WHATSAPP}"
        
        payload = {
            "number": numero_cliente,
            "title": texto,
            "buttons": [
                {
                    "id": btn["id"],
                    "displayText": btn["titulo"]
                }
                for btn in botoes
            ]
        }
        
        headers = {
            "Content-Type": "application/json",
            "apikey": EVOLUTION_API_KEY
        }
        
        resposta = requests.post(url, json=payload, headers=headers, timeout=10)
        return resposta.status_code == 200
        
    except Exception as e:
        print(f"✗ Erro ao enviar botões: {e}")
        return False


def processar_mensagem_recebida(dados_webhook: Dict) -> None:
    """
    Processa uma mensagem recebida via webhook da Evolution API.
    
    Args:
        dados_webhook: Dados recebidos do webhook
    """
    try:
        # Extrair informações da mensagem
        numero_cliente = dados_webhook.get("senderNumber", "").replace("@c.us", "")
        texto_mensagem = dados_webhook.get("text", "")
        tipo_mensagem = dados_webhook.get("type", "text")
        
        if not numero_cliente or not texto_mensagem:
            print("✗ Dados incompletos no webhook")
            return
        
        print(f"\n📱 Mensagem recebida de {numero_cliente}: {texto_mensagem}")
        
        # Inicializar histórico do cliente se não existir
        if numero_cliente not in historico_conversas:
            historico_conversas[numero_cliente] = []
        
        # Adicionar mensagem ao histórico
        historico_conversas[numero_cliente].append({
            "role": "user",
            "content": texto_mensagem
        })
        
        # Gerar resposta usando o agente
        resposta = gerar_resposta_agente(
            texto_mensagem,
            historico_conversas[numero_cliente]
        )
        
        # Adicionar resposta ao histórico
        historico_conversas[numero_cliente].append({
            "role": "assistant",
            "content": resposta
        })
        
        # Enviar resposta
        enviar_mensagem_whatsapp(numero_cliente, resposta)
        
        # Verificar se deve oferecer agendamento
        if len(historico_conversas[numero_cliente]) > 6:  # Após algumas mensagens
            oferecer_agendamento(numero_cliente)
        
    except Exception as e:
        print(f"✗ Erro ao processar mensagem: {e}")


def oferecer_agendamento(numero_cliente: str) -> None:
    """
    Oferece ao cliente a opção de agendar contato com especialista.
    
    Args:
        numero_cliente: Número do cliente
    """
    mensagem = "Gostaria de agendar uma conversa com um especialista para tirar dúvidas e simular seu consórcio? 📅"
    
    botoes = [
        {"id": "agendar_sim", "titulo": "Sim, agendar agora"},
        {"id": "agendar_nao", "titulo": "Não, obrigado"}
    ]
    
    enviar_mensagem_com_botoes(numero_cliente, mensagem, botoes)


def processar_resposta_botao(dados_webhook: Dict) -> None:
    """
    Processa a resposta quando o cliente clica em um botão.
    
    Args:
        dados_webhook: Dados do webhook com a resposta do botão
    """
    numero_cliente = dados_webhook.get("senderNumber", "").replace("@c.us", "")
    id_botao = dados_webhook.get("buttonId", "")
    
    if id_botao == "agendar_sim":
        mensagem = "Perfeito! 🎉 Para agendar sua consulta, por favor compartilhe seu nome e melhor horário para contato. Nosso especialista entrará em contato em breve!"
        enviar_mensagem_whatsapp(numero_cliente, mensagem)
        
    elif id_botao == "agendar_nao":
        mensagem = "Tudo bem! Qualquer dúvida que tiver, é só me chamar. Estou sempre por aqui para ajudar! 😊"
        enviar_mensagem_whatsapp(numero_cliente, mensagem)


# ============================================================================
# WEBHOOK HANDLER (para usar com Flask/FastAPI)
# ============================================================================

def handle_webhook(request_data: Dict) -> Dict:
    """
    Handler para receber webhooks da Evolution API.
    
    Uso com FastAPI:
    ```python
    from fastapi import FastAPI, Request
    
    app = FastAPI()
    
    @app.post("/webhook/messages")
    async def webhook(request: Request):
        dados = await request.json()
        return handle_webhook(dados)
    ```
    
    Args:
        request_data: Dados recebidos do webhook
        
    Returns:
        Resposta para confirmar recebimento
    """
    try:
        tipo_evento = request_data.get("event", "")
        
        if tipo_evento == "messages.upsert":
            # Mensagem de texto recebida
            processar_mensagem_recebida(request_data)
            
        elif tipo_evento == "messages.update":
            # Atualização de mensagem (ex: lida)
            pass
            
        elif tipo_evento == "buttons.response":
            # Resposta a botões
            processar_resposta_botao(request_data)
        
        return {"status": "ok", "message": "Webhook processado"}
        
    except Exception as e:
        print(f"✗ Erro no webhook: {e}")
        return {"status": "error", "message": str(e)}


# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

def testar_conexao() -> bool:
    """
    Testa a conexão com Evolution API.
    
    Returns:
        True se conectado, False caso contrário
    """
    try:
        url = f"{EVOLUTION_API_URL}/status"
        headers = {"apikey": EVOLUTION_API_KEY}
        resposta = requests.get(url, headers=headers, timeout=5)
        
        if resposta.status_code == 200:
            print("✓ Conexão com Evolution API estabelecida!")
            return True
        else:
            print(f"✗ Erro na conexão: {resposta.status_code}")
            return False
            
    except Exception as e:
        print(f"✗ Não foi possível conectar: {e}")
        return False


def enviar_mensagem_teste(numero_cliente: str) -> None:
    """
    Envia uma mensagem de teste para validar a integração.
    
    Args:
        numero_cliente: Número para teste
    """
    mensagem = """Olá! 👋 Sou o assistente de vendas do Consórcio Honda.

Estou aqui para ajudar você a encontrar a moto dos seus sonhos com parcelas que cabem no seu bolso, sem juros!

Como posso te ajudar hoje? 🏍️"""
    
    enviar_mensagem_whatsapp(numero_cliente, mensagem)


if __name__ == "__main__":
    print("=" * 70)
    print("INTEGRAÇÃO EVOLUTION API - CONSÓRCIO HONDA")
    print("=" * 70)
    print("\nEste módulo fornece integração com WhatsApp via Evolution API.")
    print("\nPara usar em produção:")
    print("1. Configure as variáveis de ambiente:")
    print("   - EVOLUTION_API_URL: URL da sua instância Evolution API")
    print("   - EVOLUTION_API_KEY: Sua chave de API")
    print("   - NUMERO_WHATSAPP: Seu número com código do país")
    print("\n2. Implemente o webhook em seu servidor FastAPI/Flask")
    print("3. Configure o webhook na Evolution API para receber mensagens")
    print("\nTestando conexão...")
    
    if testar_conexao():
        print("\n✓ Pronto para usar!")
    else:
        print("\n✗ Configure as variáveis de ambiente corretamente")
