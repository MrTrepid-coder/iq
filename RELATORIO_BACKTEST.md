# RELATÓRIO DE BACKTEST — IQ Analyzer

- **Data:** 2026-10-16
- **Ativo:** BTCUSDT (dados públicos Binance)
- **Timeframe:** 1 minuto (60 s)
- **Amostra:** 5.000 candles
- **Payout hipotético:** 80% (`b = 0,80`)
- **Expiração:** 1 candle
- **Custo:** **não modelado** (spread/slippage/taxas = 0) — ver §9
- **Reprodução:** `python run.py backtest --csv data/BTCUSDT_1m.csv --payout 0.80 --expiry 1`
  e `python run.py walkforward --csv data/BTCUSDT_1m.csv --payout 0.80 --expiry 1`

---

## 1. Fonte e período dos dados

- Arquivo: `data/BTCUSDT_1m.csv` (5.000 candles de 1 minuto, baixados via
  `scripts/fetch_binance.py` do endpoint **público** de *klines* da Binance).
- É fonte **histórica importada** (categoria C) — **não** é integração IQ Option.
- Período coberto: ~3,47 dias contínuos de mercado.

## 2. Qualidade da amostra

- Candles validados (OHLC coerente, `ts` estritamente crescente).
- Sem dados futuros: a construção do contexto é causal (`AnalysisContext.build`
  usa somente `candles[0..i]`).
- Aviso: 3,5 dias é uma amostra **curta**; conclusões sobre robustez são limitadas.

## 3. Estratégias avaliadas

| ID | Nome (resumo) |
|---|---|
| A | Tendência (EMA + contexto multi-timeframe) |
| B | Reversão à média (Bollinger/RSI) |
| C | Rompimento e reteste de suporte/resistência |
| D | Padrões de candle |
| E | Continuação de tendência (MACD/estrutura) |

## 4. Regras de entrada e expiração

- **Entrada:** no **fechamento** do candle que gera o sinal (preço de entrada
  registrado explicitamente; a simulação abre em `ts_entry = ts_signal + 60`).
- **Expiração:** 60 s (1 candle).
- **Resultado:** WIN se o preço de saída favorece a direção; senão LOSS.
- **Payoff:** WIN paga `b = 0,80` stake; LOSS perde 1 stake.
- **Ponto de equilíbrio:** `p* = 1/(1+b) = 1/1,80 = ` **55,56%**.
- **Esperança:** `E = p·b − (1−p)`.

## 5. Métricas — *in-sample* (todas as operações)

```
Operações: 1447            Vitórias/Derrotas: 720/727
Taxa de acerto: 49,76%     IC95% (Wilson): [47,19%, 52,33%]
Ponto de equilíbrio (80%): 55,56%
Resultado líquido: -151,00 stakes
Esperança por operação: -0,1044 stakes
Drawdown máximo: 155,60 stakes
Máxima sequência de perdas: 8
```

| Estratégia | n | Acerto | IC95% |
|---|---|---|---|
| A | 501 | 48,9% | [44,5%, 53,3%] |
| B | 36 | 30,6% | [18,0%, 46,9%] |
| C | 355 | 53,2% | [48,0%, 58,4%] |
| D | 2 | 0,0% | [0,0%, 65,8%] |
| E | 553 | 49,7% | [45,6%, 53,9%] |

> **Nota sobre a Estratégia C:** a correção do bug de `false_breakout` **e** do
> tipo do nível (`Level.kind`), descritas em `AUDITORIA_TECNICA.md`, devolveram
> operações à Estratégia C. Uma versão intermediária do "conserto" deixava
> `false_breakout` **sempre** verdadeiro (tautologia), zerando C; isso foi
> corrigido. C volta a operar com taxa **abaixo** do ponto de equilíbrio, como as
> demais — ou seja, **não** há alegação de vantagem.

## 6. Métricas — *fora da amostra* (walk-forward)

**Separação temporal (sem mistura treino/teste):**

| Fold | Treino | Validação | Teste | n (teste) | Acerto |
|---|---|---|---|---|---|
| 0 | [0, 1250) | [1250, 2500) | [2500, 3750) | 409 | 49,1% |
| 1 | [1250, 2500) | [2500, 3750) | [3750, 5000) | 370 | 51,9% |

```
Agregado (só bloco de TESTE de cada fold)
Operações: 779            Vitórias/Derrotas: 393/386
Taxa de acerto: 50,45%     IC95% (Wilson): [46,94%, 53,95%]
Resultado líquido: -71,60 stakes
Esperança por operação: -0,0919 stakes
Drawdown máximo: 76,60 stakes
Máxima sequência de perdas: 8
```

| Estratégia | n | Acerto | IC95% |
|---|---|---|---|
| A | 270 | 50,0% | [44,1%, 55,9%] |
| B | 16 | 31,2% | [14,2%, 55,6%] |
| C | 179 | 54,7% | [47,4%, 61,9%] |
| D | 2 | 0,0% | [0,0%, 65,8%] |
| E | 312 | 49,7% | [44,2%, 55,2%] |

## 7. Modelo probabilístico

- **Não calibrado / não aceito** nos dados atuais.
- `Brier validação = 0,2470` (baseline `0,2500`); `Brier teste = 0,2491`
  (baseline `0,2499`) → **sem ganho** sobre a baseline (o sistema exige margem
  ≥ 0,02 para aceitar o modelo).
- Portanto o sistema reporta **“dados insuficientes / probabilidade não estimada”**
  em vez de inventar uma probabilidade.

## 8. Interpretação honesta

1. **Não há vantagem demonstrada.** As taxas (≈49–50%) ficam **abaixo** do ponto de
   equilíbrio de 55,56%. Os intervalos de confiança incluem valores abaixo do
   *break-even* — ou seja, a esperança é **negativa**.
2. A Estratégia B tem desempenho aparentemente ruim, mas `n` pequeno (IC largo).
3. Os resultados **não** são prova de lucratividade; são prova de **ausência de
   vantagem** nesta amostra.
4. Sem modelagem de custos, o cenário real seria **pior** (não melhor).

## 9. Limitações e incerteza

- Amostra curta (~3,5 dias) de um único ativo.
- Payout fixo hipotético; na prática varia por ativo/horário.
- **Custos ignorados** (spread/slippage).
- Dados públicos de mercado ≠ ativos OTC da IQ Option.
- Múltiplas estratégias → risco de sobreajuste se parâmetros forem escolhidos no
  conjunto de teste (aqui **não** foram: seleção só em treino/validação).

## 10. Como reproduzir

```powershell
$env:PYTHONPATH="."
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" run.py backtest    --csv data/BTCUSDT_1m.csv --payout 0.80 --expiry 1
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" run.py walkforward --csv data/BTCUSDT_1m.csv --payout 0.80 --expiry 1
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" scripts/make_report.py --csv data/BTCUSDT_1m.csv --out data/REPORT.md
```
