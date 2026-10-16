# ENTREGA — Sistema Inteligente de Análise Técnica e Probabilística (IQ Analyzer)

Documento de entrega seguindo a lista obrigatória do briefing.
**Modo simulação/análise — execução real desativada por padrão.**

---

## 1. Resumo do estado inicial do projeto (FASE 1 — auditoria)

A pasta `opçoes/` continha **apenas** o atalho `IQ Option.lnk`. **Não havia
código, banco de dados, dependências nem integração** com a IQ Option.

| Item | Situação encontrada |
|---|---|
| Código existente | Nenhum |
| Linguagem/framework | — (definido: Python 3.12) |
| Banco de dados | Nenhum (adotado: CSV/JSONL) |
| Integração IQ Option | Inexistente |
| API oficial IQ Option | **Não existe** para o público |
| Ambiente | Python 3.12.10 instalado (winget); numpy, pandas, scikit-learn, flask, pillow, pytest |

**Decisão de arquitetura sobre os dados.** A IQ Option não publica API oficial.
Bibliotecas não oficiais interceptam o websocket interno — violam os termos e o
próprio briefing. Por isso a coleta foi implementada em **duas vias permitidas**:
1. **CSV** (dados históricos do usuário);
2. **Coletor por leitura de tela** (`app/data/capture.py`) — lê apenas o que já
   está visível na tela do usuário, sem rede, login ou API interna.

Para **validar o motor com dados de mercado reais**, foi usada a **API pública da
Binance** (klines, gratuita e documentada) — 5.000 candles reais de BTCUSDT 1m.

---

## 2. Arquivos criados

```
iq-analyzer/
  run.py                         CLI (sample, fetch, analyze, backtest, walkforward, serve)
  requirements.txt
  README.md
  ENTREGA.md                     (este documento)
  app/
    core/candles.py              Candle/CandleSeries, validação OHLC, window() anti-lookahead, resample
    core/indicators.py           EMA, RSI, MACD, Bollinger, ATR, ADX, VWAP, volatilidade, slope
    core/patterns.py             padrões de velas por regras objetivas
    core/structure.py            tendência, swing points, S/R, consolidação, rompimentos, regime
    analysis/context.py          AnalysisContext + IndicatorCache (desempenho sem lookahead)
    strategies/__init__.py       Estratégias A–E
    signal/__init__.py           filtro de qualidade (10 critérios) + SignalReport
    probability/__init__.py      regressão logística + calibração + Brier + IC de Wilson
    backtest/__init__.py         backtest sem lookahead + walk-forward + métricas
    data/capture.py              coletor por leitura de tela
    data/__init__.py
    ui/server.py + ui/templates/index.html   dashboard web
    journal.py                   registro estruturado (aprendizado contínuo)
  scripts/
    fetch_binance.py             dados reais públicos (validação)
    make_report.py               gera data/REPORT.md
    dump_signals.py              exporta todos os sinais (inclusive perdedores)
    calibrate_capture.py         assistente de calibração do coletor por tela
    make_sample_screenshot.py    gera print sintético de teste do coletor
  tests/                         50 testes (unitários, integração, segurança)
  data/sample.csv                dados sintéticos de exemplo
  data/BTCUSDT_1m.csv            5.000 candles reais (validação)
  data/REPORT.md                 relatório medido
```

**Arquivos modificados:** nenhum (projeto criado do zero).

---

## 3. Estratégias implementadas e suas regras

| ID | Nome | Regras de entrada | Invalidação |
|----|------|-------------------|-------------|
| A | Continuação de tendência | Estrutura HH/HL (ou LH/LL) + EMAs 9/21/50 alinhadas + ADX ≥ 20 + candle a favor + sem padrão de reversão + sem consolidação | Fechamento contra a tendência por 1·ATR ou perda da EMA21 |
| B | Reversão em S/R | Preço a ≤ 0,35·ATR de um nível + padrão de rejeição + perda de força do movimento (ADX caindo / RSI extremo / MACD enfraquecendo) | Fechamento além do nível por 0,5·ATR |
| C | Rompimento e reteste | Fechamento além do nível por ≥ 0,25·ATR + compressão de Bollinger antes + reteste com defesa ou candle de continuação | Retorno de fechamento para dentro da zona |
| D | Reversão estatística | RSI extremo **E** %B extremo **E** exaustão de momentum; **bloqueada** contra tendência forte (ADX ≥ 30 + EMAs alinhadas) e contra o 5m | Candle forte (> 1·ATR) a favor da tendência anterior |
| E | Confluência | ≥ 3 fontes independentes (tendência, padrão, momentum, níveis, 5m) na mesma direção, sem fonte relevante contra | Inversão de qualquer fonte |

