# Backlog de execução para o Codex

Este arquivo deve ser usado como checklist operacional. Antes de iniciar uma tarefa, leia `AGENTS.md`, `.ia/arquitetura.md`, `.ia/regras-de-negocio.md`, `.ia/testes.md` e `.ia/codex-implementation-plan.md`.

## Regra de execução

Execute uma tarefa por vez. Não antecipe infraestrutura de fases futuras. Para cada tarefa:

1. inspecione o código atual antes de editar;
2. descreva brevemente o plano;
3. implemente a menor mudança coerente;
4. acrescente/ajuste testes;
5. execute as verificações relevantes;
6. atualize documentação afetada;
7. informe arquivos alterados, testes executados, resultados e limitações.

## T01 — Baseline de métricas

**Status:** concluída em 13/09/2026. Contadores, durações e logs periódicos/finais implementados no modo de vídeo; 46 testes Python passaram. Evidência em [Testes](testes.md). Benchmark real permanece em T10.

**Objetivo:** tornar o custo atual mensurável.

Implementar contadores e tempos do pipeline de visão sem alterar o contrato da API.

Aceite:

- contar frames recebidos, processados e descartados;
- medir duração das inferências existentes;
- produzir resumo periódico em log estruturado;
- simulação continua funcionando sem bibliotecas de visão;
- testes unitários das métricas quando aplicável.

## T02 — Frame sampling configurável

**Status:** concluída em 13/09/2026. `PROCESS_FPS=3`, seleção temporal, descartes nas métricas e preservação do tempo dos frames implementados. 58 testes Python passaram; Compose validado com `.env.example`. Evidência em [Testes](testes.md). A fila foi implementada na T03; benchmark real permanece em T10.

**Objetivo:** impedir inferência em todos os frames.

Adicionar `PROCESS_FPS`, com default inicial de 3 FPS para modo de vídeo.

Aceite:

- taxa nativa da câmera não define a quantidade de inferências;
- implementação tolera FPS desconhecido/incorreto reportado pelo OpenCV;
- timestamps continuam representando o instante do frame;
- teste cobre seleção/descartes sem exigir câmera real.

## T03 — Bounded/latest-frame queue

**Status:** concluída em 13/09/2026. Captura em thread por conexão, `FRAME_QUEUE_SIZE=5`, descarte de antigos em RTSP, fila com espera por espaço em arquivos, métricas e encerramento limitado. 72 testes Python passaram, incluindo testes com threads reais. Evidência em [Testes](testes.md).

**Objetivo:** evitar backlog.

Criar mecanismo limitado de passagem de frames entre captura e processamento.

Aceite:

- fila possui tamanho máximo configurável;
- sob sobrecarga, frames antigos podem ser descartados;
- não ocorre crescimento ilimitado de memória;
- métricas registram descartes;
- shutdown não fica preso aguardando fila cheia.

## T04 — ROI configurável

**Status:** concluída em 13/09/2026. ROI retangular normalizada e opcional implementada antes do YOLO/ByteTrack, com validação anterior aos imports de visão, restauração das coordenadas do frame completo e testes unitários sem OpenCV/modelos.

**Objetivo:** reduzir a área analisada.

Adicionar ROI de processamento separada do polígono lógico da doca quando necessário.

Aceite:

- coordenadas preferencialmente normalizadas;
- validar limites e configuração inválida;
- preservar transformação necessária para coordenadas usadas pelo tracking/zona;
- documentação explica diferença entre ROI e zona da doca.

## T05 — MotionDetector

**Status:** concluída em 14/09/2026. Detector por diferença entre frames aplicado somente à ROI, configurável, desabilitado por padrão e sem produzir eventos.

**Objetivo:** evitar YOLO em cena estática.

Implementar detector leve de movimento antes da inferência de veículos.

Aceite:

- habilitável/desabilitável por configuração;
- threshold configurável;
- movimento fora da ROI não ativa YOLO;
- detector de movimento não cria eventos de entrada/saída;
- teste com frames sintéticos estáticos e com alteração.

## T06 — Plate capture orientado a estado

**Objetivo:** executar reconhecimento de placa somente quando útil.

Adicionar solicitação explícita de captura ligada ao contexto da visita/track.

Aceite:

- OCR não roda continuamente;
- placa continua opcional;
- uma visita possui limite de tentativas/janela de captura;
- `tracking_lost` continua semanticamente correto;
- teste cobre visita sem placa.

## T07 — CaptureManager

**Objetivo:** coletar poucos candidatos de boa qualidade.

Aceite:

- máximo de candidatos configurável;
- intervalo mínimo entre candidatos;
- candidatos vinculados à identidade correta de stream/track/visita;
- memória liberada ao finalizar/perder a visita.

## T08 — BestFrameSelector

**Objetivo:** reduzir chamadas ao OCR.

Implementar score determinístico usando nitidez, confiança do detector e tamanho da placa.

Aceite:

- algoritmo documentado;
- pesos/thresholds configuráveis quando fizer sentido;
- teste unitário com candidatos sintéticos;
- sem dependência de PaddleOCR para testar seleção.

## T09 — PlateWorker desacoplado

**Objetivo:** OCR lento não bloquear captura/tracking.

Aceite:

- fila limitada de solicitações de placa;
- quantidade limitada de workers;
- modelos não são recarregados a cada requisição;
- resultados retornam ao consenso/contexto correto;
- shutdown previsível.

## T10 — Benchmark da POC

**Objetivo:** comparar baseline e pipeline otimizado.

Criar procedimento reproduzível de benchmark usando o mesmo vídeo.

Registrar:

- duração do vídeo;
- resolução/FPS;
- hardware;
- CPU média/pico;
- memória média/pico;
- número de inferências de veículo;
- número de inferências de placa;
- número de chamadas OCR;
- eventos esperados/observados;
- latência aproximada dos eventos.

Aceite:

- resultados ficam documentados sem afirmar precisão não medida;
- benchmark não exige credenciais nem arquivos privados versionados.

## T11 — Avaliação ONNX

**Objetivo:** verificar se runtime otimizado oferece benefício real.

Só iniciar após T10.

Aceite:

- exportar ou documentar exportação do modelo suportado;
- comparar com baseline anterior;
- manter fallback para implementação atual;
- registrar diferenças de precisão/performance encontradas.

## Definition of Done da rodada

A rodada de otimização está pronta para validação em uma doca real quando T01–T10 estiverem concluídas e houver evidência de que o pipeline processa vídeo sem backlog, reduz chamadas de inferência/OCR e preserva corretamente os eventos logísticos.
