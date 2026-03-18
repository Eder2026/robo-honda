#!/usr/bin/env python3
"""
Servidor FastAPI para Agente de Vendas - Consórcio Honda
Versão: 1.0 (Março 2026)

Este servidor recebe webhooks da Evolution API e processa mensagens
de clientes via WhatsApp, respondendo com o agente de IA.

Uso:
    python3 servidor_producao.py

Ou com Uvicorn:
    uvicorn servidor_producao:app --host 0.0.0.0 --port 8000 --reload
"""

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, List
import logging
import os
from datetime import datetime
import json

# Importar módulos do projeto
from agente_consorcio_honda import gerar_resposta_agente
from integracao_evolution_api import (
    enviar_mensagem_whatsapp,
    enviar_mensagem_com_botoes,
    processar_mensagem_recebida,
    processar_resposta_botao
)

# ============================================================================
# CONFIGURAÇÃO DE LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('consorcio_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# INICIALIZAR FASTAPI
# ============================================================================

app = FastAPI(
    title="Agente de Vendas - Consórcio Honda",
    description="API para atendimento de clientes via WhatsApp",
    version="1.0.0"
)

# ============================================================================
# MODELOS PYDANTIC
# ============================================================================

class MensagemWebhook(BaseModel):
    """Modelo para mensagens recebidas via webhook"""
    event: str
    senderNumber: Optional[str] = None
    text: Optional[str] = None
    type: Optional[str] = "text"
    timestamp: Optional[int] = None
    buttonId: Optional[str] = None


class RespostaAPI(BaseModel):
    """Modelo para resposta padrão da API"""
    status: str
    message: str
    data: Optional[Dict] = None


# ============================================================================
# ARMAZENAMENTO EM MEMÓRIA (Para produção, usar banco de dados)
# ============================================================================

# Histórico de conversas por cliente
historico_clientes: Dict[str, List[Dict]] = {}

# Leads qualificados
leads_qualificados: List[Dict] = []


# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

def extrair_numero_whatsapp(numero_raw: str) -> str:
    """
    Extrai número de WhatsApp do formato da Evolution API.
    
    Args:
        numero_raw: Número no formato "5511999999999@c.us"
        
    Returns:
        Número limpo: "5511999999999"
    """
    return numero_raw.replace("@c.us", "").replace("@s.whatsapp.net", "")


def registrar_lead(numero: str, nome: Optional[str] = None, orcamento: Optional[float] = None):
    """
    Registra um lead qualificado para acompanhamento.
    
    Args:
        numero: Número do cliente
        nome: Nome do cliente (opcional)
        orcamento: Orçamento mensal (opcional)
    """
    lead = {
        "numero": numero,
        "nome": nome or "Não informado",
        "orcamento": orcamento,
        "data": datetime.now().isoformat(),
        "status": "novo"
    }
    leads_qualificados.append(lead)
    logger.info(f"Lead registrado: {numero}")


def obter_historico_cliente(numero: str) -> List[Dict]:
    """
    Obtém o histórico de conversas de um cliente.
    
    Args:
        numero: Número do cliente
        
    Returns:
        Lista com histórico de mensagens
    """
    if numero not in historico_clientes:
        historico_clientes[numero] = []
    return historico_clientes[numero]


