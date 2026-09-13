## Context

Ver [proposal.md](proposal.md) para a motivação. `pipeline.py` já abre RTSP/RTSPS com OpenCV/FFmpeg, timeouts de 5 segundos e espera de reconexão de 3 segundos. Usa YOLO/ByteTrack, coordenadas normalizadas e `ZoneProcessor`, e recria o tracker após queda. `__main__.py` seleciona simulação ou vídeo e encaminha eventos à outbox. O Compose já injeta `VIDEO_SOURCE` e permite o estágio `inference`.

Hoje os imports de inferência precedem a validação da fonte, a validação RTSP verifica apenas o prefixo e a leitura verifica apenas o booleano retornado. Não há log de primeiro frame. Os testes cobrem domínio e outbox, mas não a captura. A documentação declara inferência e integração real ainda não validadas. Não há specs principais existentes em conflito.

## Goals / Non-Goals

**Goals:** consolidar o adaptador existente com validação antecipada, evidência de frames e testes determinísticos de falhas; manter as responsabilidades de domínio, captura e entrega separadas.

**Non-Goals:** alterar o contrato HTTP ou banco, adicionar servidor de streaming, painel, armazenamento de imagens, reidentificação ou paralelismo de inferência. Não exigir pesos de placas com OCR desabilitado.

## Decisions

1. **Reutilizar `SOURCE_MODE=video` e `VIDEO_SOURCE`.** Validar a fonte antes dos imports/modelos, com biblioteca padrão para verificar host e porta RTSP/RTSPS; preservar a string original para conexão. Validar arquivos pelo caminho existente. Não corrigir silenciosamente barras de escape copiadas de Markdown. Manter credenciais apenas na configuração local e exemplos com `rtsp://usuario:senha@camera.local:554/cam/realmonitor?channel=1&subtype=1`. Documentar codificação de caracteres reservados nas credenciais. Um modo novo `rtsp` duplicaria seleção já disponível.

2. **Manter o loop de captura atual e endurecer suas bordas.** Tratar leitura falsa, `None` ou imagem vazia como interrupção; somente depois de validar o frame, registrar o primeiro recebimento daquela conexão e executar inferência. Os logs usam `camera_id`, dimensões e estado da captura, sem interpolar fonte nem exceções que a contenham. Manter os limites de 5 segundos e a espera `stop.wait(3)` existentes; novos parâmetros e backoff ficam desnecessários para esta POC.

3. **Preservar semântica de tracking e entrega.** Reusar `processor.interrupt()` para limpar estados e gerar perdas; a limpeza repetida no `finally` não pode duplicar eventos. Liberar a captura também nos caminhos de erro. Recriar o tracker antes de processar a conexão seguinte; manter `stream_id` por execução e gerar visitas novas pelo domínio. Continuar emitindo pela outbox, sem criar acesso direto ao PostgreSQL no worker.

4. **Testar o adaptador sem instalar modelos.** Usar `unittest` e dublês de captura, detector, frames e relógio com `unittest.mock`; acionar o processador de domínio real em sequências controladas para verificar eventos e reutilização de IDs. Preferir pontos de substituição pequenos ou patch de imports a uma nova hierarquia de adaptadores. Cobrir arquivo local para evitar regressão no caminho compartilhado. Testes de fila existentes verificam retry; validação operacional verifica o encadeamento completo com API.

5. **Separar evidência automática da operacional.** O roteiro real começa com `inference`, OCR desligado e zona ajustada; comprova primeiro frame, movimentação anotada manualmente, persistência via consultas existentes, queda/retorno e recuperação da API. Registrar hardware, versões, pesos, zona, intervalo observado, falhas e resultados, sem guardar imagens ou URL. Um stream funcionando sem veículos comprova apenas captura; testes com dublês não comprovam precisão da inferência. OCR real é uma etapa condicional à disponibilidade do detector de placas.

## Risks / Trade-offs

- Rede do container sem rota para a câmera ou credenciais inválidas → verificar alcance a partir do ambiente de execução; registrar indisponibilidade sem presumir causa específica.
- Backend nativo pode produzir mensagens próprias com detalhes da fonte → não propagar URLs em logs da aplicação e verificar saída nativa no ensaio real; registrar eventual limitação sem afirmar sanitização universal.
- Qualidade do substream, oclusões e CPU podem reduzir detecção e estabilidade → ajustar enquadramento/zona e registrar resultados observados; não prometer precisão numérica sem ensaio.
- Timeouts dependem do backend e não limitam a duração da inferência → verificar interrupção no ambiente real e não apresentar os 5 segundos como SLA de encerramento do processo inteiro.
- Falha abrupta do worker pode deixar visitas abertas → manter a limitação documentada; reconciliação de sessões está fora desta mudança.

## Migration Plan

Não há migração de dados. Atualizar código/testes e documentação; preservar `.env` existente. No ambiente de validação, configurar localmente a URL e `SOURCE_MODE=video`, `VISION_BUILD_TARGET=inference`, `OCR_ENABLED=false`, ajustar a zona e executar `docker compose up --build -d`. Confirmar captura e eventos antes de habilitar OCR.

Para interromper a validação, parar `vision` preservando volumes e dados. Para retomar a simulação, restaurar os dois seletores para `simulation` e reconstruir; documentar que isso gera novos eventos sintéticos. Não executar `down -v` nem sobrescrever configuração local. Registrar etapas reais indisponíveis como pendentes.
