# Implementation Plan: Refine Happy Path

**Branch**: `001-refine-happy-path` | **Date**: 2026-10-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-refine-happy-path/spec.md`

## Summary

Fatia vertical MVP da v2: uma rodada completa que processa cards na raia **To Refine** — do gatilho do scheduler (a cada 5 min) ao card refinado de volta no board em **Refined** — passando pelo agente (Claude Code CLI + GLM via Z.ai, com busca web), pela preservação do registro original (bloco 📝 imutável) e pela escrita da seção `## 🔍 Refinamento` pelo orquestrador.

Abordagem técnica: processo Python de vida curta (`uv run notion-copilot run`) disparado por launchd/cron; arquitetura hexagonal (domain puro → application com ports → adapters Notion API / Claude CLI); fila é a própria coluna To Refine (sem broker); agente recebe somente MCPs de busca web e devolve JSON validado com Pydantic; orquestrador é o único a escrever no Notion.

## Technical Context

**Language/Version**: Python 3.12+ (pinado em `.python-version`, instalado pelo `uv`)

**Primary Dependencies**: `typer` (CLI), `pydantic` + `pydantic-settings` (`.env` e saída do agente), `notion-client` (API do Notion), `platformdirs` (diretório de estado: lock e logs — research R3), `httpx` (**condicional** — entra somente se `notion-client` não expuser o endpoint markdown; verificação de implementação, research R2). Externos ao processo: Claude Code CLI (executável, subprocesso), MCPs da Z.ai (`web_search_prime`, `web_reader`)

**Storage**: Notion board (estado de verdade: Pipeline, IA status, IA atualizado em) + logs locais (eventos JSON + rastro `stream-json` do agente). Sem banco de dados próprio.

**Testing**: `pytest` com fakes dos ports (sem rede, sem Notion, sem modelo — RNF-M3); `ruff` (lint/format), `mypy` (tipos em `domain/` e `application/`)

**Target Platform**: máquina local da usuária — macOS (launchd) e Linux (cron). Sem servidor, sem daemon.

**Project Type**: CLI de processo curto (`notion-copilot run`), invocado por scheduler.

**Performance Goals**: card movido para To Refine chega em Refined em ≤ 15 min em 95% dos casos (SC-001); rodada a cada 5 min; timeout de 10 min por card no agente (RNF-C4); fila vazia custa 1 consulta.

**Constraints**: nenhum segredo em log (RNF-O5); `.env` permissão 600; sem rodadas sobrepostas (FR-003); até 5 cards/rodada; escrita da página em um único request `update_content` sobre o template do banco (sem chunking; página grande demais → `validation_error` permanente); template do banco já entrega o esqueleto da seção 🔍 — o orquestrador preenche, não cria; capabilities Read content, Update content e Insert comments habilitadas na integração (senão 403 — research R1/R6).

**Scale/Scope**: 1 usuária, ~4 rodadas/hora, ≤ 5 cards/rodada, board único.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Gate | Status |
|---|---|---|
| I. Regras em código, não em prompt (NON-NEGOTIABLE) | Máquina de estados (seleção, ⏳/⚠️/❓, idempotência, regra dos 30 min) em `domain/rules.py`; agente nunca decide estado | ✅ Pass |
| II. Hexagonal com núcleo puro | `domain/` zero IO; `application/` declara ports (Protocols); adapters implementam; testes do núcleo sem rede | ✅ Pass |
| III. Segurança por ausência de ferramenta (NON-NEGOTIABLE) | Etapa Refine: somente `web_search_prime` + `web_reader` via `--allowedTools`/`--mcp-config`; nenhuma ferramenta Notion ao agente (FR-008) | ✅ Pass |
| IV. Módulos profundos, informação escondida | `adapters/notion_api.py` único que conhece a API do Notion (inclui endpoints markdown); `adapters/claude_cli.py` único que conhece flags do CLI | ✅ Pass |
| V. Aprovação humana antes de ação irreversível | Escopo só lê/escreve na própria página do card; registro original imutável; nenhuma ação fora do card nesta feature | ✅ Pass |
| VI. Test-first no núcleo | Testes obrigatórios (fakes): seleção da fila, idempotência (FR-015), transições de raia/IA status, `is_stale` 30 min, retry/backoff | ✅ Pass |
| VII. Observabilidade estruturada | Evento JSON por passo (horário, `run_id`, `card_id`, etapa, evento, duração); rastro `stream-json` por execução do agente; sem segredos | ✅ Pass |
| VIII. Simplicidade e YAGNI | Sem broker, sem daemon, sem endpoint público; retry com laço manual (sem tenacity); escrita via endpoint markdown nativo, sem conversor próprio | ✅ Pass |
| IX. Comportamento como artefato versionado | `prompts/refine.md` versionado; tabela de etapas em `domain/stages.py` (extensível a Plan/Execute sem tocar o loop) | ✅ Pass |
| X. Portabilidade e reprodutibilidade | `uv sync` + `uv.lock`; `.env` 600 + `.env.example`; roda em macOS e Linux | ✅ Pass |
| Red Flags (Ousterhout) | Evita Temporal Decomposition via `domain/stages.py`; sem pass-through, sem repetition, nomes precisos | ✅ Pass |

