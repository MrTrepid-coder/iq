# ENTREGA — Sistema Inteligente de Análise Técnica e Probabilística (IQ Analyzer)

Documento de entrega seguindo a lista obrigatória do briefing.
**Modo simulação/análise — execução real desativada por padrão.**

- **Versão:** `0.2.0`
- **Data desta revisão:** 2026-10-16
- **Versão anterior deste documento:** preservada em `docs/ENTREGA_20261016_pre-auditoria.md`
  (e no backup externo — ver §0.3).

> Esta revisão corresponde à **auditoria, correção e finalização** do projeto.
> Os relatórios detalhados estão em `AUDITORIA_TECNICA.md`,
> `RELATORIO_INTEGRACAO_IQ_OPTION.md`, `RELATORIO_BACKTEST.md`,
> `RELATORIO_TESTES.md` e `RELATORIO_SEGURANCA.md`.

---

## 0. Auditoria, backup e correções (esta revisão)

### 0.1 Estado inicial desta rodada

- Projeto Python já criado em sessão anterior; **61 testes** passando.
- Git: branch `main`, commit `7e8f95d` — **apenas `README.md` commitado**; todo o
  código era *untracked*.
- Ambiente: Python 3.12.10 (sem virtualenv); numpy 2.5.4, pandas 3.0.6,
  scikit-learn 1.9.1, scipy 1.18.1, Flask 3.1.3, pillow 12.3.0, pytest 9.1.1.

### 0.2 Correções de bugs

| # | Gravidade | Local | Problema | Correção |
|---|---|---|---|---|
| 1 | ALTO | `core/structure.py::detect_breakout` | loop morto ⇒ `false_breakout` nunca era `True`; a Estratégia C operava falsos rompimentos | reescrita da função + respeito ao tipo do nível |
| 1b | ALTO | `core/structure.py::support_resistance` (`Level.kind`) | tipo do nível derivado do preço atual ⇒ `false_breakout` **sempre** `True` (tautologia), zerando a Estratégia C | tipo do nível pela **natureza dos swings** (topos → resistência; fundos → suporte) |
| 2 | MÉDIO | `logging_config.py::setup_logging` | `NameError` (`backupCount`) | usar `backup_count` |
| 3 | MÉDIO | `simulation/_load_history` | histórico recarregava operações duplicadas | dedup por `op_id` (última versão prevalece) |
| 4 | MÉDIO | `simulation/open_simulation` | transição de estado inválida | passou a usar `ANALISANDO`/`SINAL_DISPONIVEL` |

### 0.3 Backup (FASE 0/1)

- Backup externo ao projeto **e ao OneDrive**:
  `C:\Users\paulo\iq-analyzer-backup-20261016-165516` — 46 arquivos, 682.173 bytes.
- Integridade verificada por SHA-256 (`MANIFEST.tsv`): **0 divergências**.
- Nenhuma operação destrutiva/irreversível foi executada.

### 0.4 Novos módulos implementados

| Módulo | Responsabilidade |
|---|---|
| `app/config.py` | config centralizada e validada; `simulation_mode=True` inegociável; `ensure_real_execution_blocked()` |
| `app/logging_config.py` | logging com rotação + redação de segredos |
| `app/risk/__init__.py` | `RiskManager` (limites, sem martingale) |
| `app/simulation/__init__.py` | simulação automática (expiração 60 s, idempotência, persistência) |
| `app/scanner/__init__.py` | scanner multi-ativos + qualidade de dados |
| `app/data/connectors.py` | adaptadores de dados; adaptador real indisponível |

Novos comandos em `run.py`: **`scan`** e **`simulate`**.
`app/__init__.py` atualizado para `0.2.0`.

---

## 1. Resumo do estado inicial do projeto (FASE 1 — auditoria original)

A pasta `opçoes/` continha **apenas** o atalho `IQ Option.lnk`. **Não havia
código, banco de dados, dependências nem integração** com a IQ Option.

| Item | Situação encontrada |
|---|---|
| Código existente | Nenhum |
| Linguagem/framework | — (definido: Python 3.12) |
| Banco de dados | Nenhum (adotado: CSV/JSONL) |
| Integração IQ Option | Inexistente |
| API oficial IQ Option | **Não existe** para o público |
| Ambiente | Python 3.12.10 instalado; numpy, pandas, scikit-learn, flask, pillow, pytest |

