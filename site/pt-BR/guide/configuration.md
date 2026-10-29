---
title: Configuração
description: Todos os ajustes do Cortex no ~/.cortex-claude/config.json - recall, modelos de embedding, extração de fatos, decaimento, deduplicação, escopos, clusters e armazenamento.
---

# Configuração

O Cortex lê o `~/.cortex-claude/config.json`. Todo campo é opcional; o que você deixar de fora usa o padrão. A pasta [`examples/`](https://github.com/rafaelaugustos/cortex-claude/tree/main/examples) do repositório tem arquivos prontos.

```json
{
  "recall": {
    "default_max_tokens": 200,
    "default_depth": "auto",
    "sufficiency": {
      "coverage_threshold": 0.7,
      "confidence_threshold": 0.6
    }
  },
  "embeddings": {
    "model": "all-MiniLM-L6-v2",
    "batch_size": 32
  },
  "facts": {
    "extraction_method": "local",
    "min_confidence": 0.5,
    "claude_fallback": false,
    "claude_confidence_threshold": 0.5
  },
  "decay": {
    "lambda": 0.05,
    "recalculate_interval_hours": 6,
    "min_score": 0.01
  },
  "deduplication": {
    "similarity_threshold": 0.92,
    "merge_strategy": "append"
  },
  "scopes": {
    "mappings": {},
    "default": "global",
    "search_order": "project_first"
  },
  "storage": {
    "max_db_size_mb": 500
  }
}
```

## Recall

`default_max_tokens` e `default_depth` valem quando o Claude não passa esses valores. Os limites de `sufficiency` decidem quando uma camada responde bem o bastante para parar; aumente e o recall vai mais fundo com mais frequência.

## Embeddings

O modelo usado na busca por significado. O padrão é rápido e pequeno; os maiores entendem mais e gastam mais memória.

| Modelo | Tamanho | |
| --- | --- | --- |
| `all-MiniLM-L6-v2` | 384 dimensões, 80 MB | Rápido (padrão) |
| `BAAI/bge-small-en-v1.5` | 384 dimensões, 130 MB | Rápido |
| `all-mpnet-base-v2` | 768 dimensões, 420 MB | Médio |
| `BAAI/bge-base-en-v1.5` | 768 dimensões, 440 MB | Médio |
| `intfloat/multilingual-e5-small` | 384 dimensões, 470 MB | Multilíngue |
| `BAAI/bge-large-en-v1.5` | 1024 dimensões, 1,3 GB | Melhor qualidade |
| `intfloat/e5-large-v2` | 1024 dimensões, 1,3 GB | Melhor qualidade |

O Cortex descobre as dimensões sozinho.

## Fatos

`min_confidence` descarta fatos fracos. `claude_fallback` liga a [extração com ajuda do Claude](./privacy#extracao-com-ajuda-do-claude) quando a extração local acha pouco.

## Decaimento

O quanto memórias sem uso perdem força: `lambda` maior, perda mais rápida. Os scores são recalculados a cada `recalculate_interval_hours`. Veja [Como o recall funciona](./how-it-works#frescor).

## Deduplicação

Memórias mais parecidas que o `similarity_threshold` são juntadas.

## Escopos

As `mappings` de pasta para escopo, o escopo `default` e a `search_order`. Veja [Escopos](./scopes).

## Clusters

O `similarity_threshold` dos [clusters](./clusters) (0,70 por padrão).

## Armazenamento

`max_db_size_mb` limita o tamanho do banco.
