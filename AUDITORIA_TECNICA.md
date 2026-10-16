# AUDITORIA TÉCNICA — IQ Analyzer

- **Projeto:** `C:\Users\paulo\OneDrive\Área de Trabalho\opçoes\iq-analyzer`
- **Data da auditoria:** 2026-10-16
- **Commit Git de referência:** `7e8f95d` (branch `main`)
- **Backup verificado:** `C:\Users\paulo\iq-analyzer-backup-20261016-165516`
  (46 arquivos, 682.173 bytes, `MANIFEST.tsv` SHA-256 com **0 divergências**)
- **Modo:** análise/simulação — **execução real bloqueada**
- **Versão do app:** `0.2.0` (era `0.1.0` antes desta auditoria)

> Este documento descreve o que foi auditado, o que foi corrigido e o que permanece
> pendente. Não substitui os demais relatórios (`RELATORIO_BACKTEST.md`,
> `RELATORIO_TESTES.md`, `RELATORIO_SEGURANCA.md`, `RELATORIO_INTEGRACAO_IQ_OPTION.md`).

---

## 1. Estado inicial encontrado

| Item | Situação |
|---|---|
| Código existente | Projeto Python completo (criado em sessão anterior), 61 testes passando |
| Python | 3.12.10 (sem virtualenv; dependências no Python do usuário) |
| Dependências | numpy 2.5.4, pandas 3.0.6, scikit-learn 1.9.1, scipy 1.18.1, Flask 3.1.3, pillow 12.3.0, pytest 9.1.1 |
| Git | branch `main`; **apenas `README.md` commitado**; todo o código era *untracked* |
| OneDrive | pasta sincronizada (risco de conflito durante cópia — mitigado com backup fora do OneDrive) |
| Execução real | bloqueada apenas por convenção/código de análise (sem *guard* explícito reutilizável) |
| Relatórios | `ENTREGA.md` e `data/REPORT.md` existiam |

**Nenhuma alteração local preexistente foi sobrescrita** (todo o código era *untracked*);
nenhum comando destrutivo de Git foi usado.

---

## 2. Arquitetura encontrada

```
app/
  core/        candles, indicators, patterns, structure
  analysis/    context + IndicatorCache (anti-lookahead)
  strategies/  estratégias A–E
  signal/      filtro de qualidade (10 critérios) + SignalReport
  probability/ regressão logística + calibração + Brier + IC de Wilson
  backtest/    backtest + walk-forward
  data/        capture (leitura de tela) + __init__
  ui/          server (Flask) + template do dashboard
  journal.py   registro de sinais/resultados em JSONL
run.py         CLI
scripts/       fetch_binance, make_report, dump_signals, calibrate_capture, make_sample_screenshot
tests/         16 arquivos de teste
```

A arquitetura era **boa** (separação clara, propriedade anti-lookahead verificável,
`IndicatorCache` causal). Ela foi **preservada**; apenas foram acrescentados módulos
faltantes e corrigidos bugs pontuais.

---

## 3. Problemas identificados

| # | Gravidade | Arquivo / função | Problema | Impacto | Correção |
|---|---|---|---|---|---|
| 1 | **ALTO** | `app/core/structure.py` → `detect_breakout` | Loop morto: `range(last + 1, len(candles))` é **sempre vazio** (`last = len-1`). `false_breakout` nunca era `True`. | A Estratégia C (rompimento/reteste) **nunca rejeitava falsos rompimentos** — operava armadilhas de rompimento. | Reescrita: varre os últimos `lookback` candles, avalia os candles **posteriores** ao rompimento e respeita o tipo do nível. Testes de regressão adicionados. |
| 2 | **MÉDIO** | `app/logging_config.py` → `setup_logging` | `backupCount=backupCount` (variável inexistente; parâmetro é `backup_count`) → `NameError`. | O módulo de logging não inicializava. | Corrigido para `backup_count`. (Detectado pelos testes novos.) |
| 3 | **MÉDIO** | `app/simulation/__init__.py` → `_load_history` | Cada operação era gravada 2× (abertura + resolução); a recarga contava duplicatas. | Histórico inconsistente após reinício (violava idempotência). | Recarga deduplica por `op_id`, mantendo a **última** versão. |
| 4 | **MÉDIO** | `app/simulation/__init__.py` → `open_simulation` | Transição inválida `AGUARDANDO_DADOS → OPERACAO_ABERTA`. | Máquina de estados quebrava. | Passa por `ANALISANDO → SINAL_DISPONIVEL → OPERACAO_ABERTA`. |
| 5 | **MÉDIO** | (lacunas funcionais vs. briefing) | Ausência de `config`, `logging`, `risk`, `simulation`, `scanner`, `connectors` e *guard* de execução real. | Requisitos das §7, §8, §12, §13, §14, §16 não atendidos. | Implementados (ver §5). |
| 6 | **ALTO** | `app/core/structure.py` → `support_resistance` (`Level.kind`) | O tipo do nível era derivado da **posição do preço** (`"resistance" if price > last_close else "support"`). Como `detect_breakout` filtra pelo tipo, um nível "resistência" estava **sempre** acima do último fechamento, de modo que todo rompimento de alta detectado em candles anteriores era classificado como falso. **Tautologia:** `false_breakout` passava a ser `True` em **100%** dos casos (medido: 501/501). | A Estratégia C ficava **zerada** — um "conserto" que, na prática, desligava a estratégia. A primeira versão desta auditoria **interpretou erroneamente** o 0 como comportamento de mercado; a verificação seguinte provou a tautologia. | O tipo do nível passou a vir da **natureza dos swings** que o formam (topos → resistência; fundos → suporte), independente da posição atual. `false_breakout` volta a ser significativo (255 falsos em 1.175 rompimentos) e a Estratégia C volta a operar (n=355, 53,2% *in-sample*). Teste de regressão anti-tautologia adicionado. |

