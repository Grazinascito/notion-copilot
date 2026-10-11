# Contrato — Saída do agente (etapa Refine)

O agente (Claude Code CLI) recebe o prompt versionado (`prompts/refine.md`) já montado pelo orquestrador com **todo** o conteúdo do card (título, propriedades, corpo) — ele não tem nenhuma ferramenta de leitura do Notion (FR-008). A página do card nasce com o esqueleto da seção de refinamento (template do banco — research R1); por isso o agente devolve **apenas os corpos das seções**, nunca headings. A saída é um JSON validado com Pydantic na fronteira do orquestrador.

## Formato

```json
{
  "title": "Ligar para a Estácio sobre bolsa do curso",
  "sections": {
    "contexto": "**Síntese.** ...\n- **Fato:** ... Fonte: [link]\n- **Hipótese:** ...",
    "links_guardados": "- [Nome](url) — por que importa",
    "acoes_sugeridas": "- [ ] ...",
    "o_que_ja_adiantei": "...",
    "perguntas_abertas": "...",
    "prompt_sugerido": "...",
    "executor_sugerido": "Humano — ..."
  },
  "blocking_questions": [],
  "executor_suggestion": "HUMANO"
}
```

## Regras

| Campo | Regra | FR |
|---|---|---|
| `title` | String não vazia, ≤ 80 chars. Pode igualar o original ("título já bom") | FR-010 |
| `sections` | As 7 chaves são obrigatórias (`contexto`, `links_guardados`, `acoes_sugeridas`, `o_que_ja_adiantei`, `perguntas_abertas`, `prompt_sugerido`, `executor_sugerido`). Cada valor é o corpo da seção correspondente do template da página (headings `### Contexto` … `### Executor sugerido` já existem) | FR-010 |
| Fatos vs. hipóteses | Todo fato verificado cita fonte com link; fato sem fonte marcado como **Hipótese** | FR-010, ADR-005 |
| `blocking_questions` | Lista (possivelmente vazia) de perguntas que só a usuária responde. Não vazio → card termina ❓ | FR-012 |
| `executor_suggestion` | `"HUMANO"` ou `"IA"` — alimenta a propriedade Executor (só se vier vazia); o texto exibido na seção vem em `sections.executor_sugerido` | FR-010 |
| Markdown permitido nos corpos | Parágrafo, bulleted/numbered list, to-do `- [ ]`, quote, **bold**, *itálico*, `código`, [links] — suportados nativamente pelo endpoint markdown da API do Notion (research R1). **Headings são proibidos nos corpos**: os headings vêm do template, e um heading dentro do corpo criaria casamento ambíguo no `old_str` do `update_content` | — |

## Tratamento de violação

- JSON inválido / fora do schema Pydantic → **erro permanente** do card (sem retry — research R8): ⚠️ + comentário com a saída do erro no corpo do comentário (FR-013/FR-014).
- O agente nunca escreve no Notion: quem preenche as seções, grava título, propriedades e comentários é o orquestrador (FR-009, constituição III).
- A decisão "bloqueante ou não" é do **código** (lista explícita), não de interpretação de texto (constituição I).
