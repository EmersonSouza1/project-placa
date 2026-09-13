## 1. Configuração e captura

- [x] 1.1 Validar `VIDEO_SOURCE` antes dos imports/modelos de inferência, preservando URL autenticada, query e arquivos locais; verificar com testes de fonte ausente, RTSP/RTSPS válido, host ausente, porta inválida e caminho inexistente, sem dependências de visão.
- [x] 1.2 Tratar frames ausentes/vazios como falha de captura e adicionar logs de primeiro frame por conexão com câmera e dimensões; verificar com dublês que nenhum frame inválido alcança inferência, que abertura sem imagem não gera sucesso e que os logs da aplicação não contêm URL ou credenciais fictícias usadas no teste.
- [x] 1.3 Consolidar liberação, interrupção e reconexão no pipeline existente, preservando timeouts de 5 segundos e espera interrompível de 3 segundos; verificar falha inicial, queda de leitura, encerramento durante espera e limpeza repetida sem evento duplicado.

## 2. Comportamento do pipeline

- [x] 2.1 Adicionar testes do pipeline com detector/captura/relógio substituídos e domínio real: entrada/saída, início dentro, ausência de detecção, OCR desligado e enriquecimento com leituras controladas; verificar tipos, coordenadas normalizadas, identidades e eventos enviados ao callback da outbox.
- [x] 2.2 Testar queda com visita ativa e reconexão com reutilização do track numérico; verificar `tracking_lost` único, novo `visit_id`, `observed_inside`, mesmo `stream_id` e recriação do tracker.
- [x] 2.3 Cobrir arquivo local até EOF e seleção padrão da simulação; verificar ausência de replay, preservação do tempo de mídia e independência de modelos/câmera na simulação.
- [x] 2.4 Executar em `services/vision` o comando `uv run --no-project --python 3.11 python -m unittest discover -s tests -v`; verificar toda a suíte de domínio, outbox e pipeline e registrar resultados sem classificá-los como validação de inferência real.

## 3. Operação e documentação

- [x] 3.1 Atualizar `.env.example`, README e `.ia/operacao.md` com exemplo RTSP de placeholders no formato `/cam/realmonitor?channel=1&subtype=1`, seletores de vídeo/inferência, preservação do `.env`, ausência de escapes Markdown na URL, caracteres reservados, ajuste de zona e OCR opcional; revisar comandos e links e confirmar que nenhum segredo real foi incluído.
- [x] 3.2 Atualizar `.ia/arquitetura.md` e `.ia/testes.md` com validação da fonte, logs de captura, recuperação e cobertura adicionada; entregar roteiro real que separe conexão, frames, detecção, eventos e persistência e registre limitações do backend nativo e da inferência.

## 4. Validação operacional

- [ ] 4.1 Com câmera acessível e pesos disponíveis, configurar o ambiente local sem versionar a URL, subir o estágio `inference` com OCR desligado e zona ajustada; verificar primeiro frame e dimensões e registrar ambiente/resultado sem credenciais. Se indisponível, manter esta tarefa pendente e registrar o impedimento.
- [ ] 4.2 Observar uma entrada/saída e um início dentro, comparar anotações com `GET /dock-events` e `GET /dock-stays`, e testar queda/retorno do stream; verificar permanência, placa nula, interrupção sem saída fictícia e visita nova após reconexão. Registrar resultados e qualquer evento falso/ausente, sem afirmar precisão geral.
- [ ] 4.3 Com API/PostgreSQL de testes ativos, executar na raiz `uv run --no-project --python 3.11 python tests/api_smoke.py -v` e ensaiar indisponibilidade temporária da API durante geração de eventos reais; verificar recuperação da fila sem duplicatas e registrar evidências. Manter pendente se a infraestrutura não estiver disponível.

OCR real pode ser validado posteriormente quando houver detector de placas treinado; testes com leituras controladas não comprovam reconhecimento real. Nenhuma tarefa operacional deve ser marcada concluída apenas com evidência de simulação.

## Evidência da aplicação em 12/09/2026

Concluídas as tarefas 1.1–3.2: 32 testes Python passaram; validação OpenSpec estrita e links locais aprovados. As tarefas 4.1–4.3 permanecem pendentes: Docker não encontrado no PATH nem no caminho padrão, OpenCV/Ultralytics ausentes no Python inspecionado, pesos não provisionados e nenhuma API escutando em 127.0.0.1:5080. A câmera real não foi acessada. Configuração local e dados preservados. Consulte .ia/testes.md para evidências e roteiro operacional.

Atualização na mesma data, após solicitação de inicialização: Docker Desktop localizado no perfil do usuário fora do sandbox. Compose construiu e iniciou os três serviços; API saudável, primeiro frame real de 640 × 480 recebido e 7 testes de integração aprovados dentro do container. Dependências Python foram instaladas na imagem; não são necessárias no host. A tarefa 4.1 permanece parcialmente atendida porque a zona ainda é a padrão, sem calibração visual. A tarefa 4.2 aguarda ensaio de movimentação e reconexão; 4.3 já tem smoke aprovado, mas ainda aguarda indisponibilidade da API com eventos reais. Nenhuma dessas tarefas foi marcada completa com evidência parcial. Detalhes em `.ia/testes.md`.
