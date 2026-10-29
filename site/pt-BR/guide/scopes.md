---
title: Escopos
description: Os escopos do Cortex deixam a memória global, por projeto ou com os seus próprios limites. Ligue pastas a escopos, defina a ordem de busca e gerencie com o cortex_scopes.
---

# Escopos

Um **escopo** é uma memória separada. Por padrão existe um, o `global`, dividido por todos os projetos.

## Escopos de projeto

Ligue uma pasta a um escopo próprio e o que você salva trabalhando ali fica ali:

```json
{
  "scopes": {
    "mappings": {
      "/Users/eu/trabalho/loja": "project:loja",
      "/Users/eu/trabalho/api": "project:api"
    },
    "default": "global",
    "search_order": "project_first"
  }
}
```

Com `project_first`, o recall procura primeiro no escopo do projeto e depois no global, então os detalhes do projeto ganham e o conhecimento geral continua aparecendo.

O [grafo de código](./code-graph) de um projeto sem ligação vai para um escopo automático `project:<nome-da-pasta>`, então o código nunca enche a memória global.

## Gerenciando escopos

Peça ao Claude, que usa o `cortex_scopes`:

| Ação | Faz |
| --- | --- |
| `list` | Todos os escopos |
| `info` | Os detalhes de um |
| `create` | Um escopo novo |
| `delete` | Apaga um escopo e a memória dele |
| `link` | Liga uma pasta a um escopo |
| `unlink` | Tira a ligação de uma pasta |

O `cortex_status` mostra a contagem de memórias e fatos e o espaço de cada escopo.
