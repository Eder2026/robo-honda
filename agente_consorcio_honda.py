#!/usr/bin/env python3
"""
Agente de Atendimento de Vendas - Consórcio Honda
Versão: 1.0 (Março 2026)

Este agente atende clientes via WhatsApp, fornecendo informações sobre
Consórcio Honda, simulando parcelas, qualificando leads e agendando contatos.

Integração: Evolution API ou Z-API (WhatsApp)
"""

import json
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from openai import OpenAI

# ============================================================================
# CONFIGURAÇÃO INICIAL
# ============================================================================

# Inicializar cliente OpenAI (usa OPENAI_API_KEY do ambiente)
client = OpenAI()

# Base de conhecimento integrada
CONHECIMENTO_CONSORCIO = {
    "planos": {
        "VoudeHonda": {
            "descricao": "Motos de até 300cc com parcelas baixas",
            "prazos": [12, 18, 24, 36, 48, 60, 80],
            "contemplacoes": {
                "12": {"total": 26, "sorteio": 2, "lance_fixo": 1, "lance_livre": 23},
                "18": {"total": 26, "sorteio": 2, "lance_fixo": 1, "lance_livre": 23},
                "24": {"total": 26, "sorteio": 2, "lance_fixo": 1, "lance_livre": 23},
                "36": {"total": 26, "sorteio": 2, "lance_fixo": 1, "lance_livre": 23},
                "48": {"total": 20, "sorteio": 2, "lance_fixo": 1, "lance_livre": 17},
                "60": {"total": 16, "sorteio": 2, "lance_fixo": 1, "lance_livre": 13},
                "80": {"total": 12, "sorteio": 2, "lance_fixo": 1, "lance_livre": 9},
            },
            "taxas": {
                "12": 16.50, "18": 17.00, "24": 17.50, "36": 19.50,
                "48": 20.50, "60": 22.00, "80": 25.00
            }
        },
        "Advance": {
            "descricao": "Motos de alta cilindrada (acima de 300cc)",
            "prazos": [72],
            "contemplacoes": {
                "72": {"total": 7, "sorteio": 1, "lance_livre": 6},
            },
            "taxas": {"72": 15.00}
        },
        "EasyHonda": {
            "descricao": "Entrada em moto 0km ou seminovo",
            "prazos": [84],
            "contemplacoes": {
                "84": {"total": 3, "sorteio": 1, "lance_livre": 2},
            },
            "taxas": {"84": 18.00}
        }
    },
    "modelos": {
        "POP 110i ES": {"parcela": 194.03, "cilindrada": 110, "categoria": "Street"},
        "BIZ 125 ES": {"parcela": 247.12, "cilindrada": 125, "categoria": "Street"},
        "Elite 125": {"parcela": 263.78, "cilindrada": 125, "categoria": "Street"},
        "BIZ 125 EX": {"parcela": 305.84, "cilindrada": 125, "categoria": "Street"},
        "CG 160 START": {"parcela": 316.61, "cilindrada": 160, "categoria": "Street"},
        "PCX CBS": {"parcela": 342.22, "cilindrada": 150, "categoria": "Street"},
        "CG 160 FAN": {"parcela": 345.52, "cilindrada": 160, "categoria": "Street"},
        "CG 160 TITAN": {"parcela": 370.70, "cilindrada": 160, "categoria": "Street"},
        "PCX ABS": {"parcela": 375.30, "cilindrada": 150, "categoria": "Street"},
        "NXR 160 BROS CBS": {"parcela": 400.04, "cilindrada": 160, "categoria": "Adventure"},
        "NXR 160 BROS ABS": {"parcela": 417.30, "cilindrada": 160, "categoria": "Adventure"},
        "CRF 300F": {"parcela": 432.61, "cilindrada": 300, "categoria": "Off Road"},
        "XRE 190": {"parcela": 433.22, "cilindrada": 190, "categoria": "Adventure"},
        "CB 300F Twister CBS": {"parcela": 452.61, "cilindrada": 300, "categoria": "Street"},
        "HONDA ADV": {"parcela": 463.36, "cilindrada": 300, "categoria": "Street"},
        "CB 300F Twister ABS": {"parcela": 470.23, "cilindrada": 300, "categoria": "Street"},
        "XR 300L Tornado": {"parcela": 552.88, "cilindrada": 300, "categoria": "Adventure"},
        "SAHARA 300": {"parcela": 567.52, "cilindrada": 300, "categoria": "Adventure"},
        "SAHARA 300 ADV": {"parcela": 586.56, "cilindrada": 300, "categoria": "Adventure"},
        "Hornet 500": {"parcela": 780.03, "cilindrada": 500, "categoria": "Street"},
        "NX 500": {"parcela": 829.43, "cilindrada": 500, "categoria": "Adventure"},
        "Hornet 750": {"parcela": 970.74, "cilindrada": 750, "categoria": "Street"},
        "CB 650R E-Clutch": {"parcela": 1052.60, "cilindrada": 650, "categoria": "Street"},
        "NC 750X MT": {"parcela": 1023.13, "cilindrada": 750, "categoria": "Adventure"},
    },
    "faq": {
        "lances": "Existem 3 tipos: Lance Livre (você escolhe o valor), Lance Fixo (valor predeterminado) e Lance Embutido (usa até 10% da carta). Quanto maior o lance, maior a chance de contemplação!",
        "atraso": "Se atrasar ANTES de ser contemplado, fica impedido de participar da assembleia. DEPOIS de contemplado, a Honda pode retomar o bem. Sempre pague no prazo!",
        "contemplacao": "Ocorre mensalmente por sorteio (Loteria Federal) ou lance. Você pode ser contemplado em qualquer mês do seu plano.",
        "trocar_moto": "Sim! A carta de crédito é em dinheiro. Se a moto for mais cara, você paga a diferença. Se for mais barata, usa o saldo para parcelas ou documentação.",
        "juros": "Não! Consórcio é ISENTO de juros. Só tem Taxa de Administração e Fundo de Reserva, ambos diluídos nas parcelas.",
        "nome_limpo": "Para ADERIR: não precisa. Para RETIRAR a moto: sim, Honda faz análise de crédito e exige CPF regularizado.",
    }
}