**Decisão de arquitetura sobre os dados.** A IQ Option não publica API oficial.
Bibliotecas não oficiais interceptam o websocket interno — violam os termos e o
próprio briefing. Por isso a coleta foi implementada em **duas vias permitidas**:
1. **CSV** (dados históricos do usuário);
2. **Coletor por leitura de tela** (`app/data/capture.py`) — lê apenas o que já
   está visível na tela do usuário, sem rede, login ou API interna.

Para **validar o motor com dados de mercado reais**, foi usada a **API pública da
Binance** (klines, gratuita e documentada) — 5.000 candles reais de BTCUSDT 1m.

---

## 2. Arquivos do projeto (versão 0.2.0)

```
iq-analyzer/
  run.py                         CLI (sample, fetch, analyze, backtest, walkforward,
                                 serve, scan, simulate, capture)
  requirements.txt
  README.md
  ENTREGA.md                     (este documento)
  AUDITORIA_TECNICA.md
  RELATORIO_INTEGRACAO_IQ_OPTION.md
  RELATORIO_BACKTEST.md
  RELATORIO_TESTES.md
  RELATORIO_SEGURANCA.md
  app/
    config.py                    configuração + bloqueio de execução real
    logging_config.py            logging com rotação + redação de segredos
    core/candles.py              Candle/CandleSeries, validação OHLC, window() anti-lookahead, resample
    core/indicators.py           EMA, RSI, MACD, Bollinger, ATR, ADX, VWAP, volatilidade, slope
    core/patterns.py             padrões de velas por regras objetivas
    core/structure.py            tendência, swing points, S/R, consolidação, rompimentos, regime
    analysis/context.py          AnalysisContext + IndicatorCache (desempenho sem lookahead)
    strategies/__init__.py       Estratégias A–E
    signal/__init__.py           filtro de qualidade (10 critérios) + SignalReport
    probability/__init__.py      regressão logística + calibração + Brier + IC de Wilson
    backtest/__init__.py         backtest sem lookahead + walk-forward + métricas
    risk/__init__.py             gestão de risco
    simulation/__init__.py       simulação automática (60 s)
    scanner/__init__.py          scanner multi-ativos
    data/capture.py              coletor por leitura de tela
    data/connectors.py           adaptadores de fonte de dados
    data/__init__.py
    ui/server.py + ui/templates/index.html   dashboard web
    journal.py                   registro estruturado (aprendizado contínuo)
  scripts/
    fetch_binance.py             dados reais públicos (validação)
    make_report.py               gera data/REPORT.md
    dump_signals.py              exporta todos os sinais (inclusive perdedores)
    calibrate_capture.py         assistente de calibração do coletor por tela
    make_sample_screenshot.py    gera print sintético de teste do coletor
  tests/                         118 testes (unitários, integração, segurança)
  docs/ENTREGA_20261016_pre-auditoria.md   versão anterior deste documento
  data/sample.csv                dados sintéticos de exemplo
  data/BTCUSDT_1m.csv            5.000 candles reais (validação)
  data/REPORT.md                 relatório medido
```

---

## 3. Estratégias implementadas e suas regras

| ID | Nome | Regras de entrada | Invalidação |
|----|------|-------------------|-------------|
| A | Continuação de tendência | Estrutura HH/HL (ou LH/LL) + EMAs 9/21/50 alinhadas + ADX ≥ 20 + candle a favor + sem padrão de reversão + sem consolidação | Fechamento contra a tendência por 1·ATR ou perda da EMA21 |
| B | Reversão em S/R | Preço a ≤ 0,35·ATR de um nível + padrão de rejeição + perda de força do movimento (ADX caindo / RSI extremo / MACD enfraquecendo) | Fechamento além do nível por 0,5·ATR |
| C | Rompimento e reteste | Fechamento além do nível por ≥ 0,25·ATR + compressão de Bollinger antes + reteste com defesa ou candle de continuação | Retorno de fechamento para dentro da zona (**agora realmente detectado**) |
| D | Reversão estatística | RSI extremo **E** %B extremo **E** exaustão de momentum; **bloqueada** contra tendência forte (ADX ≥ 30 + EMAs alinhadas) e contra o 5m | Candle forte (> 1·ATR) a favor da tendência anterior |
| E | Confluência | ≥ 3 fontes independentes (tendência, padrão, momentum, níveis, 5m) na mesma direção, sem fonte relevante contra | Inversão de qualquer fonte |