O **RSI extremo sozinho nunca é sinal** (só combinado na Estratégia D).

---

## 4. Relatórios de backtesting e testes fora da amostra

**Fonte:** 5.000 candles reais BTCUSDT 1m (API pública Binance).
**Payout:** 80% ⇒ ponto de equilíbrio **55,56%**.
**Expiração:** 1 candle/vela.

### 4.1 Backtest completo (in-sample)

```
Operações: 1574        Vitórias/Derrotas: 770/804
Taxa de acerto: 48.92%   IC95% (Wilson): [46.46%, 51.39%]
Resultado líquido: -188.00 stakes   Esperança/op: -0.1194 stakes
Drawdown máximo: 193.20 stakes   Máx. sequência de perdas: 11

[A] n=501 acerto=49.3%  [B] n=39 acerto=33.3%  [C] n=479 acerto=48.2%
[D] n=2   acerto=0.0%   [E] n=553 acerto=50.5%
```

### 4.2 Walk-forward (FORA da amostra — treino → validação → teste)

| Fold | Treino | Validação | Teste | n teste | Acerto teste |
|---|---|---|---|---|---|
| 0 | (0,1250) | (1250,2500) | (2500,3750) | 438 | 48.6% |
| 1 | (1250,2500) | (2500,3750) | (3750,5000) | 410 | 51.0% |

```
Agregado fora da amostra: n=848  acerto=49.76%  IC95%=[46.41%, 53.12%]
Resultado líquido: -88.40 stakes   Esperança/op: -0.1042 stakes
Drawdown máximo: 94.00 stakes   Máx. sequência de perdas: 11

[A] n=269 acerto=50.2%  [B] n=17 acerto=41.2%  [C] n=250 acerto=49.2%
[D] n=2   acerto=0.0%   [E] n=310 acerto=50.6%
```

### 4.3 Modelo probabilístico

```
Calibração: nenhum
Brier validação: 0.2485 (baseline 0.2500)
Brier teste:     0.2514 (baseline 0.2498)
→ sem ganho sobre a baseline ⇒ MODELO REJEITADO (não exibe probabilidade)
```

Relatório completo em `data/REPORT.md`.

---

## 5. Taxa de acerto comprovada

| Conjunto | n | Taxa | IC95% (Wilson) |
|---|---|---|---|
| In-sample | 1574 | **48,92%** | [46,46%, 51,39%] |
| Fora da amostra (walk-forward) | 848 | **49,76%** | [46,41%, 53,12%] |

**Conclusão honesta:** a taxa de acerto fica **abaixo do ponto de equilíbrio
(55,56%)** e o intervalo de confiança **inclui 50%**. **Não há vantagem
estatística demonstrada** neste ativo (BTCUSDT), expiração (1 candle) e período.
O sistema **não atinge** a meta de pesquisa de >80% e **não inventa** resultado
para atingi-la.

---

## 5.1 Coletor por leitura de tela — verificação

O coletor foi tornado **funcional** e validado:

- Segmentação por **componentes conexos**: corpo + pavios = **uma** vela (um
  pavio **não** gera vela extra; uma vela larga **não** vira várias).
- **Separação corpo/pavio** por largura de linha → open/close = corpo; high/low =
  extremos.
- **Timestamps reais** em minutos (última vela = minuto atual, truncado).
- **Região automática** pela posição das velas (`chart_region_from_image`).
- **Calibração** por dois pontos, salvável/carregável em JSON
  (`scripts/calibrate_capture.py` + `--calib/--calib-out`).
- **Comando** `run.py capture` (lê um PNG com `--shot` ou a tela ao vivo) e
  **export CSV** que alimenta o resto do sistema.

