# RELATÓRIO DE INTEGRAÇÃO COM A IQ OPTION — IQ Analyzer

- **Data:** 2026-10-16
- **Modo:** análise/simulação — **execução real bloqueada**
- **Objetivo deste documento:** separar, com honestidade, o que é integração
  **comprovada**, o que é **fonte importada**, o que é **simulado** e o que **não existe**.

---

## 1. Classificação das fontes (exigida pelo briefing)

| Categoria | Descrição | Situação no projeto |
|---|---|---|
| **A** | Integração **oficial** documentada e validada | **NÃO EXISTE** |
| **B** | Biblioteca de terceiros sem autorização compatibilidade comprovada | **PROIBIDA** — não implementada |
| **C** | Fonte **histórica / importada** | **SUPORTADA** (CSV, Binance público, leitura de tela) |
| **D** | Adaptador **simulado** (só testes) | **SUPORTADA** (série sintética) |

O sistema **não afirma** que existe uma API oficial de execução de ordens da IQ
Option — porque isso **não foi comprovado**. Sem interface autorizada e verificável,
adota-se uma arquitetura de adaptadores desacoplada, com o adaptador real
**indisponível por padrão**.

---

## 2. Bibliotecas e versões examinadas

| Biblioteca | Versão | Uso | É integração IQ Option? |
|---|---|---|---|
| numpy | 2.5.4 | cálculo | Não |
| pandas | 3.0.6 | manipulação de dados | Não |
| scikit-learn | 1.9.1 | modelo probabilístico | Não |
| scipy | 1.18.1 | estatística | Não |
| Flask | 3.1.3 | dashboard | Não |
| pillow | 12.3.0 | leitura de tela | Não |
| pytest | 9.1.1 | testes | Não |

**Nenhuma biblioteca de integração com a IQ Option está instalada.** Bibliotecas de
terceiros que interceptam o canal interno (websocket) **não** foram instaladas nem
utilizadas — o briefing as proíbe e a compatibilidade/autorização não é comprovável.

---

## 3. Documentação consultada

- Conhecimento público sobre a **ausência de API oficial** de mercado/execução da
  IQ Option para o público geral.
- Documentação pública da **Binance** (endpoint de *klines*), usada para validar o
  motor com dados reais — **não** é integração IQ Option.
- Nenhum endpoint, método, parâmetro ou payload da IQ Option foi inventado.

---

## 4. Evidências da integração

Não há evidência de integração com a IQ Option porque **não foi implementada**.
O que existe e foi comprovado:

1. **CSV histórico** — `CandleSeries.from_csv` (testado).
2. **Coletor por leitura de tela** — `app/data/capture.py`, validação ponta a ponta
   com gráfico sintético de 40 velas (40/40 recuperadas) e demo de 60 velas.
3. **Binance público** — 5.000 candles reais de BTCUSDT 1m usados na validação.
4. **Adaptador real** — `app/data/connectors.py::RealBrokerAdapter`:
   `is_available() == False` (sempre) e `submit_real_operation()` levanta
   `RealExecutionBlocked`. **Não simula sucesso.**

---

## 5. Recursos comprovados × não comprovados

| Recurso | Estado |
|---|---|
| Ler candles de CSV próprio | **Comprovado** (testes) |
| Coletar candles por leitura de tela | **Comprovado** (testes + demo) |
| Obter candles reais de fonte pública (Binance) | **Comprovado** |
| Simular operações (60 s) e medir resultado | **Comprovado** |
| Conectar-se à IQ Option (mercado) | **Não comprovado / não implementado** |
| Enviar ordens reais | **Não implementado — bloqueado** |

---

## 6. Restrições e riscos

- A leitura de tela é **aproximada** e sensível a tema/zoom/anti-aliasing.
- Ativos OTC da IQ Option podem diferir do ativo público usado na validação.
- Não há OCR do eixo de preço (a calibração é manual, por dois pontos).
- A existência de uma conexão **não** implica autorização para negociar.

---

## 7. Estado da integração

**DESCO(NECTADA) / INDISPONÍVEL por via autorizada.** O restante do sistema permanece
útil por meio de dados históricos/importados e testes determinísticos.

## 8. Motivos pelos quais a execução real permanece bloqueada

1. Não existe API oficial de execução comprovada para o público.
2. Biblioteca de terceiros não tem autorização/compatibilidade comprovadas.
3. O briefing proíbe presumir autorização de bibliotecas não oficiais.
4. Princípio de **falha segura**: sem fonte válida, o sistema informa e **não**
   simula que a operação ocorreu.

### Pré-requisitos para uma futura avaliação (NÃO implementados aqui)

- Documentação oficial de execução de ordens (endpoint/protocolo/autenticação).
- Consentimento explícito e informado do usuário.
- Isolamento de credenciais (fora do código, com redação em logs).
- Revisão dos Termos de Uso aplicáveis.
- Ambiente dedicado e limites de risco validados.

Enquanto isso, `app/config.py::ensure_real_execution_blocked()` **sempre recusa**,
independentemente de variáveis de ambiente.
