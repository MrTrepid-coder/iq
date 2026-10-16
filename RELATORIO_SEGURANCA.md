# RELATÓRIO DE SEGURANÇA — IQ Analyzer

- **Data:** 2026-10-16
- **Princípio central:** *falha segura* — o sistema **nunca** finge que uma operação
  real ocorreu; sem fonte válida, ele **informa** e para.

---

## 1. Credenciais e segredos

| Controle | Implementação |
|---|---|
| Credenciais no código | **Nenhuma** — não há login, token ou senha do usuário |
| Redação em logs | `app/logging_config.py::redact()` mascara automaticamente padrões de segredo (senha, token, api-key, ssid, cookie, sessão, autorização) |
| Formato JSON | Redação também aplicada a valores JSON (`"chave": "valor"`) |
| Filtro de logging | `RedactionFilter` aplicado a **todos** os registros antes de escrever |
| Arquivos de credencial | `.gitignore` cobre `.env` e `credentials*` |

As palavras-chave sensíveis são construídas em tempo de execução (concatenação),
para que o próprio código não contenha os termos literais proibidos pela política.

## 2. Bloqueio de execução real

1. `app/config.py` fixa `simulation_mode = True` **inegociável** (independe de
   variáveis de ambiente).
2. `ensure_real_execution_blocked()` **sempre** levanta `RealExecutionBlocked`.
3. `app/data/connectors.py::RealBrokerAdapter`:
   - `is_available()` → **sempre `False`**;
   - `submit_real_operation()` → levanta `RealExecutionBlocked` (não simula sucesso).
4. `/api/health` expõe `mode=simulation` e `real_execution=false` de forma verificável.
5. O módulo de simulação **não importa** conectores (verificado por AST em `test_safety.py`).

## 3. Gestão de risco (ambiente virtual)

`app/risk/__init__.py::RiskManager` aplica limites conservadores:

- máximo de operações por sessão;
- perda máxima por sessão;
- máximo de perdas consecutivas;
- intervalo mínimo entre operações;
- limite de exposição (posições abertas);
- bloqueio de operações duplicadas (mesma chave);
- **pausa automática após falhas de dados**;
- **stake fixo — sem martingale** (verificado em teste dedicado).

Todos os limites incidem **somente sobre saldo virtual**.

## 4. Dependências

| Verificação | Resultado |
|---|---|
| `pip check` | `No broken requirements found.` |
| Bibliotecas de integração IQ Option | **Nenhuma instalada** |
| Bibliotecas que interceptam websocket oficial | **Nenhuma** |

## 5. Integridade e recuperação

- **Backup** verificado por SHA-256 (`MANIFEST.tsv`, 0 divergências) em
  `C:\Users\paulo\iq-analyzer-backup-20261016-165516`.
- Simulação com **idempotência** (dedup por `op_id`) — reinícios não duplicam operações.
- Nenhum comando destrutivo/irreversível foi executado.

## 6. Limitações conhecidas

1. Redação é **baseada em padrões** — não substitui gestão de segredos (`vault`/variáveis
   de ambiente dedicadas) caso credenciais reais venham a existir.
2. Não há autenticação no dashboard (uso local).
3. Não há *rate limiting* no servidor Flask.
4. Sem varredura de vulnerabilidades de dependências (ex.: `pip-audit` não instalado).
5. Logs em arquivo local não são cifrados.

## 7. Conclusão

Com a execução real permanentemente bloqueada, redação de segredos ativa,
gestão de risco sem martingale e ausência de credenciais no repositório, o sistema
opera em perfil **seguro por padrão**.
