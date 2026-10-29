---
title: Instalar e atualizar
description: Instale o Cortex com uv ou pip, rode cortex-claude setup para ligar ao Claude Code, e atualize ou configure na mão.
---

# Instalar e atualizar

O Cortex precisa de **Python 3.11 a 3.13**. Ele depende do spaCy e do PyTorch, que não têm wheels para todo Python, então o jeito mais fácil é o [uv](https://docs.astral.sh/uv/), que traz um Python compatível próprio.

## Instalar

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install "cortex-claude[code]" --python 3.12
cortex-claude setup
```

O extra `[code]` adiciona os parsers tree-sitter do [grafo de código](./code-graph). Sem ele, todo o resto funciona.

Depois reinicie o Claude Code. O Cortex funciona em todo projeto; não tem nada para configurar por projeto.

### O que o setup faz

O `cortex-claude setup` mostra uma linha de ok ou falha para cada etapa, e pode rodar de novo sem problema se algo falhou (um download de modelo barrado por um proxy, por exemplo):

1. Cria a pasta de dados, `~/.cortex-claude`.
2. Instala os [hooks](./capture) e registra no `~/.claude/settings.json`.
3. Registra o servidor MCP como `cortex` no `~/.claude.json`, para todos os projetos.
4. Adiciona uma seção do Cortex no `~/.claude/CLAUDE.md` (ou cria o arquivo), dizendo ao Claude para usar a memória.
5. Baixa o modelo de embedding (uns 80 MB) e o modelo do spaCy (uns 12 MB).
6. Sobe o daemon em segundo plano.

## Extras opcionais

| Extra | Adiciona |
| --- | --- |
| `code` | O grafo de código (parsers tree-sitter para Python, JavaScript, TypeScript, Go, Java, Swift, Kotlin) |
| `claude` | A extração de fatos com ajuda do Claude, desligada por padrão (veja [Privacidade](./privacy#extracao-com-ajuda-do-claude)) |

Dá para juntar: `uv tool install "cortex-claude[code,claude]" --python 3.12`.

## Atualizar

O `uv tool install` não faz nada se o Cortex já está instalado. Para pegar uma versão nova:

```sh
uv tool upgrade cortex-claude
cortex-claude setup
```

## Com pip

```sh
pip install "cortex-claude[code]" && cortex-claude setup
```

Use um Python entre 3.11 e 3.13. A maioria dos erros de instalação vem de um Python do sistema mais novo ou de um `pip` sem wheels do spaCy e do PyTorch; o uv evita os dois.

## Configuração MCP na mão

Para ligar o Cortex só num projeto, coloque um `.mcp.json` na raiz dele, apontando para o comando instalado (`which cortex-claude`):

```json
{
  "mcpServers": {
    "cortex": {
      "type": "stdio",
      "command": "cortex-claude",
      "args": []
    }
  }
}
```

## Comandos

| Comando | Faz |
| --- | --- |
| `cortex-claude` | Roda o servidor MCP (o Claude Code que inicia) |
| `cortex-claude setup` | Instala ou conserta a integração |
| `cortex-claude daemon` | Roda o daemon em segundo plano |
| `cortex-claude web [porta]` | Abre o [dashboard](./dashboard), na porta 37800 por padrão |

## Onde ficam os dados

Tudo fica em `~/.cortex-claude`: os bancos (um por [escopo](./scopes)), a configuração e os hooks. Defina `CORTEX_HOME` para usar outra pasta.
