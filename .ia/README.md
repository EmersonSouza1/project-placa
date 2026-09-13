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

Para começar a contribuir, leia [AGENTS.md](../AGENTS.md). Para subir rapidamente
a simulação, consulte o [README principal](../README.md).

## Como manter esta documentação

- Descreva o comportamento observado no código; marque propostas e pendências.
- Ao mudar uma regra, atualize também seu contrato, testes e impactos operacionais.
- Registre a data e o alcance das validações; resultados antigos não comprovam
  alterações posteriores.
- Prefira links relativos para arquivos do repositório e exemplos sem segredos.

Base inicial: implementação revisada em **12/09/2026**.

