---
title: Como o recall funciona
description: Como o Cortex salva e recupera memórias. Embeddings, extração de fatos e resumos ao salvar, recall progressivo em três camadas, profundidade, busca híbrida, deduplicação e decaimento.
---

# Como o recall funciona

## Salvando

```text
conteúdo → embedding + extração de fatos + resumo → SQLite
```

Quando algo é salvo, o Cortex:

1. tira tudo o que estiver dentro de `<private>…</private>` (veja [Privacidade](./privacy));
2. calcula um embedding para a busca por significado;
3. extrai fatos para o [grafo de conhecimento](./knowledge-graph);
4. escreve um resumo, mais ou menos um quarto do original;
5. procura quase-duplicatas e junta (similaridade de cosseno acima de 0,92).

O [daemon](./capture#o-daemon) mantém o modelo de embedding carregado, então salvar leva uns 0,3 segundos em vez de cinco.

## Recuperando

```text
1. Fatos          poucos tokens cada   → bastou? para
2. Resumos        ~25% do original     → bastou? para
3. Texto inteiro  o original           → devolve
```

O `cortex_recall` começa pela camada mais barata e só vai adiante quando a resposta não está coberta. Na prática, a maioria das perguntas para nos fatos.

### Profundidade

| Profundidade | Devolve | Use para |
| --- | --- | --- |
| `auto` | Começa barato, vai adiante se precisar | A maioria das perguntas (o padrão) |
| `facts` | Só os trios do grafo de conhecimento | Consultas rápidas |
| `summaries` | Fatos e resumos | Algum detalhe |
| `full` | Tudo, inclusive o texto original | Quando os detalhes importam |

O `max_tokens` (200 por padrão) limita o quanto volta.

## Busca

O recall junta duas buscas:

- **similaridade de vetores**, pelo significado: "validade do token" acha "tempo de vida do JWT";
- **FTS5 do SQLite**, pelas palavras exatas: nomes, flags, códigos de erro.

## Frescor

Memórias que você nunca recupera perdem relevância com o tempo; as que você usa ganham:

```text
score = e^(-λ · dias) · (1 + log(acessos))
```

Os scores são recalculados quando o servidor sobe e a cada poucas horas. Ajuste o `λ` na [configuração](./configuration#decaimento).

## Sobre os números

As contagens de tokens são estimativas. O tokenizador do Claude não é público, então o Cortex conta com o `tiktoken` da OpenAI (`cl100k_base`) no lugar: perto o bastante para controlar o recall, não exato. Num benchmark pequeno, de 10 memórias, `facts` e `auto` devolveram 66% menos tokens que `full`. Rode você mesmo com `uv run python scripts/benchmark.py` num clone do repositório.
