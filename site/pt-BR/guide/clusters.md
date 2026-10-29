---
title: Clusters
description: O Cortex agrupa memórias em clusters semânticos pela similaridade dos embeddings, dá nome a eles pelas entidades mais frequentes e deixa o Claude navegar pela memória de cima para baixo.
---

# Clusters

Conforme as memórias se acumulam, o Cortex junta as que falam da mesma coisa em **clusters**, pela similaridade dos embeddings. Cada cluster ganha um nome com as entidades que mais aparecem nos fatos dele, por exemplo `embeddings, vectors, sqlite-vec`.

Os clusters deixam o Claude, e você, navegar pela memória de cima para baixo: ver que assuntos existem e depois entrar num deles.

- O `cortex_clusters` lista os clusters, com quantas memórias cada um tem.
- O `cortex_traverse` com `start="cluster:42"` anda pelo grafo a partir de dentro de um.
- O [dashboard](./dashboard) abre num mapa deles.

## Quando atualizam

O agrupamento roda em segundo plano a cada 20 memórias salvas, no máximo uma vez a cada 5 minutos. Para reconstruir tudo (depois de mudar o limite, por exemplo), peça o `cortex_clusters` com `action="backfill"`.

## Ajustando

O `similarity_threshold` (0,70 por padrão) decide o quanto duas memórias precisam ser parecidas para dividir um cluster. Aumente para clusters mais fechados, diminua para ter menos memórias sozinhas. Veja [Configuração](./configuration).