# ============================================================================
# FUNÇÕES UTILITÁRIAS
# ============================================================================

def encontrar_modelos_por_orcamento(orcamento_mensal: float) -> List[Dict]:
    """
    Encontra modelos de motos que cabem no orçamento mensal do cliente.
    
    Args:
        orcamento_mensal: Valor máximo mensal que o cliente pode pagar
        
    Returns:
        Lista de modelos com parcelas menores ou iguais ao orçamento
    """
    modelos_disponiveis = []
    for modelo, dados in CONHECIMENTO_CONSORCIO["modelos"].items():
        if dados["parcela"] <= orcamento_mensal:
            modelos_disponiveis.append({
                "modelo": modelo,
                "parcela": dados["parcela"],
                "cilindrada": dados["cilindrada"],
                "categoria": dados["categoria"]
            })
    
    # Ordenar por parcela (menor primeiro)
    modelos_disponiveis.sort(key=lambda x: x["parcela"])
    return modelos_disponiveis


def calcular_valor_total_consorcio(parcela_mensal: float, meses: int, taxa_total: float) -> Dict:
    """
    Calcula o valor total a ser pago no consórcio.
    
    Args:
        parcela_mensal: Valor da parcela mensal
        meses: Quantidade de meses do plano
        taxa_total: Taxa total de administração (%)
        
    Returns:
        Dicionário com valores calculados
    """
    valor_total_pago = parcela_mensal * meses
    valor_taxa = valor_total_pago * (taxa_total / 100)
    valor_bem = valor_total_pago - valor_taxa
    
    return {
        "parcela_mensal": f"R$ {parcela_mensal:.2f}".replace(".", ","),
        "meses": meses,
        "valor_total_pago": f"R$ {valor_total_pago:.2f}".replace(".", ","),
        "valor_taxa": f"R$ {valor_taxa:.2f}".replace(".", ","),
        "valor_bem_estimado": f"R$ {valor_bem:.2f}".replace(".", ","),
    }


def extrair_numero_mensagem(mensagem: str) -> Optional[float]:
    """
    Extrai um número (orçamento) de uma mensagem de texto.
    
    Args:
        mensagem: Texto da mensagem do cliente
        
    Returns:
        Número encontrado ou None
    """
    # Procura por padrões como "500", "R$ 500", "500 reais", etc.
    padrao = r'(?:r\$\s*)?(\d+(?:[.,]\d{2})?)'
    match = re.search(padrao, mensagem.lower())
    
    if match:
        valor_str = match.group(1).replace(",", ".")
        return float(valor_str)
    return None