---

## 4. Correções realizadas (resumo)

1. **`detect_breakout` + `Level.kind`** — dois defeitos encadeados:
   - **(a) loop morto** em `detect_breakout` (problema nº 1): `range(last + 1, len)`
     é sempre vazio → `false_breakout` nunca era `True` → a Estratégia C operava
     armadilhas de rompimento.
   - **(b) tautologia de `Level.kind`** (problema nº 6): com o tipo derivado da
     posição do preço, o filtro de tipo fazia **todo** rompimento aparecer como
     falso (501/501 medidos). A Estratégia C zerava. A primeira leitura desta
     auditoria atribuiu o 0 ao mercado — **estava errada**; a verificação
     seguinte expôs a tautologia.
   - **Correção final:** tipo do nível pela **natureza dos swings** (topos →
     resistência; fundos → suporte). `false_breakout` torna-se significativo
     (255 falsos em 1.175 rompimentos) e a Estratégia C volta a operar
     (n=355, 53,2% *in-sample*; n=179, 54,7% fora da amostra).
   - Testes de regressão: `tests/test_breakout_regression.py` (inclui guarda
     anti-tautologia). Ver `RELATORIO_BACKTEST.md`.
2. **Logging** — `NameError` corrigido; redação de segredos funcional.
3. **Simulação** — persistência idempotente (dedup por `op_id`) e máquina de estados válida.

---

## 5. Lacunas funcionais implementadas

| Módulo | Responsabilidade |
|---|---|
| `app/config.py` | Config centralizada e validada; `simulation_mode=True` **inegociável**; `ensure_real_execution_blocked()` (guard que sempre recusa). |
| `app/logging_config.py` | Logging estruturado com **rotação** e **redação automática** de segredos. |
| `app/risk/__init__.py` | `RiskManager`: limite de operações/sessão, perda/sessão, perdas consecutivas, intervalo mínimo, exposição, bloqueio de duplicados, pausa por falha de dados. **Sem martingale**. |
| `app/simulation/__init__.py` | `SimulationEngine` com máquina de estados explícita, expiração de 60 s, idempotência e persistência JSONL. |
| `app/scanner/__init__.py` | Scanner multi-ativos com qualidade de dados, isolamento de falhas, dedup e ordenação por qualidade. |
| `app/data/connectors.py` | Arquitetura de adaptadores; adaptador real **indisponível** que falha de forma segura. |
| `run.py` | Novos comandos `scan` e `simulate`. |

---

## 6. Verificações executadas

| Verificação | Resultado |
|---|---|
| `python -m compileall app run.py scripts` | **OK** (exit 0) |
| `python run.py --help` | OK — 9 subcomandos |
| `python -m pytest tests -q` | **118 passed** (0 failed, 0 skipped) |
| `python run.py scan` (multi-ativos) | OK — 3 ativos, falha isolada tratada |
| `python run.py simulate` (expiração 60 s) | OK — parou no limite de risco (20 ops; 10/10, 50,0%, −2,00 stakes) |
| `python run.py backtest` / `walkforward` | OK — métricas em `data/REPORT.md` |
| `pip check` | `No broken requirements found.` |
| Dashboard (`/api/health`) | `mode=simulation`, `real_execution=false` |

## 7. Verificações **NÃO** executadas (ferramenta ausente)

- **Lint** (ruff/flake8) — **não instalados**.
- **Type checking** (mypy/pylint) — **não instalados**.
- Nenhuma dessas ferramentas foi executada; não se afirma o contrário.

---

## 8. Pendências conhecidas

1. **Sem API oficial da IQ Option** — bloqueio externo (§ `RELATORIO_INTEGRACAO_IQ_OPTION.md`).
2. **Modelo probabilístico não calibrado**: Brier validação 0,2470 vs. baseline 0,2500 e teste 0,2491 vs. 0,2499 → **sem ganho** sobre a baseline (o critério exige margem ≥ 0,02). O modelo treina, mas **não é aceito**.
3. **Coletor de tela sem OCR** do eixo de preço.
4. **Custos (spread/slippage) não modelados** no backtest.
5. **Estratégia C** volta a operar, porém ainda **abaixo do ponto de equilíbrio** (53,2% *in-sample* / 54,7% fora) — como todas as demais.
6. **Sem lint/type-check** no ambiente.
