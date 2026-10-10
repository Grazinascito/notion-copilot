# Notion Copilot

Agente que opera um board de tarefas no Notion: lê cards, propõe planos, executa
trabalho com ferramentas de IA e grava resultados — com o orquestrador
determinístico controlando todas as escritas.

> Status: fase de especificação/design (sem código ainda).

## Documentação

- [Design Doc](docs/notion-copilot-design-doc.md)
- [ADRs](docs/notion-copilot-adrs.md)
- [Specs](specs/)

## Visão geral

- **Orquestrador** determinístico (regras, leitura/escrita no board via Notion API)
- **Agente** (Claude Code CLI + GLM via Z.ai) para trabalho que depende de linguagem
- **Segurança**: token do Notion somente leitura para o agente; escritas só pelo orquestrador
