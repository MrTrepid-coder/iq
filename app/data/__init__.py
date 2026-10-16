"""Camada de dados.

Duas fontes suportadas:
1. CSV (dados históricos fornecidos pelo usuário/exportados).
2. Coletor por leitura de tela (screen capture) da janela do IQ Option aberta
   no próprio computador do usuário — sem tocar em APIs internas, autenticação
   ou qualquer mecanismo não autorizado.

NÃO usamos APIs não oficiais da IQ Option. A leitura de tela apenas digitaliza
os candles já exibidos ao usuário na sua própria tela.
"""
from __future__ import annotations
