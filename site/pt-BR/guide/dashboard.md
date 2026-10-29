---
title: O dashboard
description: O dashboard web do Cortex no localhost - mapa de clusters, vizinhança das entidades, navegador de memórias, limpeza em lote com prévia e números ao vivo.
---

# O dashboard

```sh
cortex-claude web
```

Abre a sua memória em `http://localhost:37800` (passe outra porta como argumento).

O dashboard funciona do jeito que o recall funciona, a camada mais barata primeiro. Ele nunca desenha o grafo inteiro de uma vez, então continua rápido com dezenas de milhares de fatos.

## O que tem nele

- **Mapa de clusters:** a tela inicial mostra os seus [clusters](./clusters), do tamanho de quantas memórias eles têm. Abra um para ver o grafo dele e as memórias mais fortes.
- **Foco na entidade:** clique num nó para ver a vizinhança, os fatos e as memórias que falam dele.
- **Navegador de memórias:** busque, filtre por escopo e por tag, ordene por mais recente, relevância, último uso ou tamanho.
- **Limpeza em lote:** selecione por tag, escopo, cluster ou expressão regular e veja exatamente o que vai sair antes de qualquer coisa ser apagada. Apagar uma memória leva junto os fatos e o embedding dela.
- **Números ao vivo:** contagem de memórias e fatos, clusters, espaço, e um gráfico de 30 dias do que entrou, bom para achar o dia em que a captura automática desembestou.

## Segurança

O dashboard escuta só no localhost, não manda cabeçalhos de CORS e confere o `Host` e o `Origin` de toda requisição, então nenhuma outra página aberta no seu navegador consegue ler nem mudar a sua memória.
