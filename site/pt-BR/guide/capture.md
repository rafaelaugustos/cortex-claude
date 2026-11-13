---
title: Aprendizado e contexto automático
description: Memória compartilhada com significado, experiências verificadas, condições, validade e medição de tarefas.
---

# Aprendizado e contexto automático

O Cortex mantém uma memória compartilhada com a origem de cada observação. Três sessões independentes consolidam uma preferência pessoal. Experiências transferíveis também precisam de duas origens. Fatos contextuais continuam ligados à origem; instruções permanentes explícitas podem valer imediatamente. Ler ou reenviar uma memória nunca conta como confirmação.

## Entendimento das observações

Preferências diretas em português/inglês são extraídas localmente. Um modelo multilíngue residente compara paráfrases e recupera ideias relacionadas. Negação, valores opostos, números, identificadores técnicos, origem e condições limitam a consolidação; casos ambíguos permanecem separados. É uma heurística conservadora. O Claude interpreta situações mais sutis por `cortex_learn` durante o trabalho, sem uma chamada extra de IA por mensagem.

Execute `cortex-claude learning prepare` uma vez para baixar o modelo. O daemon carrega o cache offline. Os hooks pedem vetores pelo socket local, com limite de 250 ms; se o serviço estiver indisponível, a busca por palavras continua. `learning status` mostra disponibilidade e quantidade indexada. O modelo padrão ocupa aproximadamente 470 MB em disco e usa RAM enquanto está carregado.

## Experiências verificadas

`cortex_learn action="experience"` registra uma conclusão curta e um objeto `experience` com `situation`, `cause` e `solution`. Sem validação, a experiência fica fora da recuperação. Para validar, informe um `verification_id` aprovado de `action="status"`, ou `"latest"` quando o teste mais recente realmente verificar aquela solução. O comprovante deve pertencer à sessão/origem atual e ter no máximo uma hora.

São reconhecidos comandos Bash de pytest, unittest, npm/pnpm/yarn test, jest/vitest, cargo test e go test, com conclusão bem-sucedida e resumo reconhecido. Falhas mascaradas, ajuda e executores desconhecidos não bastam. O Cortex nunca executa um comando lembrado. Cabe ao Claude associar o teste correto à solução: um teste aprovado só comprova o que cobre.

Após uma nova aplicação, `action="outcome"` registra `passed` com comprovante ou `failed`. Somente sucessos independentes confirmam a experiência. Uma falha suspende o reaproveitamento até nova validação.

## Condições e validade

`conditions` aceita listas `all`, `any` e `none` com termos da tarefa. Exemplo: `{"any":["architecture","debugging"],"none":["email"]}` limita uma preferência por respostas detalhadas. A regra específica prevalece sobre a geral do mesmo assunto quando as condições combinam. As condições usam termos normalizados; exceções complexas precisam ser interpretadas pelo Claude.

`dependencies` lista até 20 arquivos relativos acompanhados, de no máximo 2 MB cada, dentro do repositório de origem. Arquivos alterados ou ausentes suspendem a memória. Inclua manifesto/lockfile para acompanhar versões; arquivos e versões não listados não são inferidos automaticamente. Experiências expiram em 90 dias por padrão; preferências podem informar `max_age_days`. A revalidação é explícita e deve acontecer após a mudança nos arquivos.

## Hooks

O setup preserva hooks de outras ferramentas e instala:

- **SessionStart:** registra a sessão, reinicia recibos após compactação e inicia daemon/indexação. Não despeja contexto aleatório.
- **UserPromptSubmit:** observa preferências diretas e entrega conclusões relevantes e compactas.
- **PostToolUse:** registra comprovantes de teste e indexa arquivos; arquivamento bruto vem desativado.
- **PostToolUseFailure:** registra falhas de testes reconhecidos.
- **Stop:** lê contadores do provedor no histórico principal, em segundo plano, sem guardar o texto.

Trechos privados são removidos antes de qualquer corte. O antigo hook que reescrevia comandos é removido. Veja [Privacidade](./privacy).

Os hooks aceitam documentos JSON UTF-8 completos de até 8 MiB (8.388.608 bytes). Eventos maiores são recusados explicitamente antes da análise ou entrada na fila; não são salvos e não podem ser recuperados por nova tentativa na fila. Eventos aceitos são normalizados antes da gravação, sem salvar a saída bruta das ferramentas como conhecimento. O diagnóstico registra a etapa, o tipo da exceção e a quantidade de bytes, sem o conteúdo da entrada; o painel Saúde distingue entrada grande demais de JSON inválido.

## Controle de tokens

Padrões: até 180 tokens estimados por mensagem, reduzidos a 96 em consultas curtas ou com correspondência fraca, cinco notas e 600 tokens por sessão. O envelope inteiro conta. Detalhes via `cortex_learn action="read"` compartilham o limite da sessão e são entregues uma vez. Informe a `query` atual para verificar condições. A compactação reinicia os recibos de entrega.

```json
{"learning":{"enabled":true,"confirmations":3,"min_contexts":2,"max_context_tokens":180,"max_session_tokens":600,"max_detail_tokens":600,"semantic_enabled":true,"semantic_timeout_ms":250,"experience_ttl_days":90,"measure_usage":true,"capture_tools":false}}
```

## Inspeção e avaliação

O painel mostra conclusões, evidências, condições, comandos de verificação, memórias pendentes, estimativas de contexto e contadores de entrada/saída/cache do provedor. Esses contadores cobrem o histórico principal, sem inferir consumo de subagentes nem limites da assinatura. Mensagens repetidas ou atualizadas por streaming são deduplicadas. Arquivos antigos permanecem disponíveis e não viram preferências automaticamente.

```bash
cortex-claude learning status
cortex-claude learning list
cortex-claude learning context "Explique a arquitetura"
```

No checkout:

```bash
uv run python scripts/evaluate_learning.py
uv run python scripts/evaluate_semantic.py --output /tmp/semantic.json
uv run python scripts/evaluate_tasks.py --output /tmp/tasks-offline.json
# Opcional: usa sua conta Claude, com limite por execução.
uv run python scripts/evaluate_tasks.py --live --repeats 2 --budget 0.40 --output /tmp/tasks.json
```

A avaliação online usa projetos sintéticos isolados, os mesmos modelos/ferramentas, ordem alternada e testes independentes do código produzido. Registra tokens, cache, tempo, falhas e qualidade. Pode mostrar aumento ou redução; poucas amostras não garantem economia. `learning record-run run.json` importa uma execução medida para o painel. A avaliação offline não inventa consumo do provedor.

Atualize com `cortex-claude setup --hooks-only` e reinicie o Claude Code. O setup faz backup das configurações alteradas e preserva hooks de outras ferramentas.