def criar_prompt_sistema() -> str:
    """
    Cria o prompt do sistema para o agente de IA.
    
    Returns:
        String com as instruções do sistema
    """
    return """Você é um agente de vendas especializado em Consórcio Honda. Seu objetivo é:

1. **Atender com profissionalismo e empatia** - Responda de forma clara, amigável e sempre em português brasileiro.
2. **Fornecer informações precisas** - Use apenas dados oficiais do Consórcio Honda 2026.
3. **Qualificar o cliente** - Entenda as necessidades (orçamento, tipo de moto, prazo).
4. **Sugerir soluções** - Recomende planos e modelos que se adequem ao perfil do cliente.
5. **Esclarecer dúvidas** - Responda perguntas sobre lances, contemplação, taxas, atrasos, etc.
6. **Agendar contato** - Quando apropriado, convide o cliente para uma conversa com um especialista.

**Informações importantes:**
- Consórcio Honda é ISENTO de juros
- Não há taxa de adesão
- Contemplação ocorre mensalmente (sorteio ou lance)
- Parcelas incluem Seguro de Vida em Grupo
- Reajustes ocorrem conforme alterações de preço da Honda

**Fluxo de conversa sugerido:**
1. Cumprimento caloroso
2. Pergunta sobre interesse (qual tipo de moto?)
3. Qualificação (orçamento mensal?)
4. Sugestão de plano e modelos
5. Esclarecimento de dúvidas
6. Agendamento de contato com especialista

**Nunca:**
- Prometa contemplação garantida
- Faça promessas sobre valores de lances
- Dê informações fora da base de conhecimento
- Seja agressivo ou insistente

Seja consultivo, educativo e focado em resolver o problema do cliente."""


def processar_mensagem_com_ia(mensagem_cliente: str, historico: List[Dict]) -> str:
    """
    Processa a mensagem do cliente usando IA (OpenAI) com contexto de Consórcio Honda.
    
    Args:
        mensagem_cliente: Mensagem recebida do cliente
        historico: Histórico de conversas anteriores
        
    Returns:
        Resposta do agente
    """
    # Preparar histórico para a IA
    mensagens = [
        {
            "role": "system",
            "content": criar_prompt_sistema()
        }
    ]
    
    # Adicionar histórico
    for msg in historico[-10:]:  # Últimas 10 mensagens para contexto
        mensagens.append({
            "role": msg["role"],
            "content": msg["content"]
        })
    
    # Adicionar mensagem atual
    mensagens.append({
        "role": "user",
        "content": mensagem_cliente
    })
    
    # Chamar API OpenAI
    try:
        resposta = client.chat.completions.create(
            model="gpt-4.1-mini",  # Modelo disponível no sandbox
            messages=mensagens,
            temperature=0.7,
            max_tokens=500,
        )
        return resposta.choices[0].message.content
    except Exception as e:
        print(f"Erro ao chamar OpenAI: {e}")
        return "Desculpe, tive um problema ao processar sua mensagem. Pode tentar novamente?"


def gerar_resposta_agente(mensagem_cliente: str, historico: List[Dict] = None) -> str:
    """
    Função principal que gera a resposta do agente.
    
    Args:
        mensagem_cliente: Mensagem recebida do cliente
        historico: Histórico de conversas (opcional)
        
    Returns:
        Resposta formatada do agente
    """
    if historico is None:
        historico = []
    
    # Verificar se é uma pergunta sobre orçamento/simulação
    orcamento = extrair_numero_mensagem(mensagem_cliente)
    
    if orcamento and orcamento > 0:
        modelos = encontrar_modelos_por_orcamento(orcamento)
        if modelos:
            resposta = f"🏍️ Ótimo! Com orçamento de R$ {orcamento:.2f}/mês, você tem essas opções:\n\n"
            for i, modelo in enumerate(modelos[:5], 1):
                resposta += f"{i}. {modelo['modelo']} - R$ {modelo['parcela']:.2f}/mês ({modelo['cilindrada']}cc)\n"
            resposta += "\nQual dessas te interessa? Posso simular o consórcio completo! 😊"
            return resposta
    
    # Usar IA para responder
    resposta = processar_mensagem_com_ia(mensagem_cliente, historico)
    return resposta


# ============================================================================
# EXEMPLO DE USO E TESTES
# ============================================================================

def simular_conversa():
    """
    Simula uma conversa com o agente para testes.
    """
    print("=" * 70)
    print("AGENTE DE VENDAS - CONSÓRCIO HONDA 2026")
    print("=" * 70)
    print("\nEste é um agente de atendimento para WhatsApp.")
    print("Teste as seguintes mensagens:\n")
    
    historico = []
    
    # Mensagens de teste
    mensagens_teste = [
        "Olá! Gostaria de saber sobre consórcio de motos",
        "Qual é meu orçamento? Uns R$ 400 por mês",
        "Como funciona a contemplação?",
        "E se eu atrasar uma parcela?",
    ]
    
    for msg in mensagens_teste:
        print(f"\n👤 Cliente: {msg}")
        resposta = gerar_resposta_agente(msg, historico)
        print(f"🤖 Agente: {resposta}")
        
        # Adicionar ao histórico
        historico.append({"role": "user", "content": msg})
        historico.append({"role": "assistant", "content": resposta})


if __name__ == "__main__":
    # Executar simulação
    simular_conversa()
