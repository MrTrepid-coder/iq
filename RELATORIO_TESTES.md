# RELATÓRIO DE TESTES — IQ Analyzer

- **Data:** 2026-10-16
- **Runner:** pytest 9.1.1 (Python 3.12.10)
- **Diretório:** `iq-analyzer/`

---

## 1. Comando executado

```powershell
$env:PYTHONPATH="."
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest tests -q
```

## 2. Resultado final

```
118 passed in 70.02s (0:01:10)
```

| Métrica | Valor |
|---|---|
| Total de testes | **118** |
| Aprovados | **118** |
| Reprovados | **0** |
| Ignorados (skipped) | **0** |
| Esperados falhar (xfail) | **0** |
| Tempo | ~70 s |

> Linha de base antes desta auditoria: **61** testes. Após as correções e novos
> módulos: **118** testes (61 originais preservados + 57 novos). **Nenhum teste foi
> enfraquecido, removido ou marcado como skip para forçar aprovação.**

## 3. Arquivos de teste

| Arquivo | Foco |
|---|---|
| `test_indicators.py` | indicadores técnicos |
| `test_patterns.py` | padrões de candle |
| `test_strategies.py` | estratégias A–E + relatório |
| `test_probability.py` | modelo probabilístico / calibração |
| `test_no_lookahead.py` | ausência de vazamento de futuro |
| `test_cache_equivalence.py` | equivalência do cache de indicadores |
| `test_backtest.py` | backtest / walk-forward |
| `test_capture.py` | leitura de tela |
| `test_safety.py` | **segurança** (execução real bloqueada) |
| `test_breakout_regression.py` | **regressão** do bug de rompimento |
| `test_config.py` | configuração e bloqueio de execução real |
| `test_logging.py` | logging + redação de segredos |
| `test_risk.py` | gestão de risco |
| `test_simulation.py` | simulação (60 s, idempotência, persistência) |
| `test_scanner.py` | scanner multi-ativos + qualidade |
| `conftest.py` | configuração comum |

## 4. Erros encontrados durante os testes (e corrigidos)

| # | Teste que revelou | Erro no código | Correção |
|---|---|---|---|
| 1 | `test_logging` | `NameError: backupCount` em `setup_logging` | usar `backup_count` |
| 2 | `test_simulation` | histórico recarregava operações duplicadas | dedup por `op_id` |
| 3 | `test_simulation` | transição de estado inválida | inserir `ANALISANDO` na sequência |
| 4 | auditoria + `test_breakout_regression` | `detect_breakout` com loop morto | reescrita da função |
| 5 | `test_safety` (AST) | simulação importava módulo de conectores | desacoplado |
| 6 | `test_breakout_regression` (anti-tautologia) | `Level.kind` derivado do preço atual → `false_breakout` sempre `True` (Estratégia C zerada) | tipo do nível pela natureza dos swings |

## 5. Verificações complementares

| Verificação | Resultado |
|---|---|
| `compileall app run.py scripts` | exit 0 (sem erro de sintaxe) |
| `python run.py --help` | OK |
| `python run.py scan` | OK |
| `python run.py simulate` | OK |
| `python run.py backtest` / `walkforward` | OK |
| `pip check` | No broken requirements found |
| `/api/health` | `mode=simulation`, `real_execution=false` |

## 6. Verificações **NÃO** executadas

- **Lint** (`ruff`, `flake8`): **ausentes** no ambiente — não executados.
- **Type checking** (`mypy`, `pylint`): **ausentes** — não executados.
- Cobertura de código (`coverage`): não medida.

Declara-se explicitamente que **essas verificações não foram realizadas**; nada foi
inferido ou presumido em seu lugar.

## 7. Conclusão

A suíte passa integralmente (**118/118**), cobrindo segurança, ausência de
lookahead, determinismo, simulação, risco, scanner e as regressões dos bugs
corrigidos (loop morto e tautologia de `false_breakout`).
O tempo de execução total é de ~70 s.
