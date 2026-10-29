---
title: The code graph
description: Cortex indexes functions, classes, calls and imports from Python, JavaScript, TypeScript, Go, Java, Swift and Kotlin into its graph, so Claude can look a symbol up instead of reading files.
---

# The code graph

With the `code` extra installed, Cortex parses your source with tree-sitter and stores the symbols as facts in the same graph as your memories:

<div class="facts">
  <Fact s="my_func" p="defined_in" o="app/jobs.py:42" />
  <Fact s="my_func" p="calls" o="other_func" />
  <Fact s="MyClass" p="extends" o="BaseClass" />
  <Fact s="sample" p="imports" o="json" />
</div>

**Languages:** Python, JavaScript, TypeScript and TSX, Go, Java, Swift and Kotlin.

## Looking a symbol up

`cortex_code(symbol)` returns where it is defined, what it calls, who calls it, what it extends and imports, and which memories mention it, in about 50 to 150 tokens. Reading the file to find the same thing costs a thousand or more.

## Keeping it indexed

- **At the start of a session** in a project Cortex has not indexed yet, the hook asks the daemon to index it in the background, up to 2,000 files. It happens once per project.
- **As Claude reads and edits** code files, they are indexed again, so the graph stays current.
- **By hand:** ask Claude to index a folder, which calls `cortex_index_code(path)`.

When a project has no [scope](./scopes) of its own, its code goes into an automatic `project:<folder-name>` scope instead of the global one.

## Decisions linked to code

When a saved memory mentions a symbol Cortex knows, it adds a `mentions` fact, linking the decision or bug report to the code it is about. `cortex_code` then shows that memory with the symbol.