O **RSI extremo sozinho nunca é sinal** (só combinado na Estratégia D).
> **Nota sobre a Estratégia C:** a correção do bug do loop morto + da tautologia de
> `Level.kind` (topos → resistência; fundos → suporte) devolveu operações à
> Estratégia C. Ela volta a operar de forma válida, porém **abaixo do ponto de
> equilíbrio** (53,2% *in-sample* / 54,7% fora da amostra). Detalhes em
> `RELATORIO_BACKTEST.md`.

---

## 4. Relatórios de backtesting e testes fora da amostra

**Fonte:** 5.000 candles reais BTCUSDT 1m (API pública Binance).
**Payout:** 80% ⇒ ponto de equilíbrio **55,56%**.
**Expiração:** 1 candle/vela. **Custos não modelados.**

> Números **após** a auditoria (v0.2.0), incluindo a correção da tautologia de
> `Level.kind`.

### 4.1 Backtest completo (in-sample)

```
Operações: 1447        Vitórias/Derrotas: 720/727
Taxa de acerto: 49,76%   IC95% (Wilson): [47,19%, 52,33%]
Resultado líquido: -151,00 stakes   Esperança/op: -0,1044 stakes
Drawdown máximo: 155,60 stakes   Máx. sequência de perdas: 8

[A] n=501 acerto=48,9%  [B] n=36 acerto=30,6%  [C] n=355 acerto=53,2%
[D] n=2   acerto=0,0%   [E] n=553 acerto=49,7%
```

### 4.2 Walk-forward (FORA da amostra — treino → validação → teste)

| Fold | Treino | Validação | Teste | n teste | Acerto teste |
|---|---|---|---|---|---|
| 0 | (0,1250) | (1250,2500) | (2500,3750) | 409 | 49,1% |
| 1 | (1250,2500) | (2500,3750) | (3750,5000) | 370 | 51,9% |

```
Agregado fora da amostra: n=779  acerto=50,45%  IC95%=[46,94%, 53,95%]
Resultado líquido: -71,60 stakes   Esperança/op: -0,0919 stakes
Drawdown máximo: 76,60 stakes   Máx. sequência de perdas: 8

[A] n=270 acerto=50,0%  [B] n=16 acerto=31,2%
[C] n=179 acerto=54,7%  [D] n=2   acerto=0,0%   [E] n=312 acerto=49,7%
```

### 4.3 Modelo probabilístico

```
Calibração: nenhum
Brier validação: 0,2470 | baseline val: 0,2500
Brier teste:     0,2491 | baseline teste: 0,2499
→ sem ganho sobre a baseline ⇒ MODELO REJEITADO (não exibe probabilidade)
```

Relatório completo em `data/REPORT.md`.

---

## 5. Taxa de acerto comprovada

| Conjunto | n | Taxa | IC95% (Wilson) |
|---|---|---|---|
| In-sample | 1447 | **49,76%** | [47,19%, 52,33%] |
| Fora da amostra (walk-forward) | 779 | **50,45%** | [46,94%, 53,95%] |

**Conclusão honesta:** a taxa de acerto fica **abaixo do ponto de equilíbrio
(55,56%)** e o intervalo de confiança **inclui 50%**. **Não há vantagem
estatística demonstrada** neste ativo (BTCUSDT), expiração (1 candle) e período.
O sistema **não atinge** a meta de pesquisa de >80% e **não inventa** resultado
para atingi-la.

---

## 5.1 Coletor por leitura de tela — verificação

O coletor foi tornado **funcional** e validado:

- Segmentação por **componentes conexos**: corpo + pavios = **uma** vela.
- **Separação corpo/pavio** por largura de linha → open/close = corpo; high/low = extremos.
- **Timestamps reais** em minutos (última vela = minuto atual, truncado).
- **Região automática** pela posição das velas (`chart_region_from_image`).
- **Calibração** por dois pontos, salvável/carregável em JSON.
- **Comando** `run.py capture` (lê um PNG com `--shot` ou a tela ao vivo) e **export CSV**.

Verificação (`tests/test_capture.py`), incluindo **ponta a ponta**: um gráfico
sintético de 40 velas é desenhado e **todas as 40 velas são recuperadas** com OHLC
dentro de ~2,5 px de tolerância. Demo real executada: `--shot` de 60 velas → **60 velas**.

**Limitação remanescente:** duas velas da **mesma cor sem nenhum espaço** entre si
podem ser lidas como uma; sem OCR do eixo de preço.

---

## 5.2 Scanner multi-ativos e simulação automática (novos)

