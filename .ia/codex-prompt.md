# Prompt de handoff para o Codex

Use o texto abaixo ao iniciar uma nova sessão do Codex neste repositório.

---

Você está trabalhando no repositório `project-placa`, uma POC de monitoramento de veículos em docas com reconhecimento opcional de placas.

Antes de alterar código:

1. leia `AGENTS.md`;
2. leia `.ia/README.md` e os documentos referenciados;
3. leia `.ia/codex-implementation-plan.md`;
4. leia `.ia/codex-tasks.md`;
5. inspecione o código atual relacionado à tarefa.

Objetivo técnico da próxima evolução: reduzir drasticamente o consumo de processamento do pipeline de visão. O sistema não deve executar detecção de placa e OCR continuamente. A direção arquitetural é usar frame sampling, filas limitadas, ROI, detecção leve de movimento, tracking, captura de placa orientada a evento, seleção do melhor frame e OCR somente quando necessário.

Restrições importantes:

- preserve as regras de negócio existentes;
- placa desconhecida não pode impedir evento de entrada/saída;
- não converta `tracking_lost` em saída física;
- preserve idempotência e identidades de evento/visita;
- preserve o modo de simulação sem dependências pesadas de visão;
- não adicione broker, Kubernetes ou serviços distribuídos nesta rodada;
- não versionar credenciais, vídeos, pesos de modelos ou `.env` real;
- prefira mudanças pequenas, testáveis e reversíveis;
- não declare inferência real validada se só executou simulação/testes sintéticos.

Trabalhe a partir da primeira tarefa ainda não concluída em `.ia/codex-tasks.md`. Antes de implementar, apresente um plano curto baseado no código existente. Ao terminar, execute os testes relevantes e informe objetivamente:

- arquivos alterados;
- comportamento implementado;
- testes/comandos executados;
- resultado das verificações;
- limitações ou riscos restantes;
- próxima tarefa recomendada.

Não implemente tarefas futuras apenas porque parecem convenientes. A prioridade é obter medições confiáveis e reduzir processamento mantendo a semântica atual do sistema.

---
