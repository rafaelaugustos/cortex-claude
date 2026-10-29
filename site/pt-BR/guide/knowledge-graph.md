---
title: O grafo de conhecimento
description: Como o Cortex transforma memórias em fatos de sujeito, relação e objeto com spaCy e padrões, normaliza entidades, junta fatos, acompanha tempo e confiança, e anda pelas ligações.
---

# O grafo de conhecimento

Toda memória é quebrada em **fatos**: um sujeito, uma relação e um objeto.

<div class="facts">
  <Fact s="api" p="uses" o="rate limiting" />
  <Fact s="auth service" p="uses" o="jwt tokens" />
  <Fact s="refresh tokens" p="stored_in" o="httponly cookies" />
</div>

Os fatos são a camada mais barata do [recall](./how-it-works): poucos tokens cada, e muitas vezes tudo o que o Claude precisa.

## Extração

Três métodos juntos:

1. **NLP do spaCy:** análise de dependências, entidades nomeadas, voz passiva, listas ligadas por "e".
2. **Padrões:** listas com marcador (`- X for Y`), `chave: valor`, listas com vírgula, barras (`React/TypeScript`), parênteses (`FastAPI (Python)`).
3. **Claude**, opcional e desligado por padrão: quando a extração local acha menos de dois fatos confiáveis, ela pode perguntar ao Claude Haiku. Veja [Privacidade](./privacy#extracao-com-ajuda-do-claude).

Inglês e português são detectados sozinhos. Espanhol, alemão e francês funcionam com os modelos do spaCy deles instalados.

## Entidades

Os nomes são normalizados para a mesma coisa ser uma entidade só: `postgres`, `PostgreSQL` e `pg` viram `postgresql`; `js` vira `javascript`; `k8s` vira `kubernetes`.

## Fatos que amadurecem

- **Junção:** quando várias memórias dizem o mesmo fato, ele vira um fato só, com mais confiança.
- **Confiança:** os fatos ganham confiança quando são usados e perdem quando uma informação mais nova contradiz.
- **Tempo:** os fatos percebem quando algo aconteceu ("em abril de 2024", "ontem", "desde a v2") e guardam a data.

## Andando pelo grafo

O `cortex_traverse` segue as ligações por vários saltos:

```text
auth → jwt → express-jwt → middleware
  ↓
  httponly cookies
```

Pergunte ao Claude *"o que está ligado ao auth?"* e ele pode achar coisas que você nunca perguntou direto. Comece de um [cluster](./clusters) com `start="cluster:42"`.