- `run.py scan --assets a.csv b.csv ...` varre vários ativos, **isola falhas**
  (um ativo ausente não derruba os demais), classifica **qualidade** dos dados e
  ordena os resultados. A qualidade é **coerência da estratégia**, não probabilidade.
- `run.py simulate --csv data/BTCUSDT_1m.csv` abre operações **virtuais** com
  **expiração de 60 s**, aplica **gestão de risco** e grava histórico idempotente
  (`data/simulation.jsonl`). Verificação: parou exatamente no limite de 20 operações
  da sessão; 10 vitórias / 10 derrotas (50,00%), PnL −2,00 stakes. **Nenhuma ordem real.**

---

## 6. Limitações e riscos encontrados

1. **Sem API oficial da IQ Option.** Dados "reais da plataforma" exigem CSV ou
   captura de tela (esta última é aproximada e sensível a tema/zoom).
2. **Ativo de validação ≠ ativo negociado.** A validação usou BTCUSDT (fonte
   pública). Ativos OTC da IQ Option podem ter comportamento diferente.
3. **Universalidade não comprovada.** Nenhuma estratégia venceu o break-even em
   BTC 1m; nada garante desempenho melhor em outros ativos/períodos.
4. **Custos.** O backtest não modela spread/slippage da plataforma.
5. **Amostra.** ~1.450/780 operações com IC largo; conclusões frágeis.
6. **Overfitting.** Mitigado por walk-forward e rejeição por Brier, mas nunca eliminado.
7. **Modelo probabilístico não calibrado** nos dados testados (amostra insuficiente).
8. **Sem lint/type-check** no ambiente (ferramentas ausentes) — não executados.

---

## 7. Instruções para executar e testar

```powershell
cd "iq-analyzer"
$env:PYTHONPATH="."

# dependências
python -m pip install -r requirements.txt

# dados
python run.py sample                                            # sintético (teste do software)
python run.py fetch --symbol BTCUSDT --interval 1m --limit 5000 # reais públicos

# análise de um instante
python run.py analyze --csv data/BTCUSDT_1m.csv --payout 0.80

# backtest + walk-forward
python run.py backtest    --csv data/BTCUSDT_1m.csv --payout 0.80 --expiry 1
python run.py walkforward --csv data/BTCUSDT_1m.csv --payout 0.80 --expiry 1

# scanner multi-ativos e simulação virtual (60 s)
python run.py scan     --assets BTCUSDT_1m.csv sample.csv
python run.py simulate --csv data/BTCUSDT_1m.csv --payout 0.80 --store data/simulation.jsonl

# dashboard web
python run.py serve        # http://127.0.0.1:8765

# relatório completo e exportação de sinais
python scripts/make_report.py --csv data/BTCUSDT_1m.csv --out data/REPORT.md
python scripts/dump_signals.py --csv data/BTCUSDT_1m.csv --out data/signals.csv

# testes
python -m pytest tests -q     # 118 testes
```

---

## 8. Lista objetiva de pendências

- [ ] Integração em tempo real com a **IQ Option**: impossível por via autorizada
      (sem API oficial). Depende de CSV ou do coletor por tela.
- [ ] **Calibrar o modelo probabilístico** — precisa de mais sinais resolvidos
      (o `journal.jsonl` acumula dados; recalibrar com validação temporal).
- [ ] **Validação por ativo/expiração**: repetir walk-forward para cada ativo e
      para expirações de 3/5 minutos.
- [x] **Coletor de tela funcional** (`run.py capture`).
- [ ] **Coletor de tela — evolução**: OCR do eixo de preço e robustez a temas/zoom.
- [ ] **Modelar custos** (spread/slippage) no backtest.
- [ ] **Interface**: evoluir o replay para reprodução em velocidade e exportação de imagens.
- [ ] **Aprendizado contínuo**: rotina automática de recálculo do modelo (hoje o `journal.py` só registra).
- [ ] **Escala**: otimizar para séries muito longas (>100k candles) e streaming.
- [ ] **Lint/type-check**: instalar e executar ruff/flake8/mypy (ausentes no ambiente).
- [ ] **Estratégia C**: reavaliar em outros ativos/períodos (opera em BTC 1m, porém ainda abaixo do break-even).

---

## Princípio final

O sistema mede, não promete. Nos dados testados, **não houve vantagem
estatística** — e ele reporta isso de forma explícita, preferindo a ausência de
sinal à invenção de uma taxa de acerto. A **execução real permanece bloqueada**.
