# Documentação do projeto

Esta pasta reúne o contexto para desenvolvimento e manutenção da POC de
reconhecimento de placas e monitoramento de permanência em docas.

| Documento | Conteúdo |
|---|---|
| [Arquitetura](arquitetura.md) | Responsabilidades, fluxo de vídeo e entrega de eventos |
| [Regras de negócio](regras-de-negocio.md) | Vocabulário, transições, duração e consenso de placas |
| [Contrato da API](contrato-api.md) | Campos, validações, respostas e consultas |
| [Modelo de dados](modelo-de-dados.md) | Eventos, permanências, outbox e integridade |
| [Operação](operacao.md) | Configuração, execução, inspeção e diagnóstico |
| [Testes](testes.md) | Comandos, cenários, evidências e validação com vídeo |
| [Decisões e roadmap](decisoes-e-roadmap.md) | Escolhas atuais, limitações e evolução proposta |
| [Plano de implementação para o Codex](codex-implementation-plan.md) | Arquitetura alvo e fases para reduzir o custo computacional do pipeline |
| [Backlog do Codex](codex-tasks.md) | Tarefas incrementais, critérios de aceite e Definition of Done |
| [Prompt de handoff](codex-prompt.md) | Contexto pronto para iniciar uma nova sessão do Codex |

Para começar a contribuir, leia [AGENTS.md](../AGENTS.md). Para subir rapidamente
a simulação, consulte o [README principal](../README.md).

Para a próxima rodada de otimização do pipeline de visão, o Codex deve começar pelo
[plano de implementação](codex-implementation-plan.md), seguir o
[backlog](codex-tasks.md) em ordem e usar o [prompt de handoff](codex-prompt.md)
quando uma nova sessão precisar recuperar o contexto do projeto.

## Como manter esta documentação

- Descreva o comportamento observado no código; marque propostas e pendências.
- Ao mudar uma regra, atualize também seu contrato, testes e impactos operacionais.
- Registre a data e o alcance das validações; resultados antigos não comprovam
  alterações posteriores.
- Prefira links relativos para arquivos do repositório e exemplos sem segredos.
- Ao concluir uma tarefa do backlog do Codex, registre a evidência de validação e
  mantenha plano, backlog e documentação técnica coerentes com o código.

Base inicial: implementação revisada em **12/09/2026**.
