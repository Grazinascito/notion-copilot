# Notion Copilot — Documento de Produto

> Agente de software que refina, planeja e executa tarefas registradas no LifeOS (inbox db), para que registros capturados às pressas virem trabalho encaminhado sem eu precisar reescrever cada um à mão.

---

## 1. Resumo executivo

Estou construindo um agente de software que refina, planeja e executa tarefas registradas no LifeOS - inbox db, para que registros capturados às pressas virem trabalho encaminhado sem eu precisar reescrever cada um à mão.

Hoje 53 dos 58 cards em BACKLOG estão parados há mais de 7 dias, e o mais antigo tem 66 dias. A meta é que nenhum card fique parado mais de 7 dias, e que eu consiga explicar cada peça do código para outra pessoa, porque o projeto também é portfólio e vai ser publicado.

A versão 1 funciona de ponta a ponta, mas o desenho interno do código tem 35 problemas catalogados. A v2 é uma reescrita do zero, com o escopo ampliado para incluir acesso ao meu workspace do Notion.

### Resumo em 30 segundos

- **Problema:** a captura no inbox funciona, mas não existe um processo consistente para esclarecer, priorizar, encaminhar e revisar os registros. Itens ficam parados, inclusive os que uma IA poderia fazer (pesquisa, organização, documentação, código).
- **Objetivo:** um board no Notion em que mover um card dispara a IA para refinar, planejar ou executar a tarefa. O resultado volta para a página da própria tarefa, e eu mantenho o controle de prioridades e decisões.
- **Restrição:** usar os tokens do plano GLM Coding Pro (trimestral). Sem custo adicional com Notion Custom Agents, Claude agents do Notion ou outro serviço.

---

## 2. Problema

### 2.1 Quem tem o problema

Eu, Grazi, dona do workspace grazinascitoLifeOS. E pode ser usado por outras pessoas no futuro.

### 2.2 Qual é o problema

A captura no inbox funciona: eu registro qualquer coisa em segundos. O que não funciona é o passo seguinte. Cada card capturado precisa ser esclarecido antes de virar ação: entender o que eu quis dizer, pesquisar o que falta, decidir o próximo passo. Esse trabalho é manual, demora, e por isso não acontece.

Uma parte desse trabalho não precisa de mim. Pesquisar um medicamento, achar links de compra, escrever um rascunho de mensagem e organizar um recurso são tarefas que um agente de software faz.

### 2.3 Por que isso dói

- Tarefas com prazo real (comprar, contatar alguém, pesquisar antes de uma consulta) perdem a janela útil.
- O inbox cresce e deixa de ser confiável. Quando a lista é grande demais para revisar, eu paro de abrir a lista.
- O esforço de esclarecer é maior que o esforço de capturar, então a fila só cresce.

---

## 3. Quem usa

Não invento personas. Existem duas pessoas, descritas pelo que precisam fazer.

### 3.1 Usuária primária: eu

| O que preciso fazer | Como faço hoje |
|---|---|
| Capturar sem pensar | Já funciona. Crio o card no inbox em segundos |
| Decidir o que é prioridade | Eu movo o card de coluna. Continua comigo, não passa para a IA |
| Esclarecer o que o card quis dizer | Manual. É o gargalo |
| Aprovar antes de qualquer coisa importante | Hoje não existe ponto de aprovação explícito |
| Entender o que o agente fez e por quê | Hoje só vejo "rodando" e o resultado final |

**Conhecimento técnico:** tenho experiência com frontend (React e Flutter) e entendo boas práticas de engenharia. Não domino Python, e este projeto é também como eu aprendo arquitetura de software na prática.

### 3.2 Usuária secundária: quem clonar o repositório

Uma pessoa que vê o projeto no LinkedIn e quer usar no próprio workspace. Ela precisa:

- Entender em menos de cinco minutos o que o agente faz, lendo o README.
- Instalar sem me perguntar nada.
- Criar o banco com as propriedades certas, sem montar à mão.
- Usar as próprias credenciais, sem nenhum segredo meu no repositório.
- Rodar no computador dela, que pode ser Linux.

> 🔵 **Pergunta fechada:** essa pessoa precisa ter o plano GLM Coding Pro, ou o modelo vira configurável?
> **Resposta:** modelo configurável pela pessoa, basta usar a API key.

---

## 4. Decisões de arquitetura

### 4.1 Os três papéis (não confundir)

- **Modelo:** interpreta e escreve. Aqui é o GLM.
- **Agente:** programa que usa ferramentas e age. Aqui é o Claude Code.
- **Evento/gatilho:** a decidir.

### 4.2 Tabela de decisões

