# Contrato — Comandos da CLI e scheduler

## `notion-copilot run`

Executa uma rodada (processo de vida curta). É o comando que o scheduler invoca.

```text
uv run notion-copilot run [--card <page_id|url>] [--dry-run]
```

| Flag | Efeito |
|---|---|
| (sem flags) | Rodada completa: lock → pré-flight → seleção (≤ 5 cards) → processa um a um |
| `--card` | Modo card único: processa só o card dado (bypass da seleção, sem varredura). Recusado se inelegível (`card_not_eligible`) |
| `--dry-run` | Executa pré-flight e seleção, lista o que faria, não escreve nada |

## `notion-copilot verify`

Pré-flight isolado (FR-002), sem processar cards. Verifica:

1. `.env` presente, permissão 600, campos obrigatórios (`NOTION_TOKEN`, `NOTION_DATABASE_ID`, `NOTION_USER_ID`, credencial do modelo — research R5);
2. token do Notion válido e com acesso (consulta de identidade `users.me` — sem gastar tokens de modelo);
3. banco existe e tem as propriedades esperadas (`Pipeline`, `Executor`, `IA status`, `IA atualizado em`) com as opções esperadas, e o template de página com o esqueleto 🔍 (research R1);
4. executável do agente presente (`claude --version`);
5. capabilities **Read content**, **Update content** e **Insert comments** habilitadas na integração (research R1/R6 — sem elas, leitura/escrita markdown e comentário falham com 403);
6. `prompts/refine.md` e `.mcp.json` presentes.

Saída: lista ✔/✘ com, para cada falha, **o que falta e como corrigir** (FR-002). Exit 0 se tudo ok.

## Exit codes de `run`

| Código | Significado |
|---|---|
| 0 | Rodada concluída (fila vazia conta como sucesso — edge case da spec) |
| 1 | Falha de pré-flight (mensagem diz o que falta) |
| 2 | Rodada já em execução (lock ocupado — FR-003) |
| 3 | Rodada executada com cards em erro (⚠️) — parcialmente bem-sucedida |

## Eventos (stdout/logs)

Uma linha JSON por evento (`ts`, `run_id`, `card_id?`, `stage`, `event`, `duration_s?`) — ver `data-model.md`. Nenhum segredo em qualquer saída (RNF-O5).

## Scheduler

- **macOS (launchd)**: plist com `StartInterval: 300`, `ProgramArguments: [<caminho-uv>, run, notion-copilot, run]` e `WorkingDirectory` = raiz do projeto (o default do launchd é `/`, o que quebraria `uv run` e caminhos relativos — research R4); documento de setup na feature.
- **Linux (cron)**: `*/5 * * * *` invocando o mesmo comando.

Intervalo de 5 min e proteção contra sobreposição: lock (research R3) + ⏳ nunca selecionado (FR-005).
