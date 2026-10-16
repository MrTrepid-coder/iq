# IQ Analyzer

Sistema de **análise técnica e probabilística** para opções binárias, em
**modo análise/simulação**. A execução real de ordens é **bloqueada por padrão**
e não pode ser ativada por variável de ambiente.

> **Princípio:** o sistema **mede, não promete**. Prefere a ausência de sinal à
> invenção de uma taxa de acerto.

## Aviso importante

- **Não há API oficial** de execução da IQ Option para o público. Este projeto
  **não** usa bibliotecas que interceptam o canal interno da plataforma.
- Os dados usados na validação vêm de **fontes históricas/importadas**
  (CSV, captura de tela) e de fonte **pública** (Binance) apenas para validar o motor.
- Nos dados testados **não houve vantagem estatística**. Ver `RELATORIO_BACKTEST.md`.

## Requisitos

- Python 3.12
- Dependências em `requirements.txt` (numpy, pandas, scikit-learn, scipy, Flask, pillow, pytest)

```powershell
python -m pip install -r requirements.txt
```

## Uso rápido

```powershell
$env:PYTHONPATH="."

# dados
python run.py sample                                            # sintético (teste)
python run.py fetch --symbol BTCUSDT --interval 1m --limit 5000 # reais públicos (Binance)

# análise / backtest
python run.py analyze     --csv data/BTCUSDT_1m.csv --payout 0.80
python run.py backtest    --csv data/BTCUSDT_1m.csv --payout 0.80 --expiry 1
python run.py walkforward --csv data/BTCUSDT_1m.csv --payout 0.80 --expiry 1

# scanner multi-ativos e simulação virtual (expiração 60 s)
python run.py scan     --assets BTCUSDT_1m.csv sample.csv
python run.py simulate --csv data/BTCUSDT_1m.csv --payout 0.80 --store data/simulation.jsonl

# dashboard web
python run.py serve     # http://127.0.0.1:8765

# testes
python -m pytest tests -q
```

## Segurança

- `simulation_mode` é fixo em `True`; `ensure_real_execution_blocked()` sempre recusa.
- O adaptador real (`app/data/connectors.py`) está **indisponível** e **não simula sucesso**.
- Logs redigem segredos automaticamente (`app/logging_config.py`).
- Detalhes em `RELATORIO_SEGURANCA.md`.

## Documentação

| Documento | Conteúdo |
|---|---|
| `AUDITORIA_TECNICA.md` | estado encontrado, problemas e correções |
| `RELATORIO_INTEGRACAO_IQ_OPTION.md` | o que é integração comprovada × simulada × inexistente |
| `RELATORIO_BACKTEST.md` | métricas in-sample e fora da amostra |
| `RELATORIO_TESTES.md` | suíte de testes e verificações |
| `RELATORIO_SEGURANCA.md` | credenciais, bloqueio de execução real, risco |
| `ENTREGA.md` | documento de entrega consolidado |
| `data/REPORT.md` | relatório de backtest gerado |

## Versão

`0.2.0` — modo simulação/análise.