| Tema | Decisão | Motivo |
|---|---|---|
| Modelo | GLM (GLM-5.3 e GLM-5.3-Flash), pelo GLM Coding Pro | Muitos tokens disponíveis, sem custo extra |
| Agente (quem usa ferramentas) | Claude Code CLI configurado com o endpoint da Z.ai `https://api.z.ai/api/anthropic`. Não precisa de assinatura da Anthropic | É ferramenta oficialmente suportada pelo Coding Plan e já traz o ciclo de agente pronto |
| Gatilho (quem inicia o trabalho) | Algo que rode a cada ~X min, que consulta o Notion (polling). Cron job seria útil aqui? Qual opção compensa mais? | Não sei |
| Leitura e escrita no Notion | MCP do Notion ou API do Notion? Obs.: futuramente quero que o agente tenha múltiplos MCP (GitHub, email, Figma), então MCP vai ter; o ponto é saber quando usar em relação à API | Não sei |
| Busca na web | O agente vai ser capaz de fazer pesquisas e trazer o resultado no próprio card (página Notion); também vai poder acessar link de vídeo e imagem, mas isso é no futuro, não entra agora | Não sei |
| Escopo do piloto | Acesso a todo meu workspace: leitura, edição, adição (deleção não entra agora) | — |
| Escrita do resultado | API ou MCP? Obs.: a API já aceita markdown, então não é preciso converter para blocos | — |
| Instalação do Claude Code | Instalador nativo (`~/.local/bin/claude`), sem nvm | — |
| Volume de cards | Quando as páginas estiverem na raia de "To Refine" no Notion. Teremos no máximo 5 itens por rodada no job na fila daquela coluna (aqui vamos lidar com queue, né ou não?) | — |
| Nome do programa | `notion-copilot` | — |

---

## 5. Modelo de dados no Notion

### 5.1 Propriedades do banco

- **Pipeline** (select): Backlog · To Refine · Refined · Plan · Human execute · AI execute · Review · Done · Archived (Q2). Archived não aciona a IA.
- **Executor** (select): Humano · IA.
- **IA status** (select, mudança M1): ⏳ rodando · ❓ precisa de você · ⚠️ erro. Vazio significa ok.
- **IA atualizado em** (data com horário).
- **Avaliação** (select): 👍 · 👎.

### 5.2 Migração dos itens existentes

- Status `TODO` e `IN PROGRESS` → Pipeline **Backlog**.
- Status `DONE` → **Done**.
- Status `ARCHIVED` → **Archived**.

### 5.3 Board

- O board "By Type" passa a agrupar por **Pipeline** e mostra no card: Name, IA status, Executor.
- **Comportamento preservado:** Type, Area, Details, Due Date e os templates recorrentes continuam iguais. A propriedade Status fica no banco até o fim do piloto, sem uso pelo programa.

---

## 6. Workflow (pipeline)

⚡ = coluna que aciona a IA.

| Coluna | Quem age | O que acontece | Próxima coluna |
|---|---|---|---|
| Backlog | Eu | Captura do registro original | Eu movo para To Refine |
| To Refine ⚡ | IA | Cria descrição com o contexto, melhora o título, guarda os links, adianta tudo o que der (pesquisa, rascunhos, links de compra), deixa perguntas abertas e próximos passos e sugere o Executor | Refined |
| Refined | Eu | Decido quem faz (Executor = Humano ou IA) e se precisa de plano | Plan, Human execute ou AI execute |
| Plan ⚡ | IA | Monta o plano a partir do refinamento | Human execute ou AI execute, conforme o Executor. Sem Executor ou com pergunta aberta (❓): Refined |
| Human execute | Eu | Faço a tarefa | Review ou Done |
| AI execute ⚡ | IA | Executa as instruções da página | Review |
| Review | Eu | Aprovo, ou escrevo um ajuste e devolvo para AI execute | Done |
| Done | — | — | — |

---

## 7. Autonomia e aprovação

### 7.3 Autonomia: o que o agente faz sozinho

| Ação | Precisa da minha aprovação? |
|---|---|
| Pesquisar na web | Não |
| Escrever o resultado dentro da página do card | Não |
| Reescrever o título do card | Não. O registro original fica preservado em um bloco que nunca é editado |
| Mover o card para a próxima coluna | Não. É o mecanismo do pipeline |
| Preencher Executor, Type e Area | Não, desde que estejam vazios. Nunca sobrescreve valor que eu escrevi |
| Criar página nova em outro banco | Sim |
| Editar página que já existe fora do inbox | Sim |
| Apagar qualquer coisa | Sempre. O agente nunca apaga por conta própria |
| Enviar email, mesmo para mim | Não se aplica: está fora da v2 |

### 7.4 Como a aprovação funciona

A aprovação acontece depois do Plan, antes da execução. A declaração do que o agente pretende fazer é saída da etapa Plan, não do Refine. Motivo: o Refine descobre e organiza o problema. O Plan é que define os passos concretos, e só com os passos na mão eu consigo aprovar ou recusar.

1. O **Refine** organiza o card: contexto, links, ações sugeridas, perguntas abertas e Executor sugerido.
2. O **Plan** escreve os passos e declara, por escrito, o que o agente vai fazer na execução. Exemplo do que precisa aparecer: "vou criar uma página nova na Resource library".
3. Se algum passo exige aprovação pela tabela 7.3, o card fica marcado como **aguardando confirmação** e o agente para.
4. Eu leio o plano, marco como aprovado e movo o card para a raia de execução.
5. O agente executa na rodada seguinte.
6. O resultado vai para **Review**. Nada é concluído sem eu revisar.