def adicionar_ao_historico(numero: str, role: str, conteudo: str):
    """
    Adiciona uma mensagem ao histórico do cliente.
    
    Args:
        numero: Número do cliente
        role: "user" ou "assistant"
        conteudo: Texto da mensagem
    """
    if numero not in historico_clientes:
        historico_clientes[numero] = []
    
    historico_clientes[numero].append({
        "role": role,
        "content": conteudo,
        "timestamp": datetime.now().isoformat()
    })


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/", tags=["Status"])
async def root():
    """Endpoint raiz para verificar se o servidor está rodando."""
    return {
        "status": "online",
        "servico": "Agente de Vendas - Consórcio Honda",
        "versao": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health", tags=["Status"])
async def health_check():
    """Verificar saúde do servidor."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "clientes_ativos": len(historico_clientes),
        "leads_qualificados": len(leads_qualificados)
    }


@app.post("/webhook/messages", tags=["Webhooks"])
async def webhook_messages(request: Request, background_tasks: BackgroundTasks):
    """
    Recebe mensagens do WhatsApp via Evolution API.
    
    Fluxo:
    1. Recebe mensagem do cliente
    2. Processa com agente de IA
    3. Envia resposta via WhatsApp
    4. Registra no histórico
    """
    try:
        dados = await request.json()
        logger.info(f"Webhook recebido: {dados.get('event')}")
        
        # Extrair informações
        numero_raw = dados.get("senderNumber", "")
        numero = extrair_numero_whatsapp(numero_raw)
        texto = dados.get("text", "").strip()
        tipo_evento = dados.get("event", "")
        
        # Validar dados
        if not numero or not texto:
            logger.warning("Dados incompletos no webhook")
            return RespostaAPI(
                status="error",
                message="Dados incompletos"
            )
        
        logger.info(f"Mensagem de {numero}: {texto[:50]}...")
        
        # Adicionar ao histórico
        adicionar_ao_historico(numero, "user", texto)
        
        # Gerar resposta
        historico = obter_historico_cliente(numero)
        resposta = gerar_resposta_agente(texto, historico)
        
        # Adicionar resposta ao histórico
        adicionar_ao_historico(numero, "assistant", resposta)
        
        # Enviar resposta em background
        background_tasks.add_task(
            enviar_mensagem_whatsapp,
            numero,
            resposta
        )
        
        # Verificar se deve oferecer agendamento
        if len(historico) > 8:  # Após algumas mensagens
            background_tasks.add_task(
                oferecer_agendamento_background,
                numero
            )
        
        return RespostaAPI(
            status="success",
            message="Mensagem processada",
            data={"numero": numero, "resposta_enviada": True}
        )
        
    except Exception as e:
        logger.error(f"Erro ao processar webhook: {e}", exc_info=True)
        return RespostaAPI(
            status="error",
            message=f"Erro ao processar: {str(e)}"
        )


@app.post("/webhook/buttons", tags=["Webhooks"])
async def webhook_buttons(request: Request, background_tasks: BackgroundTasks):
    """
    Recebe respostas de botões interativos.
    """
    try:
        dados = await request.json()
        numero = extrair_numero_whatsapp(dados.get("senderNumber", ""))
        id_botao = dados.get("buttonId", "")
        
        logger.info(f"Botão clicado por {numero}: {id_botao}")
        
        # Processar resposta do botão
        background_tasks.add_task(
            processar_resposta_botao_background,
            numero,
            id_botao
        )
        
        return RespostaAPI(
            status="success",
            message="Resposta de botão processada"
        )
        
    except Exception as e:
        logger.error(f"Erro ao processar botão: {e}")
        return RespostaAPI(status="error", message=str(e))


@app.post("/enviar-mensagem", tags=["Mensagens"])
async def enviar_mensagem_manual(numero: str, mensagem: str):
    """
    Envia uma mensagem manualmente para um cliente.
    
    Uso: POST /enviar-mensagem?numero=5511999999999&mensagem=Olá
    """
    try:
        if not numero or not mensagem:
            raise HTTPException(status_code=400, detail="Número e mensagem são obrigatórios")
        
        sucesso = enviar_mensagem_whatsapp(numero, mensagem)
        
        if sucesso:
            return RespostaAPI(
                status="success",
                message="Mensagem enviada"
            )
        else:
            return RespostaAPI(
                status="error",
                message="Falha ao enviar mensagem"
            )
            
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem: {e}")
        return RespostaAPI(status="error", message=str(e))


@app.get("/leads", tags=["Leads"])
async def listar_leads():
    """
    Lista todos os leads qualificados.
    """
    return {
        "total": len(leads_qualificados),
        "leads": leads_qualificados
    }


@app.get("/cliente/{numero}/historico", tags=["Clientes"])
async def obter_historico(numero: str):
    """
    Obtém o histórico de conversa de um cliente.
    
    Uso: GET /cliente/5511999999999/historico
    """
    historico = obter_historico_cliente(numero)
    return {
        "numero": numero,
        "total_mensagens": len(historico),
        "historico": historico
    }


@app.delete("/cliente/{numero}/limpar", tags=["Clientes"])
async def limpar_historico(numero: str):
    """
    Limpa o histórico de um cliente.
    """
    if numero in historico_clientes:
        del historico_clientes[numero]
        return RespostaAPI(
            status="success",
            message=f"Histórico de {numero} limpo"
        )
    return RespostaAPI(
        status="error",
        message="Cliente não encontrado"
    )


@app.get("/stats", tags=["Estatísticas"])
async def obter_estatisticas():
    """
    Retorna estatísticas do bot.
    """
    total_mensagens = sum(len(h) for h in historico_clientes.values())
    
    return {
        "clientes_ativos": len(historico_clientes),
        "total_mensagens": total_mensagens,
        "leads_qualificados": len(leads_qualificados),
        "timestamp": datetime.now().isoformat()
    }


# ============================================================================
# FUNÇÕES BACKGROUND
# ============================================================================

async def oferecer_agendamento_background(numero: str):
    """Oferece agendamento em background."""
    mensagem = "Gostaria de agendar uma conversa com um especialista para tirar dúvidas e simular seu consórcio? 📅"
    botoes = [
        {"id": "agendar_sim", "titulo": "Sim, agendar agora"},
        {"id": "agendar_nao", "titulo": "Não, obrigado"}
    ]
    enviar_mensagem_com_botoes(numero, mensagem, botoes)


async def processar_resposta_botao_background(numero: str, id_botao: str):
    """Processa resposta de botão em background."""
    if id_botao == "agendar_sim":
        mensagem = "Perfeito! 🎉 Para agendar sua consulta, por favor compartilhe seu nome e melhor horário para contato. Nosso especialista entrará em contato em breve!"
        registrar_lead(numero)
    elif id_botao == "agendar_nao":
        mensagem = "Tudo bem! Qualquer dúvida que tiver, é só me chamar. Estou sempre por aqui para ajudar! 😊"
    else:
        return
    
    enviar_mensagem_whatsapp(numero, mensagem)


# ============================================================================
# TRATAMENTO DE ERROS
# ============================================================================

@app.exception_handler(Exception)
async def exception_handler(request: Request, exc: Exception):
    """Handler para exceções não tratadas."""
    logger.error(f"Erro não tratado: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Erro interno do servidor"
        }
    )


# ============================================================================
# INICIALIZAÇÃO
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    porta = int(os.getenv("PORTA", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"Iniciando servidor em {host}:{porta}")
    
    uvicorn.run(
        app,
        host=host,
        port=porta,
        log_level="info"
    )