**Nota ADR-001**: a spec muda o intervalo de 15 → 5 min. ADR-001 é imutável; a feature DEVE registrar um **ADR-007** que o substitui (tarefa em `tasks.md`), superando também a frase do ADR-001 que permitia selecionar cards ❓/⚠️ — o FR-004 só permite IA status vazio.

**Nota ADR-006 (premissa confirmada, promoção pendente)**: os endpoints markdown da API `2026-03-11` (`GET`/`PATCH /v1/pages/{page_id}/markdown`) confirmam a premissa do ADR-006 ("a API aceita markdown, sem conversão para blocos"). O ADR-006 segue em status **Proposto**; promovê-lo a Aceito é tarefa da feature (junto com a criação do ADR-007), citando a R1. A escrita usa o comando `update_content` (recomendado; `insert_content` é legacy) — research R1.

## Project Structure

### Documentation (this feature)

```text
specs/001-refine-happy-path/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── agent-output.md  # Contrato JSON de saída do agente (etapa Refine)
│   └── cli-commands.md  # Contrato de comandos da CLI e do scheduler
└── tasks.md             # Phase 2 output (/speckit-tasks — NÃO criado por /speckit-plan)
```

### Source Code (repository root)

```text
src/notion_copilot/
  domain/                 # Regras do pipeline. Zero IO. Não conhece Notion nem Claude.
    models.py             # Card, IAStatus, RunResult, RefineOutput (Pydantic)
    stages.py             # Tabela de etapas (fonte única do conhecimento por etapa)
    rules.py              # Seleção/eligibilidade, transições, idempotência, is_stale, retry
  application/
    ports.py              # Protocols: NotionReader, NotionWriter, AgentRunner, Clock, RoundLock
    run_round.py          # Rodada: lock, preflight, seleção, loop de cards, log JSON
    process_card.py       # Ciclo do card: ⏳ → registro 📝 → agente → validar → escrever → mover
  adapters/
    notion_api.py         # Único arquivo que conhece a API do Notion (inclui endpoints markdown)
    claude_cli.py         # Único arquivo que sabe o que é stream-json e as flags do CLI
    prompts_fs.py         # Carrega prompts/*.md
    logging_fs.py         # Eventos JSON locais + rastro do agente
    lock_fs.py            # Lock de rodada (fcntl/flock) com try/finally
  cli.py                  # typer: run | verify
  config.py               # pydantic-settings (.env, permissão verificada)
prompts/
  refine.md               # Prompt versionado da etapa Refine (RNF-M4)
.mcp.json                 # MCPs da Z.ai (web_search_prime, web_reader)
tests/
  unit/                   # domain + application com fakes dos ports
  integration/            # adapters contra respostas gravadas (sem rede)
```

**Structure Decision**: estrutura única (single project), espelhando a seção 4 do design doc — hexagonal com `domain` puro, `application` declarando ports, `adapters` implementando. `tests/` fora de `src/` seguindo o design doc.

## Complexity Tracking

> Nenhuma violação de constituição a justificar. A única divergência de ADR (intervalo 5 min) é decisão a registrar no novo ADR-007, não complexidade adicional injustificada.
