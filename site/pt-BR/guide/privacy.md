---
title: Privacidade
description: O Cortex é local primeiro. SQLite, embeddings e NLP locais, tags private para manter segredos fora da memória, a extração opcional com o Claude e um dashboard preso ao localhost.
---

# Privacidade

O Cortex roda na sua máquina. Memórias, fatos, embeddings e o grafo de código ficam em SQLite, em `~/.cortex-claude`. Os embeddings e a extração de fatos rodam localmente. Não tem conta, serviço nem telemetria.

A rede é usada para baixar os modelos de embedding e do spaCy no setup, e mais nada, a não ser que você ligue a extração com ajuda do Claude.

## Tags private

Coloque o que você não quer lembrado entre tags `<private>`:

```text
A API usa JWT na autenticação. <private>API_KEY=sk-abc123secret</private> Os tokens expiram em 24h.
```

O Cortex tira tudo o que está entre as tags antes de salvar, nos salvamentos que você pede e na [captura automática](./capture). Se tudo for private, nada é salvo.

## Extração com ajuda do Claude

Desligada por padrão. Com o extra `claude` instalado, `claude_fallback: true` na [configuração](./configuration#fatos) e uma `ANTHROPIC_API_KEY` no ambiente, o Cortex manda o texto de uma memória para o Claude Haiku quando a extração local acha menos de dois fatos confiáveis. Esse texto vai então para a Anthropic, pela sua chave de API, e é cobrado nela.

## A memória que o Claude lê

O que o Cortex devolve entra no contexto do Claude Code e, dali, vai para o modelo como todo o resto da sessão. Manter o recall pequeno também é manter isso pequeno.

## O dashboard

O [dashboard](./dashboard) escuta só no localhost e confere o `Host` e o `Origin` de toda requisição, então outras páginas no seu navegador não conseguem ler nem mudar a sua memória.

## Esquecendo

Peça ao Claude para esquecer algo; ele mostra antes o que seria apagado (o `cortex_forget` roda como simulação por padrão). Para limpar em lote com prévia, use o dashboard.