Verificação (13 testes em `tests/test_capture.py`), incluindo **ponta a ponta**:
um gráfico sintético de 40 velas (corpo + pavio, cores da IQ Option) é desenhado
e **todas as 40 velas são recuperadas** com OHLC dentro de ~2,5 px de tolerância
e direção correta. Demo real executada: `--shot` de 60 velas → **60 velas** no
CSV → `run.py analyze` consumiu a captura sem erros.

**Limitação remanescente:** duas velas da **mesma cor sem nenhum espaço** entre
si podem ser lidas como uma (mitigável com mais zoom / `--no-split`); sem OCR do
eixo de preço.

---

## 6. Limitações e riscos encontrados

1. **Sem API oficial da IQ Option.** Dados \"reais da plataforma\" exigem CSV ou
   captura de tela (esta última é aproximada e sensível a tema/zoom).
2. **Ativo de validação ≠ ativo negociado.** A validação usou BTCUSDT (fonte
   pública). Ativos OTC da IQ Option podem ter comportamento diferente.
3. **Universalidade não comprovada.** Nenhuma estratégia venceu o break-even em
   BTC 1m; nada garante desempenho melhor em outros ativos/períodos.
4. **Custos.** O backtest não modela spread/slippage da plataforma.
5. **Amostra.** ~1.500–850 operações com IC largo; conclusões frágeis.
6. **Overfitting.** Mitigado por walk-forward e rejeição por Brier, mas nunca
   eliminado.
7. **Modelo probabilístico não calibrado** nos dados testados — por isso o
   sistema exibe **\"dados insuficientes\"** em vez de probabilidade.

---

## 7. Instruções para executar e testar

```powershell
cd "iq-analyzer"

# dependências
python -m pip install -r requirements.txt

# dados
python run.py sample                                   # sintético (teste do software)
python run.py fetch --symbol BTCUSDT --interval 1m --limit 5000   # reais públicos

# análise de um instante
python run.py analyze --csv data/BTCUSDT_1m.csv --payout 0.80

# backtest + relatório JSON
python run.py backtest --csv data/BTCUSDT_1m.csv --payout 0.80 --expiry 1 --json data/bt.json

# walk-forward fora da amostra
python run.py walkforward --csv data/BTCUSDT_1m.csv --payout 0.80 --expiry 1 --folds 2

# dashboard web (gráfico, marcações, painéis, replay)
python run.py serve        # abra http://127.0.0.1:8765

# relatório completo e exportação de sinais
python scripts/make_report.py --csv data/BTCUSDT_1m.csv --out data/REPORT.md
python scripts/dump_signals.py --csv data/BTCUSDT_1m.csv --out data/signals.csv

# testes
python -m pytest tests -q     # 50 testes
```

---

## 8. Lista objetiva de pendências

- [ ] Integração em tempo real com a **IQ Option**: impossível por via autorizada
      (sem API oficial). Depende de CSV ou do coletor por tela.
- [ ] **Calibrar o modelo probabilístico** — precisa de mais sinais resolvidos
      (o `journal.jsonl` acumula dados; recalibrar com validação temporal).
- [ ] **Validação por ativo/expiração**: repetir walk-forward para cada ativo e
      para expirações de 3/5 minutos.
- [x] **Coletor de tela funcional** (`run.py capture`): segmentação corpo/pavio
      por componentes conexos, timestamps reais, região automática, export CSV e
      assistente de calibração (`scripts/calibrate_capture.py`).
- [ ] **Coletor de tela — evolução**: OCR do eixo de preço (calibração
      automática) e robustez a temas/zoom variados.
- [ ] **Modelar custos** (spread/slippage) no backtest.
- [ ] **Interface**: evoluir o replay para reprodução em velocidade e exportação
      de imagens dos gráficos marcados.
- [ ] **Aprendizado contínuo**: rotina automática de recálculo do modelo com
      comparação ao modelo anterior (hoje o `journal.py` só registra).
- [ ] **Escala**: otimizar para séries muito longas (>100k candles) e streaming.

---

## Princípio final

O sistema mede, não promete. Nos dados testados, **não houve vantagem
estatística** — e ele reporta isso de forma explícita, preferindo a ausência de
sinal à invenção de uma taxa de acerto.