Se nenhum passo exige aprovação, o card segue o fluxo normal e eu só reviso o resultado.

**Consequência desta regra:** todo card que a IA vai executar passa pelo Plan. O caminho Refined → AI execute, sem passar por Plan, deixa de existir, porque é no Plan que o agente declara o que vai fazer.

---

## 8. Contrato de cada etapa

| Etapa | Entrada | Saída escrita na página | Próximo estado |
|---|---|---|---|
| Refine | Título, propriedades, corpo da página | `## 🔍 Refinamento:` Contexto (síntese) · Links guardados · Ações sugeridas · O que já adiantei · Perguntas abertas · Prompt sugerido para a IA executar · Executor sugerido. Mais um novo título curto | Refined (IA status vazio ou ❓) |
| Plan | Página com Refinamento e respostas | `## 🗺️ Plano:` passos, critérios de pronto, riscos | Human execute ou AI execute |
| Execute | Página com Refinamento, Plano e Ajustes | `## ✅ Resultado:` achados com fontes, rascunhos, entregáveis | Review |

**Editar o workspace:** criar e editar itens, notas e projetos em outros bancos (pergunta Q5 da Sessão 1). É uma ação que dá para desfazer: a IA faz no AI execute e você revisa no Review.

---

## 9. Regras de segurança e comportamento

- **Dúvidas e falhas:** em vez de colunas extras, usamos o IA status ❓ (precisa de você) ou ⚠️ (erro), visíveis no card.
- **Registro original preservado:** antes de reescrever o título, o script copia o texto original para um bloco "📝 Registro original", que nunca é editado.
- **Proatividade só no que dá para desfazer:** a IA pode pesquisar, rascunhar e juntar links, escrevendo só na página. Nunca envia mensagem nem compra nada. Suposições aparecem marcadas como "Hipótese".
- **Não inventar requisitos:** separar Fatos (o que está no registro), Hipóteses e Perguntas.

---

## 10. Exemplo-ouro (7.6)

Refinamento real já produzido por um agente em outro experimento:

> ✅ O texto abaixo é saída real do agente da v1, gravada em 02/10/2026 no card "Ligar para a Estácio sobre bolsa do curso". Nada aqui foi escrito nesta conversa. Este é o nível de qualidade que a v2 precisa igualar ou superar.

**Entrada:** uma frase, escrita na captura. "ligar pra estacio pra saber como pegar bolsa do curso". Sem link, sem detalhe, sem contexto.

**Saída real** (reproduzida com corte nos trechos repetitivos, marcados com …):

## 🔍 Refinamento — 02/10/2026 11:25

**Contexto.** Você quer ligar para a Estácio para descobrir como conseguir bolsa no seu curso. Já encontrei os telefones oficiais e as principais bolsas disponíveis.

- **Fato:** canais oficiais da Estácio: 4003-6767 (capitais e regiões metropolitanas), 0800 880 6767 (demais regiões) e WhatsApp (21) 98390-8414. Fonte: página de atendimento da Estácio.
- **Hipótese:** "o curso" é uma graduação da Estácio. Não sei se você já é aluno ou quer entrar.

**Links guardados.** Bolsas e financiamentos na Estácio (página oficial) · Canais de atendimento · Blog Estácio: 6 alternativas de bolsa.

**Ações sugeridas.**

- [ ] Reunir os dados antes de ligar: nome do curso, modalidade, CPF, nota do ENEM e número de matrícula.
- [ ] Ligar para 4003-6767 ou 0800 880 6767. Alternativa: WhatsApp.
- [ ] Seguir o roteiro de perguntas abaixo.
- [ ] Anotar percentual de bolsa, documentos, prazo e número de protocolo.

**O que já adiantei.** Fonte: página oficial de bolsas da Estácio.

- ProUni: bolsa de 50% ou 100%. Exige ENEM com média mínima de 450 e renda familiar por pessoa de até 1,5 salário mínimo (integral) ou 3 (parcial).
- FIES: juros reais zero para renda por pessoa de até 3 salários mínimos.
- Bolsa ENEM da própria Estácio: até 70% nas mensalidades, aceita qualquer edição do ENEM.
- … mais três opções, com a ressalva de que os percentuais variam por curso, modalidade e unidade.

**Roteiro para a ligação.** Texto pronto para ler ao telefone, com identificação, cinco perguntas numeradas (quais bolsas valem, em quais eu me encaixo, documentos, prazo, onde pedir) e o pedido do número de protocolo.

**Perguntas abertas.** 1. Você já é aluno da Estácio ou quer entrar agora? 2. Qual é o curso e a modalidade?

**Executor sugerido.** Humano — a ligação precisa da sua voz e dos seus dados pessoais; a IA não pode telefonar.
